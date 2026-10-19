"""Saved project schema: all cue timing values are expressed in seconds."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def uid() -> str:
    return uuid4().hex[:12]


class Speaker(BaseModel):
    name: str
    angle_deg: float = Field(ge=0, lt=360)
    distance_m: float = Field(gt=0, le=1000)
    output_channel: int = Field(ge=1, le=4)
    trim_db: float = Field(default=0, ge=-30, le=12)


DEFAULT_SPEAKERS = [
    Speaker(name="Front Left", angle_deg=315, distance_m=3, output_channel=1),
    Speaker(name="Front Right", angle_deg=45, distance_m=3, output_channel=2),
    Speaker(name="Rear Right", angle_deg=135, distance_m=3, output_channel=3),
    Speaker(name="Rear Left", angle_deg=225, distance_m=3, output_channel=4),
]


class ModPoint(BaseModel):
    time_s: float = Field(ge=0)
    offset_deg: float = Field(ge=-2160, le=2160)


class Cue(BaseModel):
    id: str = Field(default_factory=uid)
    title: str = "Untitled cue"
    filename: str = ""
    media_relpath: str = ""
    duration_s: float = Field(default=0, ge=0)
    color: str = "cyan"
    position_deg: float = Field(default=0, ge=0, lt=360)
    modulation: list[ModPoint] = Field(default_factory=lambda: [ModPoint(time_s=0, offset_deg=0)])
    gain_db: float = Field(default=-6, ge=-90, le=12)
    fade_in_s: float = Field(default=0.05, ge=0, le=3600)
    fade_out_s: float = Field(default=0.1, ge=0, le=3600)
    transition_s: float = Field(default=0.05, ge=0, le=60)
    pre_wait_s: float = Field(default=0, ge=0, le=3600)
    post_wait_s: float = Field(default=0, ge=0, le=3600)
    start_mode: Literal["replace", "layer", "queue"] = "replace"
    continue_mode: Literal["manual", "auto_continue", "auto_follow"] = "manual"

    @field_validator("modulation")
    @classmethod
    def valid_points(cls, points: list[ModPoint]) -> list[ModPoint]:
        if not points:
            return [ModPoint(time_s=0, offset_deg=0)]
        return sorted(points, key=lambda p: p.time_s)


class Project(BaseModel):
    schema_version: int = 1
    id: str = Field(default_factory=uid)
    name: str = "Untitled show"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    speakers: list[Speaker] = Field(default_factory=lambda: [s.model_copy() for s in DEFAULT_SPEAKERS])
    distance_compensation: bool = False
    global_rotation_deg: float = Field(default=0, ge=-3600, le=3600)
    preferred_input_device: int | None = None  # metadata, not a microphone routing facility
    cues: list[Cue] = Field(default_factory=list)

    @model_validator(mode="after")
    def speaker_geometry(self) -> "Project":
        if len(self.speakers) != 4:
            raise ValueError("Exactly 4 loudspeakers are required")
        if sorted(x.output_channel for x in self.speakers) != [1, 2, 3, 4]:
            raise ValueError("Speaker output channels must be a unique 1/2/3/4 permutation")
        angles = sorted(s.angle_deg for s in self.speakers)
        gaps = [(angles[(i + 1) % 4] - angles[i]) % 360 for i in range(4)]
        if max(gaps) >= 180:
            raise ValueError("Speakers must encircle the reference point (no gap >= 180°)")
        ids = [c.id for c in self.cues]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate cue IDs")
        return self
