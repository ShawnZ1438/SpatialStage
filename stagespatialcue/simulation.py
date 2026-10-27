"""Silent output adapter: consumes the production mixer, never opens hardware."""
from io import BytesIO
from threading import Event, Lock, Thread
from time import monotonic

import soundfile as sf
import numpy as np
from scipy.signal import lfilter

from .mixer import SAMPLE_RATE
from .spatial import SPEED_OF_SOUND_M_S, xy_from_polar

HEAD_RADIUS_M = 0.0875
VIRTUAL_MONITOR_GAIN = 0.1  # -20 dB: +6 dB monitor-only, never changes CH1-4
MONO_MONITOR_GAIN = 0.05  # -26 dB per channel


class VirtualRoom:
    """Headphone preview of the four real loudspeakers heard from a listener pose.

    Per speaker: 1/r level and r/c arrival (relative, so the centre pose equals the
    console-levelled venue), a spherical-head time difference, a broadband level
    difference, a one-pole head-shadow low-pass on the far ear and mild darkening
    for speakers behind the head. Approximate: no HRTF, reflections or SPL.
    """
    max_delay = int(0.06 * SAMPLE_RATE)

    def __init__(self, speakers, pose=(0.0, 0.0, 0.0)):
        self.history = np.zeros((self.max_delay, 4), dtype=np.float32)
        self.zi = np.zeros((4, 2, 1))
        self.speakers, self.pose = list(speakers), tuple(pose)
        self.params = self._configure()

    def update(self, speakers=None, pose=None):
        if speakers is not None:
            self.speakers = list(speakers)
        if pose is not None:
            self.pose = tuple(pose)
        self.params = self._configure()  # one assignment: safe against the audio thread

    def _configure(self):
        x0, y0, head = self.pose
        rows = []
        for s in self.speakers:
            sx, sy = xy_from_polar(s.angle_deg, s.distance_m)
            dx, dy = sx - x0, sy - y0
            r = max(0.3, float(np.hypot(dx, dy)))
            az = np.deg2rad(np.rad2deg(np.arctan2(dx, dy)) - head)  # 0 = ahead, + = right
            lateral = float(np.sin(az))
            theta = np.arcsin(abs(lateral))
            itd = round(HEAD_RADIUS_M / SPEED_OF_SOUND_M_S * (theta + np.sin(theta)) * SAMPLE_RATE)
            behind = max(0.0, -float(np.cos(az)))
            ears = []
            for side in (-1, 1):  # left, right
                near = side * lateral >= 0
                pan = 0.5 + 0.3 * lateral
                ear_gain = np.sqrt(pan if side > 0 else 1 - pan)
                cutoff = 20000 - 14000 * behind - (0 if near else 16000 * abs(lateral))
                coef = float(np.exp(-2 * np.pi * max(1200, cutoff) / SAMPLE_RATE)) if cutoff < 19000 else 0.0
                ears.append((0 if near else itd, ear_gain, coef))
            rows.append((s.output_channel - 1, s.distance_m / r, r, ears))
        nearest = min(row[2] for row in rows)
        return [(ch, gain, min(self.max_delay - 64, round((r - nearest) / SPEED_OF_SOUND_M_S * SAMPLE_RATE)), ears)
                for ch, gain, r, ears in rows]

    def process(self, block: np.ndarray) -> np.ndarray:
        frames = len(block)
        H = self.max_delay
        buffer = np.concatenate([self.history, block.astype(np.float32)])
        out = np.zeros((frames, 2), dtype=np.float32)
        for i, (ch, gain, delay, ears) in enumerate(self.params):
            for ear, (itd, ear_gain, coef) in enumerate(ears):
                d = min(H, delay + itd)
                segment = buffer[H - d:H - d + frames, ch]
                if coef:
                    segment, self.zi[i, ear] = lfilter([1 - coef], [1, -coef], segment, zi=self.zi[i, ear])
                out[:, ear] += segment * (gain * ear_gain)
        self.history = buffer[-H:]
        return out


