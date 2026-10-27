"""SpatialStage project v4. Time is seconds, bearings clockwise from 12 o'clock.

v4 separates the audio library (sound design per file) from cues (what fires on
GO). A cue holds one or more layers; each layer plays one library sound at its
own position/path, level and delay. Older projects migrate on load.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
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


class PathPoint(BaseModel):
    """Stage-map waypoint in metres about the centre (0,0); time is clip seconds."""
    time_s: float = Field(ge=0, le=14400)
    x_m: float = Field(ge=-100, le=100)
    y_m: float = Field(ge=-100, le=100)


def _sorted_path(points: list[PathPoint]) -> list[PathPoint]:
    if len(points) > 200:
        raise ValueError("Maximum 200 path points per cue")
    return sorted(points, key=lambda p: p.time_s)


class Spatial(BaseModel):
    """Where one sound plays: a bearing with an angular envelope, or stage-map XY."""
    position_deg: float = Field(default=0, ge=0, le=360)
    direction_mode: Literal["keyframes", "adsr", "path"] = "keyframes"
    modulation: list[ModPoint] = Field(default_factory=lambda: [ModPoint(time_s=0, offset_deg=0)])
    direction_adsr: DirectionADSR = Field(default_factory=DirectionADSR)
    # direction_mode "path": XY waypoints replace bearing + angular envelope.
    path: list[PathPoint] = Field(default_factory=list)

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

    @field_validator("path")
    @classmethod
    def valid_path(cls, points: list[PathPoint]) -> list[PathPoint]:
        return _sorted_path(points)

    @model_validator(mode="after")
    def path_mode_has_points(self):
        if self.direction_mode == "path" and not self.path:
            raise ValueError("Path mode needs at least one stage-map point")
        return self


SPATIAL_FIELDS = tuple(Spatial.model_fields)


class MediaItem(BaseModel):
    """One audio file in the project library and its sound design.

    Shared by every cue layer that uses it: trims, fades, loop, level and stereo
    handling belong to the sound; where it plays belongs to the cue layer.
    """
    id: str = Field(default_factory=uid)
    name: str = "Untitled audio"
    filename: str = ""
    media_relpath: str = ""
    duration_s: float = Field(default=0, ge=0)
    source_channels: int = Field(default=1, ge=1, le=64)
    gain_db: float = Field(default=0, ge=-90, le=12)
    trim_start_s: float = Field(default=0, ge=0, le=14400)
    trim_end_s: float = Field(default=0, ge=0, le=14400)  # 0 = to the end of the file
    fade_in_s: float = Field(default=0.05, ge=0, le=3600)
    fade_out_s: float = Field(default=0.1, ge=0, le=3600)
    loop: bool = False
    # Stereo files: "width" keeps L/R as two sources at ±width/2 around the layer
    # position; "mono" downmixes.
    stereo_mode: Literal["mono", "width"] = "mono"
    stereo_width_deg: float = Field(default=90, ge=0, le=180)
    color: str = "cyan"
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_trim(self) -> "MediaItem":
        if self.trim_end_s and self.trim_end_s <= self.trim_start_s:
            raise ValueError("Audio trim end must be after trim start (0 = file end)")
        return self

    @property
    def play_duration_s(self) -> float:
        end = self.trim_end_s or self.duration_s
        return max(0.0, end - self.trim_start_s) if end else 0.0


class CueLayer(Spatial):
    """One library sound inside a cue: its own position/path, level and delay."""
    id: str = Field(default_factory=uid)
    media_id: str
    gain_db: float = Field(default=0, ge=-90, le=12)
    delay_s: float = Field(default=0, ge=0, le=3600)
    muted: bool = False


class LayerPreset(Spatial):
    layer_id: str = ""


class SpatialPreset(BaseModel):
    """Stored spatial setup of every layer of a cue, restored by Recall."""
    layers: list[LayerPreset] = Field(default_factory=list)
    stored_at: str = ""

    @model_validator(mode="before")
    @classmethod
    def legacy_single_layer(cls, data):
        # v3 presets stored one cue's spatial fields at the top level.
        if isinstance(data, dict) and "layers" not in data and "direction_mode" in data:
            layer = {k: data[k] for k in SPATIAL_FIELDS if k in data}
            return {"layers": [{**layer, "layer_id": data.get("layer_id", "")}],
                    "stored_at": data.get("stored_at", "")}
        return data


class Cue(BaseModel):
    id: str = Field(default_factory=uid)
    title: str = "Untitled cue"
    color: str = "cyan"
    notes: str = Field(default="", max_length=2000)
    layers: list[CueLayer] = Field(default_factory=list)
    spatial_preset: SpatialPreset | None = None
    gain_db: float = Field(default=0, ge=-90, le=12)
    transition_s: float = Field(default=2.5, ge=0, le=60)
    replace_style: Literal["crossfade", "cut"] = "crossfade"
    pre_wait_s: float = Field(default=0, ge=0, le=3600)
    post_wait_s: float = Field(default=0, ge=0, le=3600)
    start_mode: Literal["replace", "layer", "queue"] = "replace"
    continue_mode: Literal["manual", "auto_continue", "auto_follow"] = "manual"
    stop_fade_s: float = Field(default=2, ge=0, le=60)  # this cue's ■ button

    @model_validator(mode="after")
    def valid_layers(self) -> "Cue":
        if len(self.layers) > 32:
            raise ValueError("Maximum 32 audio layers per cue")
        ids = [layer.id for layer in self.layers]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate layer IDs in a cue")
        return self


class PlaybackSpec(Spatial):
    """Flat description of ONE playing sound, built from cue + layer + library item.

    The mixer only knows these. Scheduling fields come from the cue; level is
    library gain + layer gain + cue gain; fades, loop and stereo come from the sound.
    """
    id: str = Field(default_factory=uid)
    cue_id: str = ""
    layer_id: str = ""
    media_id: str = ""
    title: str = "Untitled sound"
    duration_s: float = Field(default=0, ge=0)
    source_channels: int = Field(default=1, ge=1, le=64)
    stereo_mode: Literal["mono", "width"] = "mono"
    stereo_width_deg: float = Field(default=90, ge=0, le=180)
    gain_db: float = Field(default=-6, ge=-270, le=36)
    fade_in_s: float = Field(default=0.05, ge=0, le=3600)
    fade_out_s: float = Field(default=0.1, ge=0, le=3600)
    loop: bool = False
    transition_s: float = Field(default=2.5, ge=0, le=60)
    replace_style: Literal["crossfade", "cut"] = "crossfade"
    pre_wait_s: float = Field(default=0, ge=0, le=3600)
    post_wait_s: float = Field(default=0, ge=0, le=3600)
    start_mode: Literal["replace", "layer", "queue"] = "replace"
    continue_mode: Literal["manual", "auto_continue", "auto_follow"] = "manual"

    @property
    def group_id(self) -> str:
        """The cue this sound belongs to (a bare spec is its own group)."""
        return self.cue_id or self.id


CUE_SCHEDULE_FIELDS = ("transition_s", "replace_style", "pre_wait_s", "post_wait_s",
                       "start_mode", "continue_mode")
MEDIA_SOUND_FIELDS = ("source_channels", "stereo_mode", "stereo_width_deg",
                      "fade_in_s", "fade_out_s", "loop")


def layer_spec(cue: Cue, layer: CueLayer, media: MediaItem) -> PlaybackSpec:
    return PlaybackSpec(
        id=f"{cue.id}:{layer.id}", cue_id=cue.id, layer_id=layer.id, media_id=media.id,
        title=cue.title if len(cue.layers) == 1 else f"{cue.title} · {media.name}",
        duration_s=media.play_duration_s,
        gain_db=media.gain_db + layer.gain_db + cue.gain_db,
        **{k: getattr(layer, k) for k in SPATIAL_FIELDS},
        **{k: getattr(media, k) for k in MEDIA_SOUND_FIELDS},
        **{k: getattr(cue, k) for k in CUE_SCHEDULE_FIELDS})


def media_display_name(filename: str) -> str:
    """'001_Rain_heavy.wav' -> 'Rain heavy' (leading numbers stay out of names)."""
    stem = PurePosixPath(filename.replace("\\", "/")).stem
    match = re.match(r"^\d{1,5}[-_ ](.+)$", stem)
    return (match.group(1) if match else stem).replace("_", " ") or "Untitled audio"


def _stable_id(*parts) -> str:
    return hashlib.sha1("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()[:12]


LEGACY_MEDIA_FIELDS = ("filename", "media_relpath", "duration_s", "source_channels",
                       "stereo_mode", "stereo_width_deg", "fade_in_s", "fade_out_s")


def migrate_v3_project(data: dict) -> dict:
    """v1-v3 cues each owned one file. Split them into library items + one layer.

    IDs are derived from the old data, so every load of the same file agrees.
    The same file with identical sound settings becomes one library item.
    """
    cues = data.get("cues") or []
    if "media" in data or not any(isinstance(c, dict) and "layers" not in c for c in cues):
        return data
    media, by_key, new_cues = [], {}, []
    for raw in cues:
        if not isinstance(raw, dict) or "layers" in raw:
            new_cues.append(raw)
            continue
        cue = {k: v for k, v in raw.items() if k not in LEGACY_MEDIA_FIELDS and k not in SPATIAL_FIELDS}
        cue["gain_db"] = raw.get("gain_db", -6)  # v3 default was -6 dB on the cue
        cue["id"] = cue_id = raw.get("id") or uid()
        cue["layers"] = []
        cue.pop("spatial_preset", None)
        relpath = raw.get("media_relpath") or ""
        if relpath:
            design = {k: raw[k] for k in LEGACY_MEDIA_FIELDS if k in raw}
            key = json.dumps(design, sort_keys=True, ensure_ascii=False)
            if key not in by_key:
                by_key[key] = {**design, "id": _stable_id("media", key), "gain_db": 0,
                               "name": media_display_name(raw.get("filename") or relpath),
                               "color": raw.get("color", "cyan")}
                media.append(by_key[key])
            layer_id = _stable_id("layer", cue_id)
            spatial = {k: raw[k] for k in SPATIAL_FIELDS if k in raw}
            cue["layers"] = [{**spatial, "id": layer_id, "media_id": by_key[key]["id"]}]
            preset = raw.get("spatial_preset")
            if isinstance(preset, dict):
                cue["spatial_preset"] = {"layers": [{**{k: preset[k] for k in SPATIAL_FIELDS if k in preset},
                                                     "layer_id": layer_id}],
                                         "stored_at": preset.get("stored_at", "")}
        new_cues.append(cue)
    return {**data, "media": media, "cues": new_cues}


class Project(BaseModel):
    # Older projects migrate automatically (Pydantic defaults + migrate_v3_project).
    schema_version: int = 4
    id: str = Field(default_factory=uid)
    name: str = "Untitled show"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    speakers: list[Speaker] = Field(default_factory=lambda: [s.model_copy() for s in DEFAULT_SPEAKERS])
    distance_compensation: bool = False  # opt-in, approximate only
    # Off: a sound only ends by itself or by STOP / ■ (replace cues and CUT GO
    # never fade other sounds out). On: the classic replace / CUT GO behaviour.
    auto_replace: bool = False
    global_rotation_deg: float = Field(default=0, ge=-3600, le=3600)
    global_envelope_enabled: bool = False
    global_modulation: list[ModPoint] = Field(default_factory=lambda: [ModPoint(time_s=0, offset_deg=0)])
    preferred_input_device: int | None = None  # legacy; not used or shown in the UI
    # Set on the project created from the repository's show/audio folder.
    bundle_id: str | None = None
    bundle_files: list[str] = Field(default_factory=list)
    # Only managed by the AutoCal approval API. Ordinary project PUT cannot enable it.
    active_calibration_id: str | None = None
    calibration_enabled: bool = False
    media: list[MediaItem] = Field(default_factory=list)
    cues: list[Cue] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_cues(cls, data):
        if not isinstance(data, dict):
            return data
        return {**migrate_v3_project(data), "schema_version": max(4, data.get("schema_version", 1))}

    def media_by_id(self) -> dict[str, MediaItem]:
        return {m.id: m for m in self.media}

    def cue_specs(self, cue: Cue) -> list[PlaybackSpec]:
        """Audible layers of a cue as flat mixer specs (muted layers skipped)."""
        media = self.media_by_id()
        return [layer_spec(cue, layer, media[layer.media_id]) for layer in cue.layers if not layer.muted]

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
        media_ids = [m.id for m in self.media]
        if len(set(media_ids)) != len(media_ids):
            raise ValueError("Duplicate audio library IDs")
        known = set(media_ids)
        for cue in self.cues:
            for layer in cue.layers:
                if layer.media_id not in known:
                    raise ValueError(f"Cue '{cue.title}' uses audio that is not in the library")
        return self
