"""Repository show folder → one project, so a fresh clone opens with its cues.

show/audio/* is copied into a project marked `bundle_id` the first time (with the
speaker layout from show/stage.json, if present); later
launches append files that were never imported before. Cues deleted in the app
stay deleted, and operator edits (order, positions, presets) are never touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .audio import filename_key, media_cue
from .models import Project
from .storage import AUDIO_EXT, ProjectStore

BUNDLE_ID = "repository-show"
SHOW_DIR = Path(__file__).resolve().parent.parent / "show"


def bundled_files(root: Path) -> list[Path]:
    folder = root / "audio"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_EXT and not p.name.startswith("."))


def sync_bundled_show(store: ProjectStore, root: Path | None = None) -> Project | None:
    root = Path(root or os.environ.get("SPATIALSTAGE_SHOW_DIR") or SHOW_DIR)
    files = bundled_files(root)
    if not files:
        return None
    project = next((p for p in (store.get(item["id"]) for item in store.all()) if p.bundle_id == BUNDLE_ID), None)
    created = project is None
    if created:
        name_file = root / "name.txt"
        name = name_file.read_text(encoding="utf-8").strip()[:100] if name_file.is_file() else ""
        project = Project(name=name or "Repository show", bundle_id=BUNDLE_ID)
        stage_file = root / "stage.json"  # optional speaker layout for a fresh project
        if stage_file.is_file():
            project = Project.model_validate({**project.model_dump(),
                                              **json.loads(stage_file.read_text(encoding="utf-8"))})
        store.save(project)
    known = set(project.bundle_files)
    added = []
    for path in files:
        if path.name in known:
            continue
        relative, display = store.add_file(project.id, path, path.name)
        added.append(media_cue(store.media_path(project.id, relative), relative, display))
        project.bundle_files.append(path.name)
    if added or created:
        project.cues.extend(sorted(added, key=filename_key))
        store.save(project)
    return project
