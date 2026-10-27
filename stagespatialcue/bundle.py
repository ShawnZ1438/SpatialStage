"""Repository show folder → one project, so a fresh clone opens with its cues.

show/audio/* is copied into a project marked `bundle_id` the first time (with the
speaker layout from show/stage.json and the cue setup from show/project-template.json,
if present). Every file becomes a library sound; on that first import each file
also gets a one-layer cue. Later launches only add never-imported files to the
audio library, so cues the operator deleted or rebuilt are never touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .audio import filename_key, media_item, single_layer_cue
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
    manifest_file = root / "cue-manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.is_file() else {}
    known = set(project.bundle_files)
    added = []
    for path in files:
        if path.name in known:
            continue
        relative, display = store.add_file(project.id, path, path.name)
        item = media_item(store.media_path(project.id, relative), relative, display)
        if path.name in manifest:
            item.name = manifest[path.name]["title"]
        added.append(item)
        project.bundle_files.append(path.name)
    if not (added or created):
        return project
    added.sort(key=filename_key)
    template_file = root / 'project-template.json'
    if created and template_file.is_file():
        # First import only: existing local projects never receive the template.
        template = json.loads(template_file.read_text(encoding='utf-8'))
        relpaths = {m.filename: m.media_relpath for m in added}
        if "media" in template:  # v4 template: library + layered cues
            for item in template["media"]:
                if item["filename"] not in relpaths:
                    raise ValueError(f"Show template media missing: {item['filename']}")
                item["media_relpath"] = relpaths[item["filename"]]
        else:  # v3 template: one file per cue, migrated by Project
            for cue in template.get('cues', []):
                if cue['filename'] not in relpaths:
                    raise ValueError(f"Show template media missing: {cue['filename']}")
                cue['media_relpath'] = relpaths[cue['filename']]
        template.update(id=project.id, bundle_id=BUNDLE_ID, bundle_files=project.bundle_files,
                        active_calibration_id=None, calibration_enabled=False)
        project = Project.model_validate(template)
        used = {m.media_relpath for m in project.media}
        project.media.extend(m for m in added if m.media_relpath not in used)
    else:
        project.media.extend(added)
        if created:
            project.cues.extend(single_layer_cue(m) for m in added)
    store.save(project)
    return project
