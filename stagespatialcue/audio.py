"""Real output-device selection, decoding, and cue sequence orchestration."""
from __future__ import annotations

import math
import os
import json
import re
from datetime import datetime, timezone
import shutil
import subprocess
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from uuid import uuid4
from functools import wraps

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .mixer import Mixer, SAMPLE_RATE
from .models import Cue, CueLayer, MediaItem, PlaybackSpec, Project, media_display_name
from .storage import ProjectStore

MAX_CLIP_SECONDS = 30 * 60  # pre-decoded prototype; no long-file streaming
MAX_CACHE_BYTES = 700 * 1024 * 1024


def controlled_connection(method):
    """Turn driver failures into actionable errors with no live output left behind."""
    @wraps(method)
    def connect(self, *args, **kwargs):
        with self.lock:
            if self.measurement_active:
                raise ValueError("AutoCal measurement active; wait before connecting output")
            try:
                return method(self, *args, **kwargs)
            except Exception as exc:
                try:
                    self.disconnect()
                except Exception:
                    pass  # disconnect's finally clears references even if driver close fails
                self.audio_error = f"Output connection failed: {exc}. Select an available device and reconnect."
                raise ValueError(self.audio_error) from exc
    return connect


def decode_audio(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode to float32 frames x channels (1 or 2) at the mixer's fixed rate.

    Stereo stays stereo; the mixer downmixes or widens per cue. Sources with more
    than two channels are downmixed to mono. WAV/AIFF/FLAC/OGG via libsndfile,
    MP3/M4A/AAC fallback via FFmpeg.
    """
    try:
        with sf.SoundFile(path) as file:
            if len(file) / file.samplerate > MAX_CLIP_SECONDS:
                raise ValueError("Audio file exceeds 30-minute predecode limit")
            data = file.read(dtype="float32", always_2d=True)
            source_rate = file.samplerate
        if data.shape[1] > 2:
            data = data.mean(axis=1, keepdims=True, dtype=np.float32)
        if source_rate != sample_rate:
            gcd = math.gcd(source_rate, sample_rate)
            data = resample_poly(data, sample_rate // gcd, source_rate // gcd, axis=0).astype(np.float32)
        return np.ascontiguousarray(data, dtype=np.float32)
    except (sf.LibsndfileError, RuntimeError):
        if shutil.which("ffmpeg") is None:
            raise ValueError("Unsupported file: install FFmpeg or convert to WAV/FLAC")
        channels = 2 if audio_channels(path) == 2 else 1
        cmd = [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
            "-t", str(MAX_CLIP_SECONDS), "-f", "f32le", "-ac", str(channels),
            "-ar", str(sample_rate), "pipe:1",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        if result.returncode:
            raise ValueError(result.stderr.decode(errors="replace")[-300:])
        return np.frombuffer(result.stdout, dtype="<f4").reshape(-1, channels).copy()


def audio_channels(path: Path) -> int:
    """Source channel count for the editor (1 when unknown)."""
    try:
        return sf.info(str(path)).channels
    except (sf.LibsndfileError, RuntimeError):
        if not shutil.which("ffprobe"):
            return 1
        result = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
            "stream=channels", "-of", "csv=p=0", str(path),
        ], capture_output=True, text=True, timeout=20)
        try:
            return max(1, int(result.stdout.strip().splitlines()[0]))
        except (ValueError, IndexError):
            return 1


def audio_duration(path: Path) -> float:
    try:
        with sf.SoundFile(path) as f:
            return round(len(f) / f.samplerate, 3)
    except (sf.LibsndfileError, RuntimeError):
        if not shutil.which("ffprobe"):
            return 0
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ], capture_output=True, text=True, timeout=20)
        try:
            return round(float(result.stdout), 3)
        except (ValueError, TypeError):
            return 0


def media_item(path: Path, relative: str, display_name: str) -> MediaItem:
    """Library entry for an imported file: name, duration and channel count.

    Stereo files keep stereo (width 90° = L/R on the speaker pair around the layer).
    """
    channels = audio_channels(path)
    return MediaItem(name=media_display_name(display_name), filename=display_name, media_relpath=relative,
                     duration_s=audio_duration(path), source_channels=channels,
                     stereo_mode="width" if channels == 2 else "mono")


def single_layer_cue(media: MediaItem, **fields) -> Cue:
    """A cue that plays one library sound at the front (the pre-v4 import behaviour)."""
    return Cue(title=fields.pop("title", media.name),
               layers=[CueLayer(media_id=media.id)], gain_db=fields.pop("gain_db", -6), **fields)


def filename_key(item):
    """Numbered names (001_...) first in numeric order, then alphabetical."""
    name = item.filename
    match = re.match(r"^(\d{1,5})[-_ ]", name)
    return (0, int(match.group(1)), name.lower()) if match else (1, name.lower(), "")


class StageController:
    def __init__(self, store: ProjectStore):
        self.lock = RLock()
        self.store = store
        self.project_id: str | None = None
        self.mixer: Mixer | None = None
        self.next_cue_id: str | None = None
        self.needs_rearm = False
        self.output_device: int | None = None
        self.stream = None
        self.audio_error: str | None = None
        self.xruns = 0
        self.measurement_active = False
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.cache_lock = RLock()
        self.decode_lock = RLock()
        self._loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spatialstage-decode")
        self._prepare_key = None
        self.preparing = False
        self.prepare_error: str | None = None
        self._closing = False
        self.monitor_pose = (0.0, 0.0, 0.0)  # virtual headphone listener: x, y, head bearing

    @property
    def next_index(self) -> int:
        cues = self.mixer.project.cues if self.mixer else []
        return next((i for i, c in enumerate(cues) if c.id == self.next_cue_id), len(cues))

    @next_index.setter
    def next_index(self, index: int) -> None:
        cues = self.mixer.project.cues if self.mixer else []
        self.next_cue_id = cues[index].id if index < len(cues) else None
        self.needs_rearm = False

    def _cue_media(self, project: Project, cue: Cue) -> list[MediaItem]:
        media = project.media_by_id()
        return [media[layer.media_id] for layer in cue.layers if not layer.muted]

    def _sources(self, project: Project, cue: Cue, *, allow_decode: bool = True) -> list[tuple[PlaybackSpec, np.ndarray, int]]:
        """(spec, trimmed samples, delay frames) for every audible layer of a cue."""
        media = project.media_by_id()
        result = []
        for spec in project.cue_specs(cue):
            item = media[spec.media_id]
            clip = self._clip(project, item, allow_decode=allow_decode)
            samples = self._trimmed(clip, item)
            result.append((spec, samples, int(round(next(layer.delay_s for layer in cue.layers
                                                         if layer.id == spec.layer_id) * SAMPLE_RATE))))
        return result

    @staticmethod
    def _trimmed(clip: np.ndarray, item: MediaItem) -> np.ndarray:
        start = int(round(item.trim_start_s * SAMPLE_RATE))
        end = int(round(item.trim_end_s * SAMPLE_RATE)) if item.trim_end_s else len(clip)
        samples = clip[min(start, len(clip)):min(end, len(clip))]  # a view, never a copy
        if not len(samples):
            raise ValueError(f"Audio trim leaves no sound: {item.name}")
        return samples

    def _chain(self, project: Project, *, cut: bool = False) -> list[Cue]:
        index = next((i for i, c in enumerate(project.cues) if c.id == self.next_cue_id), len(project.cues))
        chain = []
        for cue in project.cues[index:]:
            chain.append(cue)
            if cut or cue.continue_mode == "manual":
                break
        return chain

    def _warm_next(self, project: Project) -> None:
        """ARM/sync primes the next automatic group; no decoder in GO or callback."""
        chain = self._chain(project)
        key = (project.id, tuple((c.id, tuple(m.media_relpath for m in self._cue_media(project, c))) for c in chain))
        if key == self._prepare_key:
            return
        self._prepare_key = key
        self.prepare_error = None
        self.preparing = bool(chain)
        if not chain:
            return
        snapshot = project.model_copy(deep=True)

        def prepare():
            error = None
            try:
                for cue in chain:
                    if self._prepare_key != key:
                        return
                    for item in self._cue_media(snapshot, cue):
                        self._clip(snapshot, item)
            except Exception as exc:
                error = str(exc)
            finally:
                with self.lock:
                    if self._prepare_key == key:
                        self.preparing = False
                        self.prepare_error = error
        self._loader.submit(prepare)

    def _ready(self) -> bool:
        if self.mixer is None or self.needs_rearm:
            return False
        chain = self._chain(self.mixer.project)
        try:
            for cue in chain:
                self._sources(self.mixer.project, cue, allow_decode=False)
            return bool(chain)
        except (ValueError, OSError):
            return False

    def _output_active(self) -> bool:
        if self.stream is None:
            return False
        try:
            active = bool(self.stream.active)
        except Exception:
            active = False
        if not active:
            self.audio_error = "Output stream stopped or device lost. Reconnect and unmute manually."
            if self.mixer:
                self.mixer.panic()
        return active

    def shutdown(self) -> None:
        self.disconnect()
        self._prepare_key = None
        self._loader.shutdown(wait=False, cancel_futures=True)

    def log(self, event: str, **fields) -> None:
        """Operator-only diagnostics disabled by default; no participant research log."""
        if os.environ.get("SPATIALSTAGE_DIAGNOSTICS") != "1":
            return
        if not self.project_id:
            return
        path = self.store.directory(self.project_id) / "events.jsonl"
        entry = {"utc": datetime.now(timezone.utc).isoformat(),
                 "project_id": self.project_id,
                 "sample_frame": self.mixer.frame if self.mixer else None,
                 "event": event, **fields}
        with self.lock:
            with path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def devices(self) -> dict:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            return {
                "inputs": [{"index": i, "name": d["name"], "channels": d["max_input_channels"]}
                           for i, d in enumerate(devices) if d["max_input_channels"] >= 1],
                "outputs": [{"index": i, "name": d["name"], "channels": d["max_output_channels"]}
                            for i, d in enumerate(devices) if d["max_output_channels"] >= 1],
            }
        except Exception as e:
            return {"inputs": [], "outputs": [], "error": f"CoreAudio/PortAudio unavailable: {e}"}

    def arm(self, project_id: str, index: int = 0, cue_id: str | None = None) -> dict:
        with self.lock:
            if self.measurement_active:
                raise ValueError("AutoCal measurement active; do not arm playback")
            project = self.store.get(project_id)
            if cue_id is not None:
                index = next((i for i, c in enumerate(project.cues) if c.id == cue_id), -1)
            if not 0 <= index <= len(project.cues):
                raise ValueError("Cue index out of range")
            if project_id != self.project_id:
                if self.mixer:
                    self.mixer.panic()
                self.project_id = project_id
                self.mixer = Mixer(project)
                self._apply_calibration(project)
                with self.cache_lock:
                    self.cache.clear()
                self.next_index = index
            else:
                self.mixer.update_project(project)
                self._apply_calibration(project)
                # Selecting a future cue during playback does not restart the show clock.
                if not self.mixer.voices:
                    self.mixer.reset_show_clock()
                self.next_index = index
            self._warm_next(project)
            self.log("operator_arm", next_index=index)
            return self.status()

    def sync(self, project: Project) -> None:
        with self.lock:
            if project.id == self.project_id and self.mixer:
                was_empty = not self.mixer.project.cues
                self.mixer.update_project(project)
                self._apply_calibration(project)
                if self.next_cue_id and not any(c.id == self.next_cue_id for c in project.cues):
                    self.next_cue_id = None
                    self.needs_rearm = True  # never silently substitute another cue
                elif was_empty and not self.needs_rearm and project.cues:
                    self.next_index = 0
                self._warm_next(project)

    def _apply_calibration(self, project: Project) -> None:
        """Resolve saved approved profiles on arm, restart, and every project sync."""
        if not self.mixer:
            return
        if not project.calibration_enabled or not project.active_calibration_id:
            self.mixer.set_calibration([0.0] * 4, [0.0] * 4)
            return
        from .autocal import geometry_signature
        sid = project.active_calibration_id
        path = self.store.directory(project.id) / "autocal" / f"{sid}.json"
        if not path.is_file():
            raise ValueError("Active AutoCal profile is missing. Disable AutoCal first")
        profile = json.loads(path.read_text(encoding="utf-8"))
        if (profile.get("status") != "applied" or not profile.get("quality_ok") or
                profile.get("speaker_signature") != geometry_signature(project.speakers) or
                project.distance_compensation or any(s.trim_db != 0 for s in project.speakers)):
            raise ValueError("Active AutoCal is invalid for current speaker routing. Disable it")
        recommendation = profile["recommendations"]
        self.mixer.set_calibration(recommendation["channel_gain_db"], recommendation["channel_delay_ms"])

    @controlled_connection
    def connect_simulation(self, device_index: int | None = None, monitor: str = "virtual") -> dict:
        from .simulation import SimulationStream, StereoMonitorStream, VirtualMonitorStream
        with self.lock:
            if self.mixer is None:
                raise ValueError("Arm a project first")
            if self.measurement_active:
                raise ValueError("AutoCal measurement active")
            self.disconnect()
            self.audio_error = None
            self.xruns = 0
            if device_index is None:
                self.stream = SimulationStream(self)
            elif monitor == "virtual":
                self.stream = VirtualMonitorStream(self, device_index, self.monitor_pose)
            else:
                self.stream = StereoMonitorStream(self, device_index)
            try:
                self.stream.start()
            except Exception:
                self.stream.close()
                self.stream = None
                raise
            return self.status()

    @controlled_connection
    def connect(self, device_index: int) -> dict:
        import sounddevice as sd
        with self.lock:
            if self.mixer is None:
                raise ValueError("Create/arm a project first")
            if self.measurement_active:
                raise ValueError("AutoCal measurement active; wait before connecting live audio")
            if self.mixer.project.calibration_enabled:
                profile_path = self.store.directory(self.mixer.project.id) / "autocal" / f"{self.mixer.project.active_calibration_id}.json"
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                device_name = str(sd.query_devices(device_index)["name"])
                if device_name != profile["output_device_name"]:
                    raise ValueError("Output interface differs from approved AutoCal profile; disable it or use measured interface")
            if self.stream is not None:
                self.disconnect()
            details = sd.query_devices(device_index)
            if details["max_output_channels"] < 4:
                raise ValueError("Output device must provide at least 4 independent channels")
            sd.check_output_settings(device=device_index, channels=4, samplerate=SAMPLE_RATE, dtype="float32")
            self.mixer.panic()  # loudness must be explicitly unmuted after re-patching
            self.xruns = 0
            self.audio_error = None

            def callback(outdata, frames, time_info, status):
                if status:
                    self.xruns += 1
                try:
                    outdata[:] = self.mixer.render(frames)
                except Exception as e:
                    outdata[:] = 0
                    self.audio_error = f"Mixer error: {e}; reconnect required"
                    self.mixer.panic()

            def finished():
                if not self._closing:
                    self.audio_error = "Output stream became inactive; reconnect required"
                    if self.mixer:
                        self.mixer.panic()

            self.stream = sd.OutputStream(
                device=device_index, samplerate=SAMPLE_RATE, channels=4,
                dtype="float32", blocksize=512, latency="low", callback=callback,
                finished_callback=finished,
            )
            try:
                self.stream.start()
            except Exception:
                self.stream.close()
                self.stream = None
                raise
            self.output_device = device_index
            self.log("output_connected", device_index=device_index)
            return self.status()

    def disconnect(self) -> dict:
        with self.lock:
            if self.mixer:
                self.mixer.panic()
            self._closing = True
            try:
                if self.stream is not None:
                    try:
                        self.stream.stop()
                    finally:
                        self.stream.close()
            finally:
                self.stream = None
                self.output_device = None
                self._closing = False
            self.log("output_disconnected")
            return self.status()

    def _clip(self, project: Project, media: MediaItem, *, allow_decode: bool = True) -> np.ndarray:
        """Whole decoded file, shared by every layer and cue that uses it."""
        if not media.media_relpath:
            raise ValueError(f"Audio has no file: {media.name}")
        path = self.store.media_path(project.id, media.media_relpath)
        stat = path.stat()
        key = f"{project.id}:{media.media_relpath}:{stat.st_mtime_ns}:{stat.st_size}"
        with self.cache_lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        if not allow_decode:
            raise ValueError(f"Audio not ready: {media.name}. Run Preflight / wait for ARM preload before GO")
        # This lock serializes decoders only, never the render/control/status path.
        with self.decode_lock:
            with self.cache_lock:
                if key in self.cache:
                    return self.cache[key]
            audio = decode_audio(path)
            if not len(audio) or not np.isfinite(audio).all():
                raise ValueError(f"Empty or non-finite audio: {media.filename}")
            if audio.nbytes > MAX_CACHE_BYTES:
                raise ValueError("Clip exceeds the 700 MiB decoded cache; split the source file")
            audio.flags.writeable = False
            with self.cache_lock:
                while self.cache and sum(arr.nbytes for arr in self.cache.values()) + audio.nbytes > MAX_CACHE_BYTES:
                    self.cache.popitem(last=False)
                self.cache[key] = audio
            return audio

    def preflight(self, project_id: str) -> dict:
        project = self.store.get(project_id)
        problems = []
        total = 0
        decoded = set()
        for cue in project.cues:
            try:
                for item in self._cue_media(project, cue):
                    clip = self._clip(project, item)
                    self._trimmed(clip, item)
                    if item.media_relpath not in decoded:  # one cache entry per file
                        decoded.add(item.media_relpath)
                        total += clip.nbytes
            except Exception as e:
                problems.append(f"{cue.title}: {e}")
        if total > MAX_CACHE_BYTES:
            problems.append("Total decoded audio exceeds 700 MiB cache: split the show or preload each next group; GO never decodes")
        if not self._output_active():
            problems.append("Select and connect a 4-output sound interface")
        return {"ok": not problems, "issues": problems, "decoded_mib": round(total / 1048576, 1),
                "count": len(project.cues), "files": len(decoded)}

    def go(self, project_id: str, *, cut: bool = False) -> dict:
        with self.lock:
            if self.measurement_active:
                raise ValueError("AutoCal measurement active")
            if not self._output_active() or self.audio_error:
                raise ValueError(self.audio_error or "Connect a 4-channel output device first")
            if self.mixer and self.mixer.master_mute:
                raise ValueError("MAIN MUTE is on. Unmute deliberately before GO")
            if self.project_id != project_id or self.mixer is None:
                raise ValueError("Arm this project first")
            project = self.store.get(project_id)
            self.mixer.update_project(project)
            if self.needs_rearm:
                raise ValueError("NEXT cue was removed. Select and ARM a cue explicitly")
            if self.next_index >= len(project.cues):
                raise ValueError("End of cue list. ARM a cue to replay")
            idx = self.next_index
            # Collect all automatically linked files BEFORE adding any voices.
            chain = []
            while idx < len(project.cues):
                cue = project.cues[idx]
                sources = self._sources(project, cue, allow_decode=False)
                chain.append((cue, sources))
                idx += 1
                # A looping layer never ends, so nothing can follow "after it ends".
                endless = any(spec.loop for spec, _, _ in sources)
                if cut or cue.continue_mode == "manual" or (cue.continue_mode == "auto_follow" and endless):
                    break
            with self.mixer.lock:
                anchor = None
                chain_id = uuid4().hex
                for n, (cue, sources) in enumerate(chain):
                    start, voices = self.mixer.queue_group(cue, sources, anchored_frame=anchor,
                                                           force_cut=(cut and n == 0), chain_id=chain_id)
                    if cue.continue_mode == "auto_continue":
                        anchor = start + int(round(cue.post_wait_s * SAMPLE_RATE))
                    elif cue.continue_mode == "auto_follow":
                        end = max([v.end_frame for v in voices], default=start)
                        anchor = end + int(round(cue.post_wait_s * SAMPLE_RATE))
                    else:
                        anchor = None
            self.next_index = idx
            self._warm_next(project)
            self.log("operator_cut_go" if cut else "operator_fade_go", first_index=self.next_index-len(chain),
                     scheduled=[{"cue_id": c.id, "title": c.title, "layers": len(sources),
                                 "mode": c.start_mode} for c, sources in chain])
            return self.status()

    def audition(self, project_id: str, cue_id: str) -> dict:
        """One selected cue, immediate replacement, no automatic chain; NEXT stays here."""
        with self.lock:
            if self.measurement_active or not self._output_active() or self.audio_error:
                raise ValueError("Connect an output in Edit first; measurement must be stopped")
            if self.project_id != project_id or self.mixer is None:
                raise ValueError("Arm this project first")
            if self.mixer.master_mute:
                raise ValueError("MAIN MUTE is ON. Unmute deliberately before audition")
            project = self.store.get(project_id)
            cue = next((c for c in project.cues if c.id == cue_id), None)
            if cue is None:
                raise ValueError("Cue missing")
            sources = self._sources(project, cue, allow_decode=False)
            self.mixer.update_project(project)
            self.mixer.queue_group(cue, sources, force_cut=True)
            self.next_index = project.cues.index(cue)
            self.log("operator_audition", cue_id=cue_id)
            return self.status()

    def _playable(self, project_id: str) -> Project:
        if self.measurement_active or not self._output_active() or self.audio_error:
            raise ValueError(self.audio_error or "Connect an output first; measurement must be stopped")
        if self.project_id != project_id or self.mixer is None:
            raise ValueError("Arm this project first")
        if self.mixer.master_mute:
            raise ValueError("MAIN MUTE is on. Unmute deliberately before GO")
        return self.store.get(project_id)

    def play_cue(self, project_id: str, cue_id: str) -> dict:
        """▶ on one cue: start it now on top of everything else; NEXT is unchanged.

        If the cue is already sounding it restarts from the top (its old voices
        fade out in 50 ms). Pre-wait is skipped; each layer keeps its delay.
        """
        with self.lock:
            project = self._playable(project_id)
            cue = next((c for c in project.cues if c.id == cue_id), None)
            if cue is None:
                raise ValueError("Cue missing")
            sources = self._sources(project, cue, allow_decode=False)
            self.mixer.update_project(project)
            with self.mixer.lock:
                self.mixer.stop_group(cue.id, 0.05)
                self.mixer.queue_group(PlaybackSpec(start_mode="layer", pre_wait_s=0), sources)
            self.log("operator_play_cue", cue_id=cue_id)
            return self.status()

    def stop_cue(self, project_id: str, cue_id: str) -> dict:
        """■ on one cue: fade only that cue out over its stop_fade_s."""
        with self.lock:
            if self.project_id != project_id or self.mixer is None:
                raise ValueError("Arm this project first")
            project = self.store.get(project_id)
            cue = next((c for c in project.cues if c.id == cue_id), None)
            if cue is None:
                raise ValueError("Cue missing")
            self.mixer.stop_group(cue.id, cue.stop_fade_s)
            self.log("operator_stop_cue", cue_id=cue_id, fade_s=cue.stop_fade_s)
            return self.status()

    def audition_media(self, project_id: str, media_id: str) -> dict:
        """Preview one library sound with its design, front centre; NEXT is untouched.

        Decoding is allowed here (never in GO): it runs in the request thread.
        """
        with self.lock:
            if self.measurement_active or not self._output_active() or self.audio_error:
                raise ValueError("Connect an output first; measurement must be stopped")
            if self.project_id != project_id or self.mixer is None:
                raise ValueError("Arm this project first")
            if self.mixer.master_mute:
                raise ValueError("MAIN MUTE is ON. Unmute deliberately before audition")
            project = self.store.get(project_id)
            item = project.media_by_id().get(media_id)
            if item is None:
                raise ValueError("Audio is not in the library")
        samples = self._trimmed(self._clip(project, item), item)
        spec = PlaybackSpec(id=f"audition:{item.id}", media_id=item.id, title=item.name,
                            duration_s=item.play_duration_s, gain_db=item.gain_db - 6,
                            source_channels=item.source_channels, stereo_mode=item.stereo_mode,
                            stereo_width_deg=item.stereo_width_deg, fade_in_s=item.fade_in_s,
                            fade_out_s=item.fade_out_s, loop=item.loop)
        with self.lock:
            self.mixer.queue_group(spec, [(spec, samples, 0)], force_cut=True)
            self.log("operator_audition_media", media_id=media_id)
            return self.status()

    def can_update(self, project: Project) -> None:
        """Reject hot speaker channel remapping while an output is unmuted."""
        with self.lock:
            if self.mixer and self.project_id == project.id:
                old_ids = [c.id for c in self.mixer.project.cues]
                new_ids = [c.id for c in project.cues]
                if set(old_ids) == set(new_ids) and old_ids != new_ids and self.mixer.voices:
                    raise ValueError("STOP active/queued cues before changing playback order")
            if self.mixer and self.project_id == project.id and self.stream is not None:
                old = self.mixer.project
                if ((old.speakers != project.speakers or
                     (old.calibration_enabled and old.distance_compensation != project.distance_compensation))
                     and not (self.mixer.master_mute and self.mixer._master_ramp.value == 0)):
                    raise ValueError("MAIN MUTE and wait for its ramp to settle before changing stage geometry/routing")

    def skip(self) -> dict:
        with self.lock:
            if self.mixer is None or self.project_id is None:
                raise ValueError("No project armed")
            project = self.store.get(self.project_id)
            if self.needs_rearm:
                raise ValueError("NEXT cue was removed. Select and ARM a cue explicitly")
            self.next_index = min(len(project.cues), self.next_index + 1)
            self._warm_next(project)
            self.log("operator_skip", next_index=self.next_index)
            return self.status()

    def status(self) -> dict:
        with self.lock:
            from .simulation import SimulationStream
            simulated = isinstance(self.stream, SimulationStream)
            connected = self._output_active()
            if self.mixer:
                for audio_event in self.mixer.drain_events():
                    self.log(audio_event.pop("event"), **audio_event)
            mix = self.mixer.status() if self.mixer else None
            return {
                "project_id": self.project_id,
                "next_index": self.next_index,
                "next_cue_id": self.next_cue_id,
                "needs_rearm": self.needs_rearm,
                "ready": self._ready(),
                "preparing": self.preparing,
                "prepare_error": self.prepare_error,
                "output_device": self.output_device,
                "output_mode": "simulation" if simulated else "hardware",
                "simulation": self.stream.status() if simulated else None,
                "connected": connected,
                "error": self.audio_error,
                "xruns": self.xruns,
                "measurement_active": self.measurement_active,
                "mixer": mix,
            }
