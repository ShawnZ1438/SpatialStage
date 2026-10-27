from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from stagespatialcue.mixer import Mixer
from stagespatialcue.models import ModPoint, PlaybackSpec, Project
from legacy import with_cues
from stagespatialcue.server import create_app
from stagespatialcue.simulation import SimulationStream, StereoMonitorStream


def test_capture_is_exact_post_master_four_channels_and_bounded():
    stage = SimpleNamespace(mixer=Mixer(Project()))
    stream = SimulationStream(stage)
    stream.max_frames = 1024
    stream.capture(True)
    assert not np.any(stream.step(512))  # starts muted
    stage.mixer.master_mute = False
    stage.mixer.speaker_test(3)
    audible = stream.step(512)
    assert np.any(audible[:, 2]) and not np.any(audible[:, [0, 1, 3]])
    assert not stream.recording and stream.frames == 1024
    data, rate = sf.read(BytesIO(stream.wav()), dtype='float32')
    assert rate == 48000 and data.shape == (1024, 4)
    np.testing.assert_array_equal(data[512:], audible)
    stream.step(512)
    assert stream.frames == 1024


def test_capture_requires_stop_and_nonempty():
    stream = SimulationStream(SimpleNamespace(mixer=Mixer(Project())))
    with pytest.raises(ValueError, match='empty'):
        stream.wav()
    stream.capture(True)
    with pytest.raises(ValueError, match='Stop'):
        stream.wav()


def test_simulation_api_go_stop_save_capture(tmp_path, monkeypatch):
    # Deterministic stepping; no sounddevice import or hardware stream.
    monkeypatch.setattr(SimulationStream, 'start', lambda s: setattr(s, 'active', True))
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        project = app.state.store.create('sim')
        path = app.state.store.directory(project.id) / 'tone.wav'
        sf.write(path, np.full(4800, .1, dtype=np.float32), 48000)
        rel, name = app.state.store.add_file(project.id, path, '001_tone.wav')
        project = with_cues(project, [dict(filename=name, media_relpath=rel, fade_in_s=0, fade_out_s=0)])
        app.state.store.save(project)
        pid = project.id
        assert client.post('/api/audio/arm', json={'project_id':pid}).status_code == 200
        result = client.post('/api/simulation/connect').json()
        assert result['mixer']['master_mute'] and result['output_mode'] == 'simulation'
        assert client.post('/api/audio/go', json={'project_id':pid}).status_code == 400
        assert client.get(f'/api/projects/{pid}/preflight').json()['ok']
        client.post('/api/audio/master', json={'mute':False, 'db':-18})
        client.post('/api/simulation/capture', json={'recording':True})
        assert client.post('/api/audio/go', json={'project_id':pid}).status_code == 200
        assert client.post('/api/audio/go', json={'project_id':pid}).status_code == 400
        stream = app.state.stage.stream
        stream.step(1024)
        project.global_rotation_deg = 270
        assert client.put(f'/api/projects/{pid}', json=project.model_dump()).status_code == 200
        client.post('/api/audio/stop'); client.post('/api/audio/stop')
        stream.step(2400)
        assert not app.state.stage.mixer.voices
        client.post('/api/simulation/capture', json={'recording':False})
        data, rate = sf.read(BytesIO(client.get('/api/simulation/capture.wav').content))
        assert rate == 48000 and data.shape == (3424,4) and np.max(np.abs(data)) > 0
        assert client.post('/api/audio/panic').json()['mixer']['master_mute']
        assert client.post('/api/audio/disconnect').json()['connected'] is False
        assert client.get('/api/simulation/capture.wav').status_code == 400


def test_monitor_solo_gain_and_capture_do_not_change_stems(monkeypatch):
    import sounddevice
    monkeypatch.setattr(sounddevice, 'OutputStream', lambda **kw: SimpleNamespace())
    stage = SimpleNamespace(mixer=Mixer(Project()), xruns=0, audio_error=None)
    stream = StereoMonitorStream(stage, 0)
    block = np.tile(np.array([.1,.2,.3,.4], dtype=np.float32), (512,1))
    monkeypatch.setattr(stage.mixer, 'render', lambda frames: block.copy())
    stream.gains = np.array([0,0,.5,0], dtype=np.float32)
    stream.previous_gains = stream.gains.copy()
    stream.capture(True)
    out = np.empty((512,2), dtype=np.float32)
    stream.callback(out,512,None,False)
    np.testing.assert_allclose(out, .3*.5*.05)
    np.testing.assert_array_equal(stream.blocks[0], block)
    stream.gains = np.zeros(4, dtype=np.float32)
    stream.callback(out,512,None,False)
    assert np.all(out[-1] == 0)


def test_status_bearing_includes_cue_and_global_envelopes():
    cue = PlaybackSpec(position_deg=270, modulation=[ModPoint(time_s=0,offset_deg=0), ModPoint(time_s=1,offset_deg=90)])
    mix = Mixer(Project(global_rotation_deg=45,global_envelope_enabled=True,
                        global_modulation=[ModPoint(time_s=0,offset_deg=10)]))
    mix.queue(cue,np.zeros(96000,dtype=np.float32))
    mix.render(48000)
    assert mix.status()['voices'][0]['position_deg'] == 55


@pytest.mark.parametrize('channel', [1,2,3,4])
def test_capture_channel_identity_and_clipping(channel):
    mix = Mixer(Project())
    mix.master_mute = False
    mix.master_db = 6
    for _ in range(20):
        mix.speaker_test(channel)
    stream = SimulationStream(SimpleNamespace(mixer=mix))
    stream.capture(True)
    block = stream.step(4800)
    assert np.max(np.abs(block[:,channel-1])) == 1
    assert mix.peak_over_count > 0
    assert not np.any(np.delete(block,channel-1,axis=1))
    assert np.isfinite(block).all()


def test_monitor_peak_guard_reports_overload():
    stream = StereoMonitorStream.__new__(StereoMonitorStream)
    stream.monitor_peak_over_count = 0
    source = np.array([[2., -2.], [.1, -.1]], dtype=np.float32)
    out = stream.limit_monitor(source)
    assert np.max(np.abs(out)) <= .980001
    assert stream.monitor_peak_over_count == 1
    np.testing.assert_allclose(source, [[2., -2.], [.1, -.1]])
