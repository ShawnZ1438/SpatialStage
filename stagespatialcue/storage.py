"""Atomic JSON project persistence and media path isolation."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import BinaryIO
from pathlib import Path

from .models import Project

ID_RE = re.compile(r"^[a-f0-9]{12}$")
AUDIO_EXT = {".wav", ".aiff", ".aif", ".flac", ".ogg", ".mp3", ".m4a", ".aac"}


class ProjectStore:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, project_id: str) -> Path:
        if not ID_RE.fullmatch(project_id):
            raise ValueError("Invalid project ID")
        return self.root / project_id

    def all(self) -> list[dict]:
        found = []
        for path in sorted(self.root.glob("*/project.json")):
            try:
                p = Project.model_validate_json(path.read_text(encoding="utf-8"))
                found.append({"id": p.id, "name": p.name, "updated_at": p.updated_at, "count": len(p.cues)})
            except (OSError, ValueError):
                continue
        return sorted(found, key=lambda p: p["updated_at"], reverse=True)

    def create(self, name: str) -> Project:
        project = Project(name=name[:100] or "Untitled show")
        self.save(project)
        return project

    def get(self, project_id: str) -> Project:
        path = self.directory(project_id) / "project.json"
        if not path.exists():
            raise FileNotFoundError("Project not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        project = Project.model_validate(data)
        if data.get("schema_version", 1) < project.schema_version:
            # Persist the migration once (keeping updated_at) so every reader
            # sees the same library/layer IDs from now on.
            self._write(project)
        return project

    def save(self, project: Project) -> Project:
        project.updated_at = datetime.now(timezone.utc).isoformat()
        return self._write(project)

    def _write(self, project: Project) -> Project:
        folder = self.directory(project.id)
        folder.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".save-", dir=folder, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(project.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, folder / "project.json")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        return project

    def media_path(self, project_id: str, relpath: str) -> Path:
        base = self.directory(project_id).resolve()
        if not relpath.startswith("media/"):
            raise ValueError("Media path must be inside media/")
        resolved = (base / relpath).resolve()
        if not resolved.is_relative_to(base / "media"):
            raise ValueError("Unsafe media path")
        return resolved

    def add_file(self, project_id: str, incoming_file: Path, name: str) -> tuple[str, str]:
        extension = Path(name).suffix.lower()
        if extension not in AUDIO_EXT:
            raise ValueError("Unsupported audio extension")
        stem = Path(name.replace("\\", "/")).name
        stem = re.sub(r"[^\w.\- ()\u4e00-\u9fff]", "_", stem, flags=re.UNICODE)[:180]
        if not stem or stem.startswith("."):
            stem = "sound" + extension
        folder = self.directory(project_id) / "media"
        folder.mkdir(parents=True, exist_ok=True)
        base = Path(stem)
        candidate = folder / base.name
        count = 2
        while candidate.exists():
            candidate = folder / f"{base.stem}_{count}{extension}"
            count += 1
        shutil.copyfile(incoming_file, candidate)
        return "media/" + candidate.name, Path(name).name

    def export_zip(self, project_id: str) -> BinaryIO:
        """Bounded-memory backup: current media + project + acoustic profiles only."""
        folder = self.directory(project_id)
        project = self.get(project_id)
        stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        try:
            members = {"project.json": folder / "project.json"}
            for item in project.media:
                if item.media_relpath:
                    members[item.media_relpath] = self.media_path(project_id, item.media_relpath)
            for path in (folder / "autocal").glob("*.json"):
                if not path.name.startswith('.') and path.resolve().is_relative_to(folder.resolve()):
                    members[path.relative_to(folder).as_posix()] = path
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, path in sorted(members.items()):
                    if path.is_file():
                        archive.write(path, name)
            stream.seek(0)
            return stream
        except Exception:
            stream.close()
            raise
