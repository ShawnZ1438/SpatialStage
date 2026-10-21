"""Audit regressions: actual rendered samples and API state, no audio hardware."""
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from stagespatialcue.audio import StageController
from stagespatialcue.mixer import Mixer
from stagespatialcue.models import Cue, Project
from stagespatialcue.server import create_app
from stagespatialcue.storage import ProjectStore


def plain(**kw):
    return Cue(gain_db=0, fade_in_s=0, fade_out_s=0, **kw)


def running_mixer():
    mx = Mixer(Project(), sample_rate=1000)
    mx.master_db = 0
    mx.master_mute = False
    mx.render(30)  # allow a deliberate unmute ramp to settle before measurements
    return mx


@pytest.mark.parametrize('second_stop', ['stop', 'replace'])
def test_repeated_stop_never_raises_current_level_or_extends_end(second_stop):
    mx = running_mixer()
    old = mx.queue(plain(position_deg=315), np.ones(5000, dtype=np.float32))
    mx.render(100)
    mx.queue(plain(position_deg=45, transition_s=2), np.ones(5000, dtype=np.float32))
    before = mx.render(1000)
    original_end = old.end_frame
    if second_stop == 'stop':
        mx.stop_all(2)  # same duration must NOT restart the existing ramp
    else:
        mx.queue(plain(position_deg=135, transition_s=2), np.ones(5000, dtype=np.float32))
    after = mx.render(1000)
    assert after[0, 0] <= before[-1, 0] + 1e-6
    assert old.end_frame <= original_end
    assert np.max(np.diff(after[:, 0])) <= 1e-6


def test_shorter_stop_starts_from_current_gain():
    mx = running_mixer()
    old = mx.queue(plain(position_deg=315), np.ones(5000, dtype=np.float32))
    mx.render(100)
    mx.stop_all(2)
    before = mx.render(1000)
    mx.stop_all(.04)
    after = mx.render(60)
    assert .49 <= after[0, 0] <= before[-1, 0]
    assert after[20, 0] == pytest.approx(.25, abs=.002)
    assert np.all(after[40:] == 0)
    assert old.end_frame <= mx.frame


def make_chain(tmp_path, modes=('auto_continue', 'manual'), waits=(0, 0)):
    store = ProjectStore(tmp_path)
    p = store.create('Auto chain')
    media = store.directory(p.id) / 'media'
    media.mkdir()
    for i, (mode, wait) in enumerate(zip(modes, waits)):
        name = f'{i}.wav'
        sf.write(media / name, np.full(4800, .4, dtype=np.float32), 48000, subtype='FLOAT')
        p.cues.append(plain(position_deg=[315, 45, 135][i], filename=name,
                           media_relpath='media/' + name, continue_mode=mode, post_wait_s=wait))
    store.save(p)
    stage = StageController(store)
    stage.arm(p.id)
    stage.stream = SimpleNamespace(active=True)
    stage.mixer.master_mute = False
    stage.mixer.master_db = 0
    stage.preflight(p.id)
    return stage, p


def test_zero_wait_auto_continue_preserves_both_default_replace_cues(tmp_path):
    stage, p = make_chain(tmp_path)
    result = stage.go(p.id)
    output = stage.mixer.render(4800)
    assert output[:, 0].max() > .35, 'first auto-linked cue was swallowed'
    assert output[:, 1].max() > .35
    assert result['next_index'] == 2
    assert len([e for e in stage.mixer.drain_events() if e['event'] == 'cue_audio_start']) == 2


def test_three_same_frame_auto_linked_cues_all_sound(tmp_path):
    stage, p = make_chain(tmp_path, ('auto_continue', 'auto_continue', 'manual'), (0, 0, 0))
    stage.go(p.id)
    out = stage.mixer.render(4800)
    assert np.all(out[:, :3].max(axis=0) > .35)


def wave_bytes():
    wave = BytesIO()
    sf.write(wave, np.zeros(4800, dtype=np.float32), 48000, format='WAV')
    return wave.getvalue()


def test_import_sorts_only_new_rows_keeps_existing_cue_ids_and_order(tmp_path):
    client = TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8765')
    p = client.post('/api/projects', json={'name': 'Order'}).json()
    url = f"/api/projects/{p['id']}"
    wav = wave_bytes()
    p = client.post(url + '/upload', files=[
        ('files', ('002_b.wav', wav, 'audio/wav')),
        ('files', ('001_a.wav', wav, 'audio/wav')),
    ]).json()['project']
    p['cues'].reverse()
    old_ids = [c['id'] for c in p['cues']]
    assert client.put(url, json=p).status_code == 200
    res = client.post(url + '/upload', files=[
        ('files', ('004_d.wav', wav, 'audio/wav')),
        ('files', ('003_c.wav', wav, 'audio/wav')),
    ])
    assert res.status_code == 200, res.text
    cues = res.json()['project']['cues']
    assert [c['filename'] for c in cues] == ['002_b.wav', '001_a.wav', '003_c.wav', '004_d.wav']
    assert [c['id'] for c in cues[:2]] == old_ids


@pytest.mark.parametrize('block', [1, 4, 512])
def test_master_mute_and_unmute_are_bounded_sample_ramps(block):
    mx = running_mixer()
    mx.queue(plain(position_deg=315), np.ones(2000, dtype=np.float32))
    mx.render(40)
    mx.master_mute = True
    down = np.concatenate([mx.render(block) for _ in range((40+block-1)//block)])[:, 0]
    assert down[0] > .9, 'ordinary mute is an abrupt step'
    assert np.max(np.abs(np.diff(down))) <= 1/15 + 1e-6
    assert np.all(down[16:] == 0)
    mx.master_mute = False
    up = np.concatenate([mx.render(block) for _ in range((40+block-1)//block)])[:, 0]
    assert up[0] < .1, 'unmute jumps from zero to full gain'
    assert np.max(np.abs(np.diff(up))) <= 1/15 + 1e-6
    assert up[16] == pytest.approx(1)


def test_panic_clears_calibration_delay_before_an_immediate_unmute():
    mx = running_mixer()
    mx.set_calibration([0]*4, [30, 0, 0, 0])
    mx.queue(plain(position_deg=315), np.ones(1000, dtype=np.float32))
    mx.render(40)
    assert np.any(mx._delay_buffers[0])
    mx.panic()
    mx.master_mute = False  # no intermediate muted callback
    assert not np.any(mx.render(100)), 'PANIC leaked pre-panic buffered samples'
