"""Startup snapshot used to reject stale or wrong-data-directory engines."""
import hashlib
import os
from pathlib import Path


def runtime_identity(data_root):
    root = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    files = [root / 'pyproject.toml'] + sorted((root / 'stagespatialcue').rglob('*.py')) + sorted((root / 'stagespatialcue/static').glob('*'))
    for path in files:
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return {'source_root': str(root), 'source_sha256': digest.hexdigest(),
            'data_root': str(Path(data_root).expanduser().resolve()), 'pid': os.getpid()}
