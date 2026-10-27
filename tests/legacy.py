"""Test helpers: build v4 projects from the old one-file-per-cue fields."""
from stagespatialcue.models import Project


def with_cues(project: Project, cues: list[dict]) -> Project:
    """Old cue dicts (filename, media_relpath, position_deg, ...) → library + layers,
    exactly as a v3 project file migrates on load."""
    data = project.model_dump(mode='json', exclude={'media', 'cues'})
    data['cues'] = cues
    return Project.model_validate(data)


def cue_files(project: dict) -> list[str]:
    """Filename of the first layer's library sound for every cue (project JSON)."""
    media = {m['id']: m for m in project['media']}
    return [media[c['layers'][0]['media_id']]['filename'] if c['layers'] else '' for c in project['cues']]
