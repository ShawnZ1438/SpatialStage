"""SpatialStage project v2. Time is seconds, bearings clockwise from 12 o'clock."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def uid() -> str:
    return uuid4().hex[:12]


class Speaker(BaseModel):
    """Canonical polar geometry about the fixed stage center (0,0).

    Screen x increases to the right, y towards 12 o'clock/upstage.
    x = distance*sin(angle), y = distance*cos(angle).
    """
    name: str
    angle_deg: float = Field(ge=0, le=360)
    distance_m: float = Field(gt=0, le=100)
    output_channel: int = Field(ge=1, le=4)
    trim_db: float = Field(default=0, ge=-30, le=12)

    @field_validator('angle_deg')
    @classmethod
    def canonical_angle(cls, value):
        return value % 360


DEFAULT_SPEAKERS = [
    Speaker(name="L · front left", angle_deg=315, distance_m=3, output_channel=1),
    Speaker(name="R · front right", angle_deg=45, distance_m=3, output_channel=2),
    Speaker(name="RR · rear right", angle_deg=135, distance_m=3, output_channel=3),
    Speaker(name="RL · rear left", angle_deg=225, distance_m=3, output_channel=4),
]


class ModPoint(BaseModel):
    time_s: float = Field(ge=0, le=14400)
    offset_deg: float = Field(ge=-2160, le=2160)


class DirectionADSR(BaseModel):
    """Unwrapped angular offset, not a gain envelope.

    Attack: 0 to peak. Decay: peak to sustain. Hold: sustain.
    Release: sustain to release_offset in the last release_s of the clip.
    If A+D+R > duration, phases are proportionally compressed.
    """
    attack_s: float = Field(default=0.3, ge=0, le=3600)
    peak_offset_deg: float = Field(default=90, ge=-2160, le=2160)
    decay_s: float = Field(default=0.5, ge=0, le=3600)
    sustain_offset_deg: float = Field(default=90, ge=-2160, le=2160)
    release_s: float = Field(default=0.3, ge=0, le=3600)
    release_offset_deg: float = Field(default=0, ge=-2160, le=2160)


class Cue(BaseModel):
    id: str = Field(default_factory=uid)
    title: str = "Untitled cue"
    filename: str = ""
    media_relpath: str = ""
    duration_s: float = Field(default=0, ge=0)
    color: str = "cyan"
    position_deg: float = Field(default=0, ge=0, le=360)
    direction_mode: Literal["keyframes", "adsr"] = "keyframes"
    modulation: list[ModPoint] = Field(default_factory=lambda: [ModPoint(time_s=0, offset_deg=0)])
    direction_adsr: DirectionADSR = Field(default_factory=DirectionADSR)
    gain_db: float = Field(default=-6, ge=-90, le=12)
    fade_in_s: float = Field(default=0.05, ge=0, le=3600)
    fade_out_s: float = Field(default=0.1, ge=0, le=3600)
    transition_s: float = Field(default=2.5, ge=0, le=60)
    replace_style: Literal["crossfade", "cut"] = "crossfade"
    pre_wait_s: float = Field(default=0, ge=0, le=3600)
    post_wait_s: float = Field(default=0, ge=0, le=3600)
    start_mode: Literal["replace", "layer", "queue"] = "replace"
    continue_mode: Literal["manual", "auto_continue", "auto_follow"] = "manual"

    @field_validator('position_deg')
    @classmethod
    def canonical_bearing(cls, value):
        return value % 360

    @field_validator("modulation")
    @classmethod
    def valid_points(cls, points: list[ModPoint]) -> list[ModPoint]:
        if not points:
            return [ModPoint(time_s=0, offset_deg=0)]
        if len(points) > 200:
            raise ValueError("Maximum 200 direction keyframes per cue")
        return sorted(points, key=lambda p: p.time_s)


class Project(BaseModel):
    # v1 projects migrate automatically via Pydantic defaults; old data remains loadable.
    schema_version: int = 3
    id: str = Field(default_factory=uid)
    name: str = "Untitled show"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    speakers: list[Speaker] = Field(default_factory=lambda: [s.model_copy() for s in DEFAULT_SPEAKERS])
    distance_compensation: bool = False  # opt-in, approximate only
    global_rotation_deg: float = Field(default=0, ge=-3600, le=3600)
    global_envelope_enabled: bool = False
    global_modulation: list[ModPoint] = Field(default_factory=lambda: [ModPoint(time_s=0, offset_deg=0)])
    preferred_input_device: int | None = None  # legacy; not used or shown in the UI
    # Only managed by the AutoCal approval API. Ordinary project PUT cannot enable it.
    active_calibration_id: str | None = None
    calibration_enabled: bool = False
    cues: list[Cue] = Field(default_factory=list)

    @field_validator("global_modulation")
    @classmethod
    def global_curve(cls, points: list[ModPoint]) -> list[ModPoint]:
        if len(points) > 200:
            raise ValueError("Maximum 200 global direction keyframes")
        return sorted(points, key=lambda p: p.time_s) or [ModPoint(time_s=0, offset_deg=0)]

    @model_validator(mode="after")
    def speaker_geometry(self) -> "Project":
        if len(self.speakers) != 4:
            raise ValueError("Exactly 4 loudspeakers are required")
        if sorted(x.output_channel for x in self.speakers) != [1, 2, 3, 4]:
            raise ValueError("Speaker output channels must be a unique 1/2/3/4 permutation")
        angles = sorted(s.angle_deg for s in self.speakers)
        gaps = [(angles[(i + 1) % 4] - angles[i]) % 360 for i in range(4)]
        if min(gaps) < 0.01 - 1e-9:
            raise ValueError("Speaker bearings must be separated by at least 0.01 degrees, including across 0/360")
        if max(gaps) >= 180:
            raise ValueError("Speakers must surround the stage center (gap < 180°)")
        ids = [c.id for c in self.cues]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate cue IDs")
        return self
