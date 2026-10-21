"""Real output-device selection, decoding, and cue sequence orchestration."""
from __future__ import annotations

import math
import os
import json
from datetime import datetime, timezone
import shutil
import subprocess
from collections import OrderedDict
from pathlib import Path
from threading import RLock

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .mixer import Mixer, SAMPLE_RATE
from .models import Project, Cue
from .storage import ProjectStore

MAX_CLIP_SECONDS = 30 * 60  # pre-decoded prototype; no long-file streaming
MAX_CACHE_BYTES = 700 * 1024 * 1024


def decode_audio(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode to mono floating-point at the mixer's fixed rate.

    WAV/AIFF/FLAC/OGG via libsndfile, MP3/M4A/AAC fallback via FFmpeg.
    """
    try:
        with sf.SoundFile(path) as file:
            if len(file) / file.samplerate > MAX_CLIP_SECONDS:
                raise ValueError("Audio file exceeds 30-minute predecode limit")
            data = file.read(dtype="float32", always_2d=True)
            source_rate = file.samplerate
        mono = data.mean(axis=1, dtype=np.float32)
        if source_rate != sample_rate:
            gcd = math.gcd(source_rate, sample_rate)
            mono = resample_poly(mono, sample_rate // gcd, source_rate // gcd).astype(np.float32)
        return mono
    except (sf.LibsndfileError, RuntimeError):
        if shutil.which("ffmpeg") is None:
            raise ValueError("Unsupported file: install FFmpeg or convert to WAV/FLAC")
        cmd = [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
            "-t", str(MAX_CLIP_SECONDS), "-f", "f32le", "-ac", "1",
            "-ar", str(sample_rate), "pipe:1",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        if result.returncode:
            raise ValueError(result.stderr.decode(errors="replace")[-300:])
        return np.frombuffer(result.stdout, dtype="<f4").copy()


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


class StageController:
    def __init__(self, store: ProjectStore):
        self.lock = RLock()
        self.store = store
        self.project_id: str | None = None
        self.mixer: Mixer | None = None
        self.next_index = 0
        self.output_device: int | None = None
        self.stream = None
        self.audio_error: str | None = None
        self.xruns = 0
        self.measurement_active = False
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()

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

    def arm(self, project_id: str, index: int = 0) -> dict:
        with self.lock:
            if self.measurement_active:
                raise ValueError("AutoCal measurement active; do not arm playback")
            project = self.store.get(project_id)
            if not 0 <= index <= len(project.cues):
                raise ValueError("Cue index out of range")
            if project_id != self.project_id:
                if self.mixer:
                    self.mixer.panic()
                self.project_id = project_id
                self.mixer = Mixer(project)
                self._apply_calibration(project)
                self.cache.clear()
                self.next_index = index
            else:
                self.mixer.update_project(project)
                self._apply_calibration(project)
                # Selecting a future cue during playback does not restart the show clock.
                if not self.mixer.voices:
                    self.mixer.reset_show_clock()
                self.next_index = index
            self.log("operator_arm", next_index=index)
            return self.status()

    def sync(self, project: Project) -> None:
        with self.lock:
            if project.id == self.project_id and self.mixer:
                self.mixer.update_project(project)
                self._apply_calibration(project)
                self.next_index = min(self.next_index, len(project.cues))

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
        profile = json.loads(path.read_text())
        if (profile.get("status") != "applied" or not profile.get("quality_ok") or
                profile.get("speaker_signature") != geometry_signature(project.speakers) or
                project.distance_compensation or any(s.trim_db != 0 for s in project.speakers)):
            raise ValueError("Active AutoCal is invalid for current speaker routing. Disable it")
        recommendation = profile["recommendations"]
        self.mixer.set_calibration(recommendation["channel_gain_db"], recommendation["channel_delay_ms"])

    def connect(self, device_index: int) -> dict:
        import sounddevice as sd
        with self.lock:
            if self.mixer is None:
                raise ValueError("Create/arm a project first")
            if self.measurement_active:
                raise ValueError("AutoCal measurement active; wait before connecting live audio")
            if self.mixer.project.calibration_enabled:
                profile_path = self.store.directory(self.mixer.project.id) / "autocal" / f"{self.mixer.project.active_calibration_id}.json"
                profile = json.loads(profile_path.read_text())
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
                    self.audio_error = f"Mixer error: {e}"

            self.stream = sd.OutputStream(
                device=device_index, samplerate=SAMPLE_RATE, channels=4,
                dtype="float32", blocksize=512, latency="low", callback=callback,
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
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
            self.stream = None
            self.output_device = None
            self.log("output_disconnected")
            return self.status()

    def _clip(self, project: Project, cue: Cue) -> np.ndarray:
        key = f"{project.id}:{cue.media_relpath}"
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        path = self.store.media_path(project.id, cue.media_relpath)
        if not path.is_file():
            raise FileNotFoundError(f"Missing audio: {cue.filename}")
        audio = decode_audio(path)
        if not len(audio):
            raise ValueError(f"Empty audio file: {cue.filename}")
        while self.cache and sum(arr.nbytes for arr in self.cache.values()) + audio.nbytes > MAX_CACHE_BYTES:
            self.cache.popitem(last=False)
        if audio.nbytes < MAX_CACHE_BYTES:
            self.cache[key] = audio
        return audio

    def preflight(self, project_id: str) -> dict:
        project = self.store.get(project_id)
        problems = []
        total = 0
        for cue in project.cues:
            try:
                clip = self._clip(project, cue)
                total += clip.nbytes
            except Exception as e:
                problems.append(f"{cue.title}: {e}")
        if total > MAX_CACHE_BYTES:
            problems.append("Total decoded audio exceeds 700 MiB cache: GO may block to decode")
        if self.output_device is None:
            problems.append("Select and connect a 4-output sound interface")
        return {"ok": not problems, "issues": problems, "decoded_mib": round(total / 1048576, 1), "count": len(project.cues)}

    def go(self, project_id: str, *, cut: bool = False) -> dict:
        with self.lock:
            if self.measurement_active:
                raise ValueError("AutoCal measurement active")
            if not self.stream:
                raise ValueError("Connect a 4-channel output device first")
            if self.mixer and self.mixer.master_mute:
                raise ValueError("MAIN MUTE is on. Unmute deliberately before GO")
            if self.project_id != project_id or self.mixer is None:
                raise ValueError("Arm this project first")
            project = self.store.get(project_id)
            self.mixer.update_project(project)
            if self.next_index >= len(project.cues):
                raise ValueError("End of cue list. ARM a cue to replay")
            idx = self.next_index
            # Collect all automatically linked files BEFORE adding any voices.
            chain = []
            while idx < len(project.cues):
                cue = project.cues[idx]
                chain.append((cue, self._clip(project, cue)))
                idx += 1
                if cut or cue.continue_mode == "manual":
                    break
            anchor = None
            for n, (cue, clip) in enumerate(chain):
                voice = self.mixer.queue(cue, clip, anchored_frame=anchor, force_cut=(cut and n == 0))
                if cue.continue_mode == "auto_continue":
                    anchor = voice.start_frame + int(round(cue.post_wait_s * SAMPLE_RATE))
                elif cue.continue_mode == "auto_follow":
                    anchor = voice.end_frame + int(round(cue.post_wait_s * SAMPLE_RATE))
                else:
                    anchor = None
            self.next_index = idx
            self.log("operator_cut_go" if cut else "operator_fade_go", first_index=self.next_index-len(chain),
                     scheduled=[{"cue_id": c.id, "title": c.title,
                                 "bearing_deg": c.position_deg, "mode": c.start_mode}
                                for c, _ in chain])
            return self.status()

    def can_update(self, project: Project) -> None:
        """Reject hot speaker channel remapping while an output is unmuted."""
        with self.lock:
            if self.mixer and self.project_id == project.id and self.stream is not None:
                old = self.mixer.project
                if ((old.speakers != project.speakers or
                     (old.calibration_enabled and old.distance_compensation != project.distance_compensation))
                     and not self.mixer.master_mute):
                    raise ValueError("MAIN MUTE first before changing stage geometry/routing or calibrated output settings")

    def skip(self) -> dict:
        with self.lock:
            if self.mixer is None or self.project_id is None:
                raise ValueError("No project armed")
            project = self.store.get(self.project_id)
            self.next_index = min(len(project.cues), self.next_index + 1)
            self.log("operator_skip", next_index=self.next_index)
            return self.status()

    def status(self) -> dict:
        with self.lock:
            if self.mixer:
                for audio_event in self.mixer.drain_events():
                    self.log(audio_event.pop("event"), **audio_event)
            mix = self.mixer.status() if self.mixer else None
            return {
                "project_id": self.project_id,
                "next_index": self.next_index,
                "output_device": self.output_device,
                "connected": self.stream is not None and self.stream.active,
                "error": self.audio_error,
                "xruns": self.xruns,
                "measurement_active": self.measurement_active,
                "mixer": mix,
            }
