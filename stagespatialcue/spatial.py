"""Planar constant-power VBAP, stage center geometry, and angular envelopes."""
from __future__ import annotations

import numpy as np
from .models import Speaker, ModPoint, DirectionADSR

SPEED_OF_SOUND_M_S = 343.0  # approximate at 20°C; not a measured calibration


def wrap_deg(deg):
    return np.mod(deg, 360.0)


def xy_from_polar(angle_deg: float, distance_m: float) -> tuple[float, float]:
    rad = np.deg2rad(angle_deg)
    return float(distance_m * np.sin(rad)), float(distance_m * np.cos(rad))


def polar_from_xy(x_m: float, y_m: float) -> tuple[float, float]:
    distance = float(np.hypot(x_m, y_m))
    if not np.isfinite(distance) or distance <= 0:
        raise ValueError("Speaker cannot be at stage center")
    return float(wrap_deg(np.rad2deg(np.arctan2(x_m, y_m)))), distance


def calibration_preview(speakers: list[Speaker]) -> list[dict]:
    """Theoretical center-point hints; does NOT calibrate real SPL or latency."""
    max_distance = max(s.distance_m for s in speakers)
    median_distance = float(np.median([s.distance_m for s in speakers]))
    result = []
    for speaker in speakers:
        x, y = xy_from_polar(speaker.angle_deg, speaker.distance_m)
        result.append({
            "name": speaker.name, "channel": speaker.output_channel,
            "angle_deg": round(speaker.angle_deg, 2), "distance_m": round(speaker.distance_m, 3),
            "x_m": round(x, 3), "y_m": round(y, 3),
            "pointing_at_center_deg": round(float(wrap_deg(speaker.angle_deg+180)), 2),
            "estimated_arrival_ms": round(speaker.distance_m / SPEED_OF_SOUND_M_S * 1000, 2),
            "suggested_extra_delay_ms": round((max_distance - speaker.distance_m) / SPEED_OF_SOUND_M_S * 1000, 2),
            "suggested_relative_gain_db": round(20 * np.log10(speaker.distance_m / median_distance), 2),
            "manual_trim_db": speaker.trim_db,
        })
    return result


def envelope_offsets(time_s: np.ndarray, points: list[ModPoint]) -> np.ndarray:
    """Straight-line interpolation on UNWRAPPED angular offsets.

    Offsets 0 -> +360 produce a full clockwise circle, not a 0° movement.
    """
    t = np.asarray(time_s, dtype=np.float64)
    if not points:
        return np.zeros_like(t)
    pts = sorted(points, key=lambda x: x.time_s)
    return np.interp(t, [p.time_s for p in pts], [p.offset_deg for p in pts])


def adsr_offsets(time_s: np.ndarray, duration_s: float, adsr: DirectionADSR) -> np.ndarray:
    """Attack→Decay→Sustain→Release for *direction*, not amplitude.

    A/D/R times are seconds; clipped content compresses phases proportionally,
    preventing negative sustain durations and keeping the final release in range.
    """
    t = np.asarray(time_s, dtype=np.float64)
    duration = max(float(duration_s), 1e-9)
    a, d, r = adsr.attack_s, adsr.decay_s, adsr.release_s
    if a + d + r > duration:
        scale = duration / (a + d + r)
        a, d, r = a * scale, d * scale, r * scale
    k0, k1, k2, k3, k4 = (0.0, a, a+d, duration-r, duration)
    # Duplicate times are intentional for zero-length stages; zero-duration
    # transitions jump instantly at the segment boundary.
    points = [(k0, 0.0), (k1, adsr.peak_offset_deg),
              (k2, adsr.sustain_offset_deg), (k3, adsr.sustain_offset_deg),
              (k4, adsr.release_offset_deg)]
    if t.size == 0:
        return t.copy()
    flat = t.reshape(-1)
    out = np.zeros_like(flat)
    out[flat >= k4] = adsr.release_offset_deg
    for (lo, vlo), (hi, vhi) in zip(points[:-1], points[1:]):
        if hi <= lo:
            continue
        mask = (flat >= lo) & (flat < hi)
        out[mask] = vlo + (flat[mask] - lo) / (hi - lo) * (vhi - vlo)
    return out.reshape(t.shape)


def cue_direction_offsets(time_s: np.ndarray, duration_s: float, cue) -> np.ndarray:
    if cue.direction_mode == 'adsr':
        return adsr_offsets(time_s, duration_s, cue.direction_adsr)
    return envelope_offsets(time_s, cue.modulation)


def vbap_gains(bearing_deg: float | np.ndarray, speakers: list[Speaker], *, distance_compensation: bool=False) -> np.ndarray:
    """Order: physical channels 1,2,3,4; for each bearing at most 2 active.

    Correct at the stage *reference center* under amplitude panning assumptions.
    This is NOT a room model or proof of localization for moving performers.
    """
    angles = np.asarray([s.angle_deg for s in speakers], dtype=float)
    idx = np.argsort(angles)
    sorted_angles = angles[idx]
    target = wrap_deg(np.atleast_1d(np.asarray(bearing_deg, dtype=float)))
    right_idx = np.searchsorted(sorted_angles, target, side='right') % 4
    left_idx = (right_idx - 1) % 4
    left_angle, right_angle = sorted_angles[left_idx], sorted_angles[right_idx]
    span = np.mod(right_angle - left_angle, 360)
    rel = np.mod(target - left_angle, 360)
    if np.any(span >= 180.0) or np.any(span <= 0):
        raise ValueError('Invalid speaker geometry')
    left = np.sin(np.deg2rad(span - rel)) / np.sin(np.deg2rad(span))
    right = np.sin(np.deg2rad(rel)) / np.sin(np.deg2rad(span))
    norm = np.hypot(left, right)
    left, right = left/norm, right/norm
    result = np.zeros((target.shape[0],4), dtype=np.float32)
    rows = np.arange(len(target))
    result[rows,idx[left_idx]] = left
    result[rows,idx[right_idx]] = right
    if distance_compensation:
        dist = np.asarray([s.distance_m for s in speakers], dtype=float)
        result *= (dist / np.median(dist)).astype(np.float32)
    for i, speaker in enumerate(speakers):
        result[:,i] *= np.float32(10.0**(speaker.trim_db/20.0))
    physical = np.zeros_like(result)
    for i, speaker in enumerate(speakers):
        physical[:,speaker.output_channel-1] = result[:,i]
    return physical
