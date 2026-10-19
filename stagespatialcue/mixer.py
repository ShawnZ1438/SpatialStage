"""Reference 4-channel software mixer, shared 48 kHz sample clock.

The whole render operation runs in a Python PortAudio callback. This is a
rehearsal prototype, NOT a hard-real-time implementation or show-safe engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from threading import RLock
from typing import Optional

import numpy as np

from .models import Cue, Project
from .spatial import envelope_offsets, vbap_gains

SAMPLE_RATE = 48_000


@dataclass
class Voice:
    cue: Cue
    samples: np.ndarray
    start_frame: int
    test_channel: Optional[int] = None
    stop_frame: Optional[int] = None
    stop_fade_frames: int = 0

    @property
    def end_frame(self) -> int:
        natural = self.start_frame + len(self.samples)
        if self.stop_frame is None:
            return natural
        return min(natural, self.stop_frame + self.stop_fade_frames)


class Mixer:
    def __init__(self, project: Project, sample_rate: int = SAMPLE_RATE):
        self.lock = RLock()
        self.project = project
        self.sample_rate = sample_rate
        self.frame = 0
        self.voices: list[Voice] = []
        self.master_mute = True
        self.master_db = -18.0
        self.meters = [0.0] * 4
        self.peak_over_count = 0
        self.lifecycle_events = deque(maxlen=4000)

    def update_project(self, project: Project) -> None:
        with self.lock:
            self.project = project

    def queue(self, cue: Cue, samples: np.ndarray, *, anchored_frame: int | None = None) -> Voice:
        with self.lock:
            now = max(self.frame, anchored_frame if anchored_frame is not None else self.frame)
            pre = int(round(cue.pre_wait_s * self.sample_rate))
            if cue.start_mode == "queue":
                now = max([now] + [v.end_frame for v in self.voices])
            start = now + pre
            if cue.start_mode == "replace":
                fade_length = max(1, int(round(cue.transition_s * self.sample_rate)))
                for voice in self.voices:
                    if voice.end_frame <= start:
                        continue
                    if voice.start_frame > start:
                        # Pending cues are cancelled by replace (not silently kept).
                        voice.stop_frame = start
                        voice.stop_fade_frames = 0
                    else:
                        voice.stop_frame = start
                        voice.stop_fade_frames = fade_length
            voice = Voice(cue=cue.model_copy(deep=True), samples=samples, start_frame=start)
            self.voices.append(voice)
            return voice

    def speaker_test(self, channel: int) -> Voice:
        if not 1 <= channel <= 4:
            raise ValueError("Channel must be 1..4")
        n = int(1.0 * self.sample_rate)
        t = np.arange(n) / self.sample_rate
        data = (np.sin(2 * np.pi * 440.0 * t) * (10 ** (-22 / 20))).astype(np.float32)
        cue = Cue(title=f"Speaker test {channel}", fade_in_s=0.025, fade_out_s=0.15, gain_db=0)
        with self.lock:
            voice = Voice(cue=cue, samples=data, start_frame=self.frame, test_channel=channel)
            self.voices.append(voice)
            return voice

    def stop_all(self, fade_s: float = 0.03) -> None:
        with self.lock:
            fade_frames = max(1, int(round(max(0.005, fade_s) * self.sample_rate)))
            for voice in self.voices:
                if voice.start_frame > self.frame:
                    voice.stop_frame = self.frame
                    voice.stop_fade_frames = 0
                else:
                    voice.stop_frame = self.frame
                    voice.stop_fade_frames = fade_frames

    def panic(self) -> None:
        with self.lock:
            self.voices.clear()
            self.meters = [0.0] * 4
            self.master_mute = True

    def render(self, frames: int) -> np.ndarray:
        if frames <= 0:
            return np.zeros((0, 4), dtype=np.float32)
        with self.lock:
            out = np.zeros((frames, 4), dtype=np.float32)
            index = self.frame + np.arange(frames, dtype=np.int64)
            for voice in self.voices:
                if voice.end_frame > voice.start_frame and self.frame <= voice.start_frame < self.frame + frames:
                    self.lifecycle_events.append({"event": "cue_audio_start", "cue_id": voice.cue.id,
                                                  "cue_title": voice.cue.title, "frame": voice.start_frame})
                if self.frame < voice.end_frame <= self.frame + frames:
                    self.lifecycle_events.append({"event": "cue_audio_end", "cue_id": voice.cue.id,
                                                  "cue_title": voice.cue.title, "frame": voice.end_frame})
                relative = index - voice.start_frame
                valid = (relative >= 0) & (relative < len(voice.samples))
                if voice.stop_frame is not None:
                    valid &= index < voice.stop_frame + voice.stop_fade_frames
                if not np.any(valid):
                    continue
                positions = relative[valid]
                secs = positions / self.sample_rate
                data = voice.samples[positions].astype(np.float32, copy=True)
                cue = voice.cue
                fadein = int(round(cue.fade_in_s * self.sample_rate))
                fadeout = int(round(cue.fade_out_s * self.sample_rate))
                if fadein > 0:
                    data *= np.sin(0.5 * np.pi * np.minimum(1, positions / fadein)).astype(np.float32)
                if fadeout > 0:
                    remaining = len(voice.samples) - positions - 1
                    data *= np.sin(0.5 * np.pi * np.minimum(1, remaining / fadeout)).astype(np.float32)
                if voice.stop_frame is not None:
                    remaining_stop = voice.stop_frame + voice.stop_fade_frames - index[valid]
                    if voice.stop_fade_frames:
                        data *= np.minimum(1, remaining_stop / voice.stop_fade_frames).astype(np.float32)
                data *= np.float32(10 ** (cue.gain_db / 20))
                if voice.test_channel is not None:
                    out[valid, voice.test_channel - 1] += data
                else:
                    angles = (
                        cue.position_deg
                        + self.project.global_rotation_deg
                        + envelope_offsets(secs, cue.modulation)
                    )
                    gains = vbap_gains(
                        angles, self.project.speakers,
                        distance_compensation=self.project.distance_compensation,
                    )
                    out[valid] += data[:, None] * gains
            out *= np.float32(10 ** (self.master_db / 20))
            if self.master_mute:
                out[:] = 0
            excess = np.max(np.abs(out)) > 1.0
            if excess:
                self.peak_over_count += 1
            np.clip(out, -1, 1, out=out)
            self.meters = np.max(np.abs(out), axis=0).tolist()
            self.frame += frames
            self.voices = [v for v in self.voices if v.end_frame > self.frame]
            return out

    def drain_events(self) -> list[dict]:
        with self.lock:
            events = list(self.lifecycle_events)
            self.lifecycle_events.clear()
            return events

    def status(self) -> dict:
        with self.lock:
            return {
                "frame": self.frame,
                "seconds": round(self.frame / self.sample_rate, 2),
                "master_mute": self.master_mute,
                "master_db": self.master_db,
                "meters": self.meters[:],
                "peak_over_count": self.peak_over_count,
                "voices": [
                    {
                        "cue_id": v.cue.id,
                        "title": v.cue.title,
                        "state": "queued" if v.start_frame > self.frame else "playing",
                        "elapsed_s": round(max(0, self.frame - v.start_frame) / self.sample_rate, 2),
                        "duration_s": round(len(v.samples) / self.sample_rate, 2),
                        "end_s": round(v.end_frame / self.sample_rate, 2),
                    }
                    for v in self.voices if v.end_frame > self.frame
                ],
            }