class SimulationStream:
    # Bounded PCM capture: 60 seconds, four float channels (~46 MiB).
    max_frames = SAMPLE_RATE * 60

    def __init__(self, stage):
        self.stage = stage
        self.active = False
        self.done = Event()
        self.lock = Lock()
        self.blocks = []
        self.frames = 0
        self.recording = False
        self.thread = None

    def start(self):
        self.active = True
        self.thread = Thread(target=self._run, daemon=True, name="spatialstage-simulation")
        self.thread.start()

    def _run(self):
        deadline = monotonic()
        try:
            while not self.done.is_set():
                self.step(512)
                deadline += 512 / SAMPLE_RATE
                # No catch-up bursts after OS stalls; this is not a driver latency test.
                if deadline < monotonic():
                    deadline = monotonic()
                self.done.wait(max(0, deadline - monotonic()))
        except Exception as exc:
            self.stage.audio_error = f"Simulation stopped: {exc}"
            self.stage.mixer.panic()
        finally:
            self.active = False

    def step(self, frames):
        block = self.stage.mixer.render(frames)
        with self.lock:
            if self.recording:
                count = min(len(block), self.max_frames - self.frames)
                self.blocks.append(block[:count].copy())
                self.frames += count
                if self.frames >= self.max_frames:
                    self.recording = False
        return block

    def capture(self, recording):
        with self.lock:
            if recording:
                self.blocks.clear()
                self.frames = 0
            self.recording = recording

    def wav(self):
        with self.lock:
            if self.recording:
                raise ValueError("Stop capture before downloading")
            if not self.frames:
                raise ValueError("Capture is empty")
            blocks = self.blocks[:]
        result = BytesIO()
        with sf.SoundFile(result, mode="w", samplerate=SAMPLE_RATE,
                          channels=4, format="WAV", subtype="FLOAT") as audio:
            for block in blocks:
                audio.write(block)
        return result.getvalue()

    def status(self):
        with self.lock:
            return {"recording": self.recording, "captured_seconds": self.frames / SAMPLE_RATE,
                    "limit_seconds": 60, "hardware_output": False}

    def stop(self):
        self.done.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.active = False

    def close(self):
        self.stop()


class StereoMonitorStream(SimulationStream):
    """Real four-channel render with a conservative mono sum duplicated to L/R."""
    def __init__(self, stage, device):
        super().__init__(stage)
        import sounddevice as sd
        self.gains = np.ones(4, dtype=np.float32)
        self.previous_gains = np.zeros(4, dtype=np.float32)
        self.monitor_peak_over_count = 0
        self.device = sd.OutputStream(device=device, samplerate=SAMPLE_RATE, channels=2,
                                      dtype="float32", blocksize=512, callback=self.callback,
                                      finished_callback=self.finished)

    def callback(self, outdata, frames, time_info, status):
        try:
            if status:
                self.stage.xruns += 1
            block = self.step(frames)
            # Smooth monitor-only edits, leaving captured four-channel PCM unchanged.
            target = self.gains.copy()
            weights = np.linspace(self.previous_gains, target, frames, dtype=np.float32)
            self.previous_gains = target
            mono = np.sum(block * weights, axis=1) * MONO_MONITOR_GAIN
            outdata[:] = self.limit_monitor(mono[:, None])
        except Exception as exc:
            outdata[:] = 0
            self.stage.audio_error = f"Stereo monitor error: {exc}; reconnect required"
            self.stage.mixer.panic()

    def limit_monitor(self, signal):
        if np.max(np.abs(signal), initial=0) > 0.98:
            self.monitor_peak_over_count = getattr(self, 'monitor_peak_over_count', 0) + 1
        return np.clip(signal, -0.98, 0.98)

    def finished(self):
        self.active = False

    def start(self):
        self.device.start()
        self.active = True

    def stop(self):
        self.device.stop()
        self.active = False

    def close(self):
        self.device.close()

    def status(self):
        result = super().status()
        result.update(hardware_output=True, stereo_monitor=True, monitor_gains=self.gains.tolist(),
                      monitor_mode="sum", monitor_peak_over_count=getattr(self, "monitor_peak_over_count", 0))
        return result


class VirtualMonitorStream(StereoMonitorStream):
    """Headphones hear the real CH1-4 output as four virtual speakers (VirtualRoom)."""
    def __init__(self, stage, device, pose=(0.0, 0.0, 0.0)):
        super().__init__(stage, device)
        self.room = VirtualRoom(stage.mixer.project.speakers, pose)
        self._geometry = None

    def callback(self, outdata, frames, time_info, status):
        try:
            if status:
                self.stage.xruns += 1
            block = self.step(frames)
            speakers = self.stage.mixer.project.speakers
            geometry = tuple((s.angle_deg, s.distance_m, s.output_channel) for s in speakers)
            if geometry != self._geometry:
                self._geometry = geometry
                self.room.update(speakers=speakers)
            target = self.gains.copy()
            weights = np.linspace(self.previous_gains, target, frames, dtype=np.float32)
            self.previous_gains = target
            outdata[:] = self.limit_monitor(self.room.process(block * weights) * VIRTUAL_MONITOR_GAIN)
        except Exception as exc:
            outdata[:] = 0
            self.stage.audio_error = f"Virtual monitor error: {exc}; reconnect required"
            self.stage.mixer.panic()

    def status(self):
        result = super().status()
        x, y, head = self.room.pose
        result.update(monitor_mode="virtual", pose={"x_m": x, "y_m": y, "head_deg": head})
        return result
