"""Silent output adapter: consumes the production mixer, never opens hardware."""
from io import BytesIO
from threading import Event, Lock, Thread
from time import monotonic

import soundfile as sf
import numpy as np

from .mixer import SAMPLE_RATE


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
            mono = np.sum(block * weights, axis=1) * 0.025  # <= 0.1 full-scale sum
            outdata[:] = mono[:, None]
        except Exception as exc:
            outdata[:] = 0
            self.stage.audio_error = f"Stereo monitor error: {exc}; reconnect required"
            self.stage.mixer.panic()

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
        result.update(hardware_output=True, stereo_monitor=True, monitor_gains=self.gains.tolist())
        return result
