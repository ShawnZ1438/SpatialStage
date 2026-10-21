"""Operator-initiated, single-position four-channel acoustic measurements.

This is NOT Audyssey MultEQ: no room-wide correction, SPL certification or EQ.
Only a short, low-level synchronous four-output/XLR-input sweep is recorded.
Raw microphone captures stay in memory; compact acoustic summaries are persisted.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock, Thread
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, Field, field_validator
from scipy.signal import chirp, correlate, correlation_lags

from .mixer import SAMPLE_RATE
from .models import Speaker
from .storage import ProjectStore

SWEEP_SECONDS = 0.85
LEAD_SECONDS = 0.25
TAIL_SECONDS = 0.6
MAX_DELAY_MS = 30.0
MIN_SNR_DB = 12.0
BAND_FREQUENCIES = [125, 250, 500, 1000, 2000, 4000, 8000]


class AutoCalConfig(BaseModel):
    """Locked v0.3 rehearsal scope. Hardware may be selected at measurement time."""

    measurement_points: int = 1
    optimization: str = "balanced"
    microphone_type: str = "xlr"
    experimental_eq: bool = False
    input_device_index: int | None = Field(default=None, ge=0)
    input_channel: int = Field(default=1, ge=1, le=16)
    output_device_index: int | None = Field(default=None, ge=0)
    stimulus_dbfs: float = Field(default=-30.0, ge=-36.0, le=-24.0)

    @field_validator("measurement_points")
    @classmethod
    def one_point(cls, value):
        if value != 1:
            raise ValueError("v0.3 AutoCal is limited to one stage-center measurement point")
        return value

    @field_validator("optimization")
    @classmethod
    def balanced(cls, value):
        if value != "balanced":
            raise ValueError("This AutoCal release only supports balanced optimization")
        return value

    @field_validator("microphone_type")
    @classmethod
    def xlr_only(cls, value):
        if value != "xlr":
            raise ValueError("This AutoCal release requires an XLR microphone via an input interface")
        return value

    @field_validator("experimental_eq")
    @classmethod
    def no_eq(cls, value):
        if value:
            raise ValueError("Experimental EQ is disabled for this release")
        return value


def geometry_signature(speakers: list[Speaker]) -> str:
    """Attach every measurement to exact stage geometry, trims, and routing."""
    entries = [s.model_dump(mode="json") for s in speakers]
    raw = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_stimulus(level_dbfs: float = -30.0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    duration = int(SWEEP_SECONDS * sample_rate)
    t = np.arange(duration, dtype=np.float64) / sample_rate
    sweep = chirp(t, f0=200, f1=min(8500, sample_rate * .42), t1=SWEEP_SECONDS, method="logarithmic")
    taper = max(1, int(.045 * sample_rate))
    envelope = np.ones(duration, dtype=np.float64)
    fade = np.sin(np.linspace(0, np.pi / 2, taper)) ** 2
    envelope[:taper] = fade
    envelope[-taper:] = fade[::-1]
    signal = (sweep * envelope * 10 ** (level_dbfs / 20)).astype(np.float32)
    return np.pad(signal, (int(LEAD_SECONDS * sample_rate), int(TAIL_SECONDS * sample_rate)))


def capture_xlr(output: np.ndarray, config: AutoCalConfig, sample_rate: int) -> np.ndarray:
    """Full-duplex PortAudio capture. Same clocked interface is strongly preferred.

    Different physical devices are allowed for compatibility, but their independent
    clocks may make timing estimates unreliable; the operator must validate them.
    """
    import sounddevice as sd

    if config.input_device_index is None or config.output_device_index is None:
        raise ValueError("Choose an XLR input interface and four-channel output interface")
    sd.check_input_settings(device=config.input_device_index, channels=config.input_channel,
                            samplerate=sample_rate, dtype="float32")
    sd.check_output_settings(device=config.output_device_index, channels=4,
                             samplerate=sample_rate, dtype="float32")
    try:
        recorded = sd.playrec(
            output, samplerate=sample_rate, channels=config.input_channel,
            device=(config.input_device_index, config.output_device_index),
            dtype="float32", blocking=True, latency="high",
        )
        return np.asarray(recorded[:, config.input_channel - 1], dtype=np.float64).copy()
    finally:
        sd.stop()


def analyze_channel(reference: np.ndarray, recorded: np.ndarray,
                    channel: int, sample_rate: int = SAMPLE_RATE) -> dict:
    """Estimate relative arrival and response; NOT calibrated absolute dB SPL.

    The cross-correlation peak includes interface playback+record latency. Across
    four sequential captures on the same clock, DIFFERENCES are more meaningful.
    """
    x = np.asarray(reference, dtype=np.float64).reshape(-1)
    y = np.asarray(recorded, dtype=np.float64).reshape(-1)
    if len(y) != len(x) or len(y) < sample_rate or not np.all(np.isfinite(y)):
        raise ValueError("Capture length mismatch, invalid samples, or too-short capture")
    c = correlate(y, x, mode="full", method="fft")
    lags = correlation_lags(len(y), len(x), mode="full")
    allowed = np.flatnonzero((lags >= 0) & (lags <= int(.25 * sample_rate)))
    best = int(allowed[np.argmax(np.abs(c[allowed]))])
    lag = int(lags[best])
    peak = float(np.max(np.abs(y)))
    quiet = y[:int(.18 * sample_rate)]
    noise = float(np.sqrt(np.mean(quiet * quiet)))
    onset = int(LEAD_SECONDS * sample_rate) + lag
    duration = int(SWEEP_SECONDS * sample_rate)
    signal = y[onset:min(len(y), onset + duration)]
    signal_rms = float(np.sqrt(np.mean(signal * signal))) if len(signal) else 0.0
    signal_dbfs = 20 * np.log10(max(1e-12, signal_rms))
    snr_db = 20 * np.log10(max(1e-12, signal_rms) / max(1e-12, noise))

    # Regularized impulse estimate; window only the early response for a compact
    # diagnostic spectrum. Frequencies are normalized to 1 kHz, not auto-EQ.
    X = np.fft.rfft(x)
    Y = np.fft.rfft(y)
    strength = np.abs(X) ** 2
    H = Y * np.conj(X) / (strength + max(1e-12, float(np.max(strength)) * 1e-5))
    impulse = np.fft.irfft(H, n=len(x))
    ir_window = impulse[lag:min(len(impulse), lag + int(.100 * sample_rate))].copy()
    ir_display = impulse[max(0, lag - 48):min(len(impulse), lag + 480)]
    if len(ir_window) > 1:
        ir_window *= np.linspace(1, 0, len(ir_window)) ** .25
    spec = np.abs(np.fft.rfft(ir_window, n=16384))
    freqs = np.fft.rfftfreq(16384, 1 / sample_rate)
    band_levels = []
    for f in BAND_FREQUENCIES:
        selected = spec[(freqs >= f / 2**(1/6)) & (freqs <= f * 2**(1/6))]
        band_levels.append(20 * np.log10(max(1e-12, float(np.mean(selected)) if len(selected) else 1e-12)))
    pivot = band_levels[BAND_FREQUENCIES.index(1000)]
    spectral_db = [round(float(np.clip(level - pivot, -36, 36)), 1) for level in band_levels]
    # Avoid exporting raw microphone sound; these are just a few deconvolved
    # correlation points for the UI diagnostic impulse plot.
    scale = float(np.max(np.abs(ir_display))) if len(ir_display) else 1.0
    preview = [round(float(a / max(scale, 1e-12)), 3)
               for a in ir_display[::max(1, len(ir_display) // 80)][:90]]
    warnings = []
    if peak >= .97:
        warnings.append("XLR input clipping: lower preamp gain and repeat")
    if signal_dbfs < -65:
        warnings.append("Very weak microphone signal: inspect XLR input, gain and routing")
    if snr_db < MIN_SNR_DB:
        warnings.append("Low measurement SNR: check quiet stage and microphone placement")
    if lag >= .2 * sample_rate:
        warnings.append("Large capture latency: verify clocks and interface routing")
    return {
        "channel": channel, "arrival_samples": lag,
        "arrival_ms": round(1000 * lag / sample_rate, 3),
        "relative_input_dbfs": round(float(signal_dbfs), 2),
        "snr_db": round(float(snr_db), 1),
        "input_peak_dbfs": round(float(20 * np.log10(max(peak, 1e-12))), 1),
        "passed": not warnings, "warnings": warnings,
        "frequency_hz": BAND_FREQUENCIES,
        "frequency_db_relative_to_1khz": spectral_db,
        "impulse_preview_normalized": preview,
    }


def recommendations(results: list[dict]) -> dict:
    if sorted(x["channel"] for x in results) != [1, 2, 3, 4]:
        raise ValueError("A measurement is required for each of CH1, CH2, CH3, CH4")
    ordered = sorted(results, key=lambda x: x["channel"])
    levels = [x["relative_input_dbfs"] for x in ordered]
    arrivals = [x["arrival_samples"] for x in ordered]
    quietest = min(levels)
    extra_delay_ms = [(max(arrivals) - v) / SAMPLE_RATE * 1000 for v in arrivals]
    differences = [quietest - v for v in levels]
    warnings = []
    if max(extra_delay_ms) > MAX_DELAY_MS:
        warnings.append(f"Delay variation exceeds {MAX_DELAY_MS:g} ms safety cap")
    if min(differences) < -12:
        warnings.append("Input level imbalance exceeds 12 dB: check gain and remeasure")
    return {
        "channel_gain_db": [round(max(-12, min(0, x)), 2) for x in differences],
        "channel_delay_ms": [round(max(0, x), 3) for x in extra_delay_ms],
        "quality_ok": all(x["passed"] for x in ordered) and not warnings,
        "warnings": warnings,
        "method": "Attenuation-only level match to quietest measured output; relative arrival delay only; EQ OFF",
        "limitation": "One measurement point; 'balanced' reduces to stage-center matching, not area optimization."
    }


class AutoCalManager:
    def __init__(self, store: ProjectStore, stage, capture=None):
        self.store = store
        self.stage = stage
        self.capture = capture or capture_xlr
        self.lock = RLock()
        self._status: dict = {"state": "idle", "channel": None, "message": "Not started", "session_id": None}

    def _folder(self, project_id: str) -> Path:
        folder = self.store.directory(project_id) / "autocal"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _atomic_json(self, path: Path, value: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".autocal-", dir=path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def config(self, project_id: str) -> AutoCalConfig:
        path = self._folder(project_id) / "config.json"
        return AutoCalConfig.model_validate_json(path.read_text()) if path.is_file() else AutoCalConfig()

    def save_config(self, project_id: str, config: AutoCalConfig) -> AutoCalConfig:
        self.store.get(project_id)
        with self.lock:
            if self._status["state"] == "running":
                raise ValueError("Cannot change AutoCal setup during a measurement")
            self._atomic_json(self._folder(project_id) / "config.json", config.model_dump(mode="json"))
        return config

    def session(self, project_id: str, session_id: str) -> dict:
        if len(session_id) != 16 or not all(c in "0123456789abcdef" for c in session_id):
            raise ValueError("Invalid calibration session ID")
        path = self._folder(project_id) / f"{session_id}.json"
        if not path.is_file():
            raise FileNotFoundError("AutoCal session not found")
        return json.loads(path.read_text())

    def sessions(self, project_id: str) -> list[dict]:
        self.store.get(project_id)
        records = []
        for path in self._folder(project_id).glob("[a-f0-9]*.json"):
            if len(path.stem) != 16:
                continue
            try:
                item = self.session(project_id, path.stem)
                records.append({k: item.get(k) for k in ("id", "created_at", "status", "quality_ok")})
            except (OSError, ValueError):
                pass
        return sorted(records, key=lambda x: x["created_at"], reverse=True)[:40]

    def status(self, project_id: str) -> dict:
        with self.lock:
            if self._status.get("project_id") != project_id:
                return {"state": "idle", "channel": None, "message": "Not running", "session_id": None}
            return self._status.copy()

    def _update(self, **fields):
        with self.lock:
            self._status.update(fields)

    def start(self, project_id: str, *, hardware_ready: bool) -> dict:
        if not hardware_ready:
            raise ValueError("Confirm that the stage is empty and analogue output level is low")
        project = self.store.get(project_id)
        config = self.config(project_id)
        if project.distance_compensation:
            raise ValueError("Disable geometric distance compensation before AutoCal (avoid double correction)")
        if any(abs(s.trim_db) > 1e-8 for s in project.speakers):
            raise ValueError("Set all four manual speaker trims to 0 dB before AutoCal (avoid double correction)")
        if config.input_device_index is None or config.output_device_index is None:
            raise ValueError("Select XLR input and 4-channel output in AutoCal settings")
        import sounddevice as sd
        input_info = sd.query_devices(config.input_device_index)
        output_info = sd.query_devices(config.output_device_index)
        if config.input_channel > input_info["max_input_channels"]:
            raise ValueError("XLR microphone input channel not found on selected device")
        if output_info["max_output_channels"] < 4:
            raise ValueError("AutoCal requires at least four independent output channels")
        with self.lock, self.stage.lock:
            if self._status["state"] == "running" or self.stage.measurement_active:
                raise ValueError("An AutoCal measurement is already in progress")
            if self.stage.stream is not None or self.stage.mixer and self.stage.mixer.voices:
                raise ValueError("Disconnect performance output and STOP all cues before calibration")
            if self.stage.mixer and not self.stage.mixer.master_mute:
                raise ValueError("MAIN MUTE must be ON before starting AutoCal")
            self.stage.measurement_active = True
            session_id = uuid4().hex[:16]
            self._status = {"state": "running", "project_id": project_id,
                            "channel": 0, "message": "Preparing XLR sweep", "session_id": session_id}
        thread = Thread(target=self._measure, args=(project, config, session_id,
                        str(input_info["name"]), str(output_info["name"])), daemon=True,
                        name=f"AutoCal-{session_id}")
        thread.start()
        return self.status(project_id)

    def _measure(self, project, config, session_id, mic_name, output_name):
        try:
            reference = make_stimulus(config.stimulus_dbfs)
            results = []
            for channel in range(1, 5):
                self._update(channel=channel, message=f"Measuring CH {channel} of 4")
                signal = np.zeros((len(reference), 4), dtype=np.float32)
                signal[:, channel - 1] = reference
                recording = self.capture(signal, config, SAMPLE_RATE)
                result = analyze_channel(reference, recording, channel)
                results.append(result)
            profile = recommendations(results)
            created_at = datetime.now(timezone.utc).isoformat()
            summary = {
                "schema_version": 1, "id": session_id, "created_at": created_at,
                "project_id": project.id, "status": "review_required",
                "quality_ok": profile["quality_ok"],
                "configuration": config.model_dump(mode="json"),
                "input_device_name": mic_name, "output_device_name": output_name,
                "speaker_signature": geometry_signature(project.speakers),
                "speakers": [s.model_dump(mode="json") for s in project.speakers],
                "measurement_point": {"x_m": 0.0, "y_m": 0.0, "name": "stage center"},
                "results": results, "recommendations": profile,
                "warning": "No acoustic SPL calibration, area optimization, or EQ. "
                           "Mic gain must remain constant for all four captures. "
                           "Interface latency is included in absolute arrival; ONLY differences are used.",
            }
            self._atomic_json(self._folder(project.id) / f"{session_id}.json", summary)
            self._update(state="completed", channel=4, message="Four measurements saved; review required")
        except Exception as exc:
            self._update(state="failed", message=str(exc))
        finally:
            with self.stage.lock:
                self.stage.measurement_active = False

    def apply(self, project_id: str, session_id: str, *, confirm: str) -> dict:
        if confirm != "APPLY":
            raise ValueError("Type APPLY to explicitly confirm compensation")
        data = self.session(project_id, session_id)
        project = self.store.get(project_id)
        with self.lock, self.stage.lock:
            if self.stage.measurement_active or self._status["state"] == "running":
                raise ValueError("Cannot apply calibration during active measurement")
            if self.stage.stream is not None or self.stage.mixer and self.stage.mixer.voices:
                raise ValueError("Disconnect live audio and stop all cues before applying compensation")
            if self.stage.mixer and not self.stage.mixer.master_mute:
                raise ValueError("MAIN MUTE must be ON to apply compensation")
            if not data.get("quality_ok") or data.get("status") != "review_required":
                raise ValueError("All four measurements must pass; only pending sessions may be applied")
            if data["speaker_signature"] != geometry_signature(project.speakers):
                raise ValueError("Stage routing/geometry has changed; remeasure before applying")
            if project.distance_compensation or any(abs(s.trim_db) > 1e-8 for s in project.speakers):
                raise ValueError("Disable geometric distance compensation and set manual trims to zero")
            if any(not x.get("passed") for x in data["results"]):
                raise ValueError("A channel failed quality checks")
            project.active_calibration_id = session_id
            project.calibration_enabled = True
            self.store.save(project)
            data["status"] = "applied"
            data["applied_at"] = datetime.now(timezone.utc).isoformat()
            self._atomic_json(self._folder(project_id) / f"{session_id}.json", data)
            self.stage.sync(project)
        return {"project": project, "session": data}

    def disable(self, project_id: str) -> dict:
        project = self.store.get(project_id)
        with self.stage.lock:
            if self.stage.stream is not None or self.stage.mixer and self.stage.mixer.voices:
                raise ValueError("Disconnect live output / stop cues before disabling calibration")
            if self.stage.mixer and not self.stage.mixer.master_mute:
                raise ValueError("MAIN MUTE must be ON to disable calibration")
            project.calibration_enabled = False
            project.active_calibration_id = None
            self.store.save(project)
            self.stage.sync(project)
        return {"project": project}
