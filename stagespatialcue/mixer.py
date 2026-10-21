"""SpatialStage 4-channel reference mixer (48 kHz shared sample clock).

Rehearsal prototype only. NumPy allocation and RLock in PortAudio callback are NOT
hard real-time safe. A native JUCE/CoreAudio engine is planned for production.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Optional

import numpy as np

from .models import Cue, Project
from .spatial import cue_direction_offsets, envelope_offsets, vbap_gains, wrap_deg

SAMPLE_RATE = 48_000
DECLICK_S = 0.005
SMOOTH_S = 0.015


@dataclass
class Voice:
    cue: Cue
    samples: np.ndarray
    start_frame: int
    test_channel: Optional[int] = None
    stop_frame: Optional[int] = None
    stop_fade_frames: int = 0
    start_fade_frames: Optional[int] = None
    last_gains: Optional[np.ndarray] = None
    last_level: Optional[float] = None

    @property
    def end_frame(self) -> int:
        natural = self.start_frame + len(self.samples)
        if self.stop_frame is None:
            return natural
        if self.stop_frame <= self.start_frame:
            return self.start_frame
        return min(natural, self.stop_frame + self.stop_fade_frames)


class Mixer:
    def __init__(self, project: Project, sample_rate: int = SAMPLE_RATE):
        self.lock = RLock()
        self.project = project
        self.sample_rate = sample_rate
        self.frame = 0
        self.show_start_frame: int | None = None
        self.voices: list[Voice] = []
        self.master_mute = True
        self.master_db = -18.0
        self._last_master_gain: float | None = None
        self.meters = [0.0] * 4
        self.peak_over_count = 0
        self.lifecycle_events = deque(maxlen=1000)  # optional diagnostics only
        self.calibration_gain_db = [0.0] * 4
        self.calibration_delay_samples = [0] * 4
        self._delay_buffers = [np.zeros(0, dtype=np.float32) for _ in range(4)]

    def set_calibration(self, gains_db: list[float], delays_ms: list[float]) -> None:
        """Only invoke after confirmed AutoCal approval, while safe/muted.

        Gain is attenuation-only. Channel delays are bounded by 30 ms.
        Buffered audio is cleared when the calibration values change.
        """
        with self.lock:
            if len(gains_db) != 4 or len(delays_ms) != 4:
                raise ValueError("Calibration must have exactly four outputs")
            if any(not np.isfinite(x) or not -12 <= x <= 0 for x in gains_db):
                raise ValueError("AutoCal gain is limited to -12..0 dB")
            if any(not np.isfinite(x) or not 0 <= x <= 30 for x in delays_ms):
                raise ValueError("AutoCal delay is limited to 0..30 ms")
            frames = [int(round(ms * self.sample_rate / 1000)) for ms in delays_ms]
            if list(gains_db) != self.calibration_gain_db or frames != self.calibration_delay_samples:
                self.calibration_gain_db = list(gains_db)
                self.calibration_delay_samples = frames
                self._delay_buffers = [np.zeros(n, dtype=np.float32) for n in frames]

    def _calibrated_output(self, output: np.ndarray) -> None:
        """In-place 4-channel gain and causal delay, continuous across blocks."""
        for channel in range(4):
            output[:, channel] *= np.float32(10 ** (self.calibration_gain_db[channel] / 20))
            delay = self.calibration_delay_samples[channel]
            if delay:
                combined = np.concatenate((self._delay_buffers[channel], output[:, channel]))
                output[:, channel] = combined[:len(output)]
                self._delay_buffers[channel] = combined[-delay:].copy()

    def update_project(self, project: Project) -> None:
        """Live direction/gain/envelope edits apply to PLAYING and queued voices.

        Audio sample buffers, scheduling, and already chosen fade-out boundaries
        stay fixed. Replacing the media file affects the next fresh playback.
        """
        with self.lock:
            self.project = project
            lookup = {c.id: c for c in project.cues}
            for voice in self.voices:
                fresh = lookup.get(voice.cue.id)
                if fresh is not None and voice.test_channel is None:
                    voice.cue = fresh.model_copy(deep=True)

    def reset_show_clock(self) -> None:
        with self.lock:
            if self.voices:
                raise ValueError("STOP active cues before restarting the global show envelope")
            self.show_start_frame = None

    def queue(self, cue: Cue, samples: np.ndarray, *, anchored_frame: int | None = None,
              force_cut: bool = False) -> Voice:
        """Queue a voice; CUT GO overrides start behavior and all pre-waits.

        FADE GO honors replace/layer/queue and the cue's configured transition.
        CUT GO kills existing voices with a 5ms de-click (not digital hard cut).
        """
        with self.lock:
            now = max(self.frame, anchored_frame if anchored_frame is not None else self.frame)
            mode = 'replace' if force_cut else cue.start_mode
            if mode == 'queue':
                now = max([now] + [v.end_frame for v in self.voices])
            start = now if force_cut else now + int(round(cue.pre_wait_s * self.sample_rate))
            fade_override = None
            if mode == 'replace':
                transition_s = DECLICK_S if (force_cut or cue.replace_style == 'cut') else cue.transition_s
                transition_frames = max(1, round(transition_s * self.sample_rate))
                had_active_replacement = False
                for voice in self.voices:
                    if voice.end_frame <= start:
                        continue
                    if voice.start_frame >= start:  # pending sound cancelled
                        voice.stop_frame = start
                        voice.stop_fade_frames = 0
                    else:
                        had_active_replacement = True
                        voice.stop_frame = start
                        voice.stop_fade_frames = transition_frames
                if force_cut or cue.replace_style == 'cut':
                    fade_override = max(1, round(DECLICK_S * self.sample_rate))
                elif had_active_replacement and transition_s:
                    # Long transitions on short FX would hide the whole sound.
                    fade_override = min(round(transition_s * self.sample_rate),
                                        max(1, len(samples) // 2))
            voice = Voice(cue=cue.model_copy(deep=True), samples=samples,
                          start_frame=start, start_fade_frames=fade_override)
            self.voices.append(voice)
            if self.show_start_frame is None:
                self.show_start_frame = start
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

    def stop_all(self, fade_s: float = 0.04) -> None:
        with self.lock:
            fade_frames = max(1, round(max(DECLICK_S, fade_s) * self.sample_rate))
            for voice in self.voices:
                if voice.start_frame >= self.frame:
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
            self._last_master_gain = None

    def render(self, frames: int) -> np.ndarray:
        if frames <= 0:
            return np.zeros((0,4), dtype=np.float32)
        with self.lock:
            out = np.zeros((frames,4),dtype=np.float32)
            index = self.frame + np.arange(frames,dtype=np.int64)
            global_offsets = np.zeros(frames, dtype=np.float64)
            if self.project.global_envelope_enabled and self.show_start_frame is not None:
                show_t = np.maximum(0,index-self.show_start_frame)/self.sample_rate
                global_offsets = envelope_offsets(show_t, self.project.global_modulation)
            for voice in self.voices:
                if voice.end_frame > voice.start_frame and self.frame <= voice.start_frame < self.frame+frames:
                    self.lifecycle_events.append({'event':'cue_audio_start','cue_id':voice.cue.id,'frame':voice.start_frame})
                if self.frame < voice.end_frame <= self.frame + frames:
                    self.lifecycle_events.append({'event':'cue_audio_end','cue_id':voice.cue.id,'frame':voice.end_frame})
                rel = index - voice.start_frame
                valid = (rel >= 0) & (rel < len(voice.samples))
                if voice.stop_frame is not None:
                    valid &= index < voice.stop_frame + voice.stop_fade_frames
                if not np.any(valid):
                    continue
                positions = rel[valid]
                seconds = positions / self.sample_rate
                samples = voice.samples[positions].astype(np.float32,copy=True)
                cue = voice.cue
                fadein = int(round(cue.fade_in_s * self.sample_rate))
                if voice.start_fade_frames is not None:
                    fadein = max(fadein,voice.start_fade_frames)
                fadeout = int(round(cue.fade_out_s * self.sample_rate))
                if fadein:
                    samples *= np.sin(0.5*np.pi*np.minimum(1,positions/fadein)).astype(np.float32)
                if fadeout:
                    remaining = len(voice.samples)-positions-1
                    samples *= np.sin(0.5*np.pi*np.minimum(1,remaining/fadeout)).astype(np.float32)
                if voice.stop_frame is not None and voice.stop_fade_frames:
                    remaining_stop = voice.stop_frame + voice.stop_fade_frames - index[valid]
                    samples *= np.minimum(1,remaining_stop/voice.stop_fade_frames).astype(np.float32)
                target_level = float(10**(cue.gain_db/20))
                if voice.last_level is not None and not np.isclose(target_level,voice.last_level):
                    n=min(len(samples),max(1,round(SMOOTH_S*self.sample_rate)))
                    volume=np.full(len(samples),target_level,dtype=np.float32)
                    volume[:n]=np.linspace(voice.last_level,target_level,n,dtype=np.float32)
                    samples *= volume
                else:
                    samples *= np.float32(target_level)
                voice.last_level = target_level
                if voice.test_channel is not None:
                    out[valid,voice.test_channel-1] += samples
                else:
                    angles=(cue.position_deg + self.project.global_rotation_deg
                            + cue_direction_offsets(seconds,len(voice.samples)/self.sample_rate,cue)
                            + global_offsets[valid])
                    gains=vbap_gains(angles,self.project.speakers,
                                     distance_compensation=self.project.distance_compensation)
                    if voice.last_gains is not None and gains.shape[0]:
                        n=min(len(gains),max(1,round(SMOOTH_S*self.sample_rate)))
                        blend=np.linspace(0,1,n,dtype=np.float32)[:,None]
                        gains[:n]=voice.last_gains[None,:]*(1-blend)+gains[:n]*blend
                    voice.last_gains=gains[-1,:].copy()
                    out[valid] += samples[:,None]*gains
            target_master=float(10**(self.master_db/20))
            if self._last_master_gain is not None and not np.isclose(target_master,self._last_master_gain):
                n=min(frames,max(1,round(SMOOTH_S*self.sample_rate)))
                gain=np.full(frames,target_master,dtype=np.float32)
                gain[:n]=np.linspace(self._last_master_gain,target_master,n,dtype=np.float32)
                out *= gain[:,None]
            else:
                out *= np.float32(target_master)
            self._last_master_gain=target_master
            if self.master_mute:
                out.fill(0)
                # Never emit a previously buffered delayed sample after unmute.
                for buffer in self._delay_buffers:
                    buffer.fill(0)
            else:
                self._calibrated_output(out)
            if np.max(np.abs(out)) > 1.0:
                self.peak_over_count+=1
            np.clip(out,-1,1,out=out)
            self.meters=np.max(np.abs(out),axis=0).tolist()
            self.frame+=frames
            self.voices=[v for v in self.voices if v.end_frame > self.frame]
            return out

    def drain_events(self) -> list[dict]:
        with self.lock:
            result=list(self.lifecycle_events)
            self.lifecycle_events.clear()
            return result

    def status(self) -> dict:
        with self.lock:
            elapsed=0 if self.show_start_frame is None else max(0,self.frame-self.show_start_frame)/self.sample_rate
            return {'frame':self.frame,'seconds':round(self.frame/self.sample_rate,3),
                    'show_elapsed_s':round(elapsed,3),
                    'master_mute':self.master_mute,'master_db':self.master_db,
                    'meters':self.meters[:],'peak_over_count':self.peak_over_count,
                    'autocal_enabled':self.project.calibration_enabled,
                    'autocal_gain_db':self.calibration_gain_db[:],
                    'autocal_delay_ms':[round(1000*x/self.sample_rate,3) for x in self.calibration_delay_samples],
                    'voices':[{'cue_id':v.cue.id,'title':v.cue.title,
                               'state':'queued' if v.start_frame>self.frame else 'playing',
                               'elapsed_s':round(max(0,self.frame-v.start_frame)/self.sample_rate,2),
                               'duration_s':round(len(v.samples)/self.sample_rate,2),
                               'end_s':round(v.end_frame/self.sample_rate,2),
                               'position_deg':round(float(wrap_deg(v.cue.position_deg+self.project.global_rotation_deg)),2)}
                              for v in self.voices if v.end_frame>self.frame]}
