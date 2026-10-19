"""2-D VBAP: 0° is upstage/top of displayed circle, 90° clockwise right.

This is gain panning, not HRTF/head tracking or true sound field synthesis.
Distances are optional center-point inverse-distance gain compensation only.
"""
import numpy as np

from .models import Speaker, ModPoint


def wrap_deg(deg):
    return np.mod(deg, 360.0)


def envelope_offsets(time_s: np.ndarray, points: list[ModPoint]) -> np.ndarray:
    """Unwrapped offset interpolation: 350 -> 370 means a +20° sweep.

    The keyframe y-axis is an offset, not the absolute cue bearing.
    """
    points = sorted(points, key=lambda x: x.time_s)
    if not points:
        return np.zeros_like(time_s, dtype=np.float64)
    return np.interp(
        time_s,
        np.array([x.time_s for x in points]),
        np.array([x.offset_deg for x in points]),
    )


def vbap_gains(
    bearing_deg: float | np.ndarray,
    speakers: list[Speaker],
    *,
    distance_compensation: bool = False,
) -> np.ndarray:
    """Return gains ordered by physical channels 1..4 (shape N,4).

    At the center of a pair, equal-power gains are used. We skip room effects.
    """
    angles = np.asarray([s.angle_deg for s in speakers], dtype=float)
    sort_indices = np.argsort(angles)
    sorted_angles = angles[sort_indices]
    target = wrap_deg(np.atleast_1d(np.asarray(bearing_deg, dtype=float)))
    right_index = np.searchsorted(sorted_angles, target, side="right") % 4
    left_index = (right_index - 1) % 4
    a = sorted_angles[left_index]
    b = sorted_angles[right_index]
    span = np.mod(b - a, 360.0)
    rel = np.mod(target - a, 360.0)
    if np.any(span >= 180.0) or np.any(span <= 0):
        raise ValueError("Invalid loudspeaker geometry")
    # Pair solution for target = L*[g_left, g_right], prior to equal-power norm.
    left = np.sin(np.deg2rad(span - rel)) / np.sin(np.deg2rad(span))
    right = np.sin(np.deg2rad(rel)) / np.sin(np.deg2rad(span))
    norm = np.hypot(left, right)
    left, right = left / norm, right / norm
    result = np.zeros((target.shape[0], 4), dtype=np.float32)
    rows = np.arange(len(target))
    result[rows, sort_indices[left_index]] = left
    result[rows, sort_indices[right_index]] = right
    if distance_compensation:
        # Simplified inverse-distance correction at one reference position.
        dist = np.asarray([s.distance_m for s in speakers], dtype=float)
        result *= (dist / np.median(dist)).astype(np.float32)
    for i, speaker in enumerate(speakers):
        result[:, i] *= np.float32(10.0 ** (speaker.trim_db / 20.0))
    physical = np.zeros_like(result)
    for i, speaker in enumerate(speakers):
        physical[:, speaker.output_channel - 1] = result[:, i]
    return physical
