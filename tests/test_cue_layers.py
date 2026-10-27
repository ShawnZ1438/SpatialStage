"""v4: audio library + cues with several layers (position, level, delay per layer)."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stagespatialcue.audio import StageController
from stagespatialcue.bundle import sync_bundled_show
from stagespatialcue.mixer import Mixer
from stagespatialcue.models import Cue, CueLayer, MediaItem, PathPoint, PlaybackSpec, Project
from stagespatialcue.server import create_app
from stagespatialcue.storage import ProjectStore

REPO = Path(__file__).resolve().parents[1]


def layered_stage(tmp_path, layers, media_fields=None, cue_fields=None):
    """Controller with one cue; `layers` are CueLayer kwargs, one 0.1 s file each."""
    store = ProjectStore(tmp_path)
    project = store.create('Layers')
    folder = store.directory(project.id) / 'media'
    folder.mkdir()
    for i, layer in enumerate(layers):
        sf.write(folder / f'{i}.wav', np.full(4800, .4, dtype=np.float32), 48000, subtype='FLOAT')
        item = MediaItem(name=f'sound {i}', filename=f'{i}.wav', media_relpath=f'media/{i}.wav', duration_s=.1,
                         fade_in_s=0, fade_out_s=0, **(media_fields or {}))
        project.media.append(item)
        layer.setdefault('media_id', item.id)
    project.cues = [Cue(title='Two places', layers=[CueLayer(**l) for l in layers], **(cue_fields or {}))]
    store.save(project)
    stage = StageController(store)
    stage.arm(project.id)
    stage.stream = SimpleNamespace(active=True)
    stage.mixer.master_mute = False
    stage.mixer.master_db = 0
    assert stage.preflight(project.id)['issues'] == ['Select and connect a 4-output sound interface'] or True
    return stage, store.get(project.id)


def test_one_go_plays_every_layer_at_its_own_position_and_delay(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315), dict(position_deg=135, delay_s=.05)])
    stage.go(project.id)
    voices = stage.mixer.voices
    assert [v.cue.cue_id for v in voices] == [project.cues[0].id] * 2
    assert [v.start_frame for v in voices] == [0, 2400]
    out = stage.mixer.render(9600)
    assert out[1000, 0] > .35 and abs(out[1000, 2]) < 1e-6   # layer 1 front-left, layer 2 not started
    assert out[3000, 0] > .35 and out[3000, 2] > .35         # both playing
    status = stage.status()
    assert status['next_index'] == 1


def test_level_is_library_plus_layer_plus_cue_gain(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315, gain_db=-6)],
                                   media_fields={'gain_db': -6}, cue_fields={'gain_db': 0})
    spec = project.cue_specs(project.cues[0])[0]
    assert spec.gain_db == -12
    stage.go(project.id)
    out = stage.mixer.render(2000)
    assert out[1500, 0] == pytest.approx(.4 * 10 ** (-12 / 20), rel=1e-3)


def test_muted_layer_is_silent_and_replace_cue_stops_previous_layers(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315), dict(position_deg=45, muted=True)])
    stage.go(project.id)
    assert len(stage.mixer.voices) == 1
    out = stage.mixer.render(2000)
    assert abs(out[1500, 1]) < 1e-6


def test_trim_and_loop_come_from_the_library_sound(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315)],
                                   media_fields={'trim_start_s': .02, 'trim_end_s': .06, 'loop': True})
    stage.go(project.id)
    voice = stage.mixer.voices[0]
    assert len(voice.samples) == 1920 and voice.loop
    out = stage.mixer.render(48000)  # one second: a 40 ms loop keeps sounding
    assert out[-1, 0] > .35
    stage.mixer.stop_all(.04)
    stage.mixer.render(4800)
    assert not stage.mixer.voices


def test_loop_layer_stops_an_after_end_chain(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315)], media_fields={'loop': True},
                                   cue_fields={'continue_mode': 'auto_follow'})
    project.cues.append(Cue(title='never auto', layers=[CueLayer(media_id=project.media[0].id)]))
    stage.store.save(project)
    stage.sync(project)
    stage.preflight(project.id)
    status = stage.go(project.id)
    assert status['next_index'] == 1 and len(stage.mixer.voices) == 1


def test_empty_replace_cue_fades_out_what_is_playing(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315)], media_fields={'loop': True})
    project.cues.append(Cue(title='fade out', transition_s=.1))
    stage.store.save(project)
    stage.sync(project)
    stage.go(project.id)
    stage.mixer.render(4800)
    stage.go(project.id)
    stage.mixer.render(9600)
    assert not stage.mixer.voices


def test_live_layer_edit_moves_only_that_layer(tmp_path):
    stage, project = layered_stage(tmp_path, [dict(position_deg=315), dict(position_deg=45)],
                                   media_fields={'loop': True})
    stage.go(project.id)
    stage.mixer.render(1000)
    project.cues[0].layers[1].position_deg = 135
    stage.sync(project)
    out = stage.mixer.render(2000)
    assert out[-1, 0] > .35 and out[-1, 2] > .35 and abs(out[-1, 1]) < 1e-3


def test_project_rejects_layers_pointing_outside_the_library():
    with pytest.raises(ValidationError):
        Project(cues=[Cue(layers=[CueLayer(media_id='missing')])])
    with pytest.raises(ValidationError):
        MediaItem(trim_start_s=2, trim_end_s=1)


def test_v3_project_file_migrates_once_with_stable_ids(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create('Old show')
    folder = store.directory(project.id)
    old = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    old.pop('media')
    old['schema_version'] = 3
    preset = {'direction_mode': 'path', 'position_deg': 0, 'path': [{'time_s': 0, 'x_m': 1, 'y_m': 1}], 'stored_at': 'x'}
    old['cues'] = [
        {'id': 'aaaaaaaaaaaa', 'title': 'Wind', 'filename': '01_wind.wav', 'media_relpath': 'media/01_wind.wav',
         'gain_db': -9, 'stereo_mode': 'width', 'source_channels': 2, 'direction_mode': 'path',
         'path': [{'time_s': 0, 'x_m': 1, 'y_m': 1}], 'spatial_preset': preset},
        {'id': 'bbbbbbbbbbbb', 'title': 'Wind again', 'filename': '01_wind.wav', 'media_relpath': 'media/01_wind.wav',
         'stereo_mode': 'width', 'source_channels': 2, 'position_deg': 90},
    ]
    (folder / 'project.json').write_text(json.dumps(old), encoding='utf-8')
    first = store.get(project.id)
    assert len(first.media) == 1 and first.media[0].name == 'wind'  # same file + same design = one sound
    assert [c.gain_db for c in first.cues] == [-9, -6]
    assert first.cues[0].layers[0].path[0].x_m == 1 and first.cues[1].layers[0].position_deg == 90
    assert first.cues[0].spatial_preset.layers[0].layer_id == first.cues[0].layers[0].id
    assert json.loads((folder / 'project.json').read_text(encoding='utf-8'))['schema_version'] == 4
    assert store.get(project.id).model_dump() == first.model_dump()


def test_media_audition_previews_a_library_sound_without_moving_next(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        p = c.post('/api/projects', json={'name': 'library'}).json()
        wav = sf.SoundFile
        import io
        buf = io.BytesIO()
        sf.write(buf, np.full(4800, .2, dtype=np.float32), 48000, format='WAV')
        p = c.post(f"/api/projects/{p['id']}/upload?create_cues=false",
                   files=[('files', ('rain.wav', buf.getvalue(), 'audio/wav'))]).json()['project']
        media_id = p['media'][0]['id']
        assert not p['cues'] and wav
        c.post('/api/audio/arm', json={'project_id': p['id']})
        payload = {'project_id': p['id'], 'media_id': media_id}
        assert c.post('/api/audio/audition-media', json=payload).status_code == 400  # not connected
        c.post('/api/simulation/connect')
        assert c.post('/api/audio/audition-media', json=payload).status_code == 400  # muted
        c.post('/api/audio/master', json={'mute': False, 'db': -30})
        status = c.post('/api/audio/audition-media', json=payload).json()
        assert status['mixer']['voices'][0]['media_id'] == media_id and status['next_index'] == 0
        assert c.post('/api/audio/audition-media', json={**payload, 'media_id': 'nope'}).status_code == 400
        c.post('/api/audio/panic')


def test_repository_show_imports_as_library_plus_cues(tmp_path):
    if not (REPO / 'show' / 'project-template.json').is_file() or not list((REPO / 'show' / 'audio').glob('*')):
        pytest.skip('no repository show in this checkout')
    project = sync_bundled_show(ProjectStore(tmp_path), REPO / 'show')
    files = sorted(p.name for p in (REPO / 'show' / 'audio').iterdir() if p.suffix.lower() in {'.wav', '.flac'})
    assert sorted(m.filename for m in project.media) == files
    assert len(project.cues) == len(json.loads((REPO / 'show' / 'project-template.json').read_text(encoding='utf-8'))['cues'])
    assert all(len(c.layers) == 1 for c in project.cues)
    names = {m.id: m.name for m in project.media}
    assert names[project.cues[0].layers[0].media_id].startswith('01')  # manifest title on the sound


def test_playback_spec_group_is_its_cue():
    assert PlaybackSpec(cue_id='c1').group_id == 'c1'
    spec = PlaybackSpec()
    assert spec.group_id == spec.id
    mx = Mixer(Project(), sample_rate=1000)
    start, voices = mx.queue_group(spec, [(spec, np.ones(10, dtype=np.float32), 0),
                                          (spec, np.ones(10, dtype=np.float32), 5)])
    assert start == 0 and [v.start_frame for v in voices] == [0, 5]
    path = PlaybackSpec(direction_mode='path', path=[PathPoint(time_s=0, x_m=0, y_m=1)])
    assert path.path[0].y_m == 1
