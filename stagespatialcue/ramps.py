"""Sample-counted ramps: duration is independent of callback block size."""
from __future__ import annotations

import numpy as np


class LinearRamp:
    def __init__(self, value: float = 0.0):
        self.value = self.target = float(value)
        self.remaining = 0
        self.step = 0.0

    def render(self, target: float, frames: int, duration: int) -> np.ndarray:
        if target != self.target:
            self.target = float(target)
            self.remaining = max(1, duration)
            self.step = (self.target - self.value) / self.remaining
        out = np.full(frames, self.target, dtype=np.float32)
        count = min(frames, self.remaining)
        if count:
            out[:count] = self.value + self.step * np.arange(count)
            self.value += count * self.step
            self.remaining -= count
        if not self.remaining:
            self.value = self.target
        return out
