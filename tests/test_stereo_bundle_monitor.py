"""Stereo width sources, the repository show bundle and the virtual headphone monitor."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from stagespatialcue.audio import decode_audio, media_item
from stagespatialcue.bundle import BUNDLE_ID, sync_bundled_show
from stagespatialcue.mixer import Mixer
from stagespatialcue.models import PathPoint, PlaybackSpec as Cue, Project, Speaker
from stagespatialcue.server import create_app
from stagespatialcue.simulation import VirtualMonitorStream, VirtualRoom
from stagespatialcue.storage import ProjectStore


def corners():
    d = 3 * np.sqrt(2)
    return Project(speakers=[Speaker(name=n, angle_deg=a, distance_m=d, output_channel=c)
                             for n, a, c in [('L', 315, 1), ('R', 45, 2), ('RR', 135, 3), ('RL', 225, 4)]]).speakers


def render(cue, samples, frames=200):
    p = Project(speakers=corners())
    mixer = Mixer(p, sample_rate=1000)
    mixer.master_mute = False
    mixer.master_db = 0
    mixer.render(20)
    mixer.queue(cue, samples)
    return mixer.render(frames)


def write_wav(path, channels, seconds=0.2, rate=44100):
    t = np.arange(int(rate * seconds)) / rate
    data = np.stack([0.1 * np.sin(2 * np.pi * (300 + 100 * i) * t) for i in range(channels)], axis=1)
    sf.write(path, data, rate)
    return path


def test_decode_keeps_stereo_and_resamples(tmp_path):
    audio = decode_audio(write_wav(tmp_path / 's.wav', 2))
    assert audio.shape == (round(0.2 * 48000), 2) and audio.dtype == np.float32
    assert decode_audio(write_wav(tmp_path / 'm.wav', 1)).shape[1] == 1
    assert decode_audio(write_wav(tmp_path / 'q.wav', 4)).shape[1] == 1  # >2 channels: mono


def test_media_item_defaults_stereo_files_to_width(tmp_path):
    item = media_item(write_wav(tmp_path / '003_Car_pass.wav', 2), 'media/003_Car_pass.wav', '003_Car_pass.wav')
    assert (item.name, item.source_channels, item.stereo_mode) == ('Car pass', 2, 'width')
    assert media_item(write_wav(tmp_path / 'bell.wav', 1), 'media/bell.wav', 'bell.wav').stereo_mode == 'mono'


def test_width_places_left_and_right_channels_on_the_front_pair():
    stereo = np.zeros((1000, 2), dtype=np.float32)
    stereo[:, 0] = 1  # signal only in the LEFT channel of the file
    base = dict(gain_db=0, fade_in_s=0, fade_out_s=0, start_mode='layer', position_deg=0)
    wide = render(Cue(stereo_mode='width', stereo_width_deg=90, **base), stereo)[100]
    assert wide[0] == pytest.approx(np.sqrt(.5), abs=1e-4) and abs(wide[1]) < 1e-6  # L -> front-left only
    mono = render(Cue(stereo_mode='mono', **base), stereo)[100]
    assert mono[0] == pytest.approx(mono[1]) and mono[0] == pytest.approx(.5 * np.sqrt(.5), abs=1e-4)


def test_width_follows_stage_map_paths_and_collapses_at_centre():
    stereo = np.ones((1000, 2), dtype=np.float32)
    stereo[:, 1] = -1  # anti-phase L/R: a mono downmix would cancel completely
    centre = Cue(gain_db=0, fade_in_s=0, fade_out_s=0, start_mode='layer', direction_mode='path',
                 path=[PathPoint(time_s=0, x_m=0, y_m=0)], stereo_mode='width', stereo_width_deg=180)
    out = render(centre, stereo)[100]
    assert np.allclose(out, 0, atol=1e-5)  # both sources at the centre: equal on all four
    front = centre.model_copy(update={'path': [PathPoint(time_s=0, x_m=0, y_m=3)]})
    out = render(front, stereo)[100]
    assert out[0] > .4 and out[3] > .4 and out[1] < -.4 and out[2] < -.4  # L left half, R right half


def test_bundle_imports_once_keeps_deletions_and_appends_new_files(tmp_path):
    show = tmp_path / 'show'
    (show / 'audio').mkdir(parents=True)
    write_wav(show / 'audio' / 'BRS_Crowd.wav', 2)
    write_wav(show / 'audio' / '001_Bell.wav', 1)
    (show / 'name.txt').write_text('Black box', encoding='utf-8')
    store = ProjectStore(tmp_path / 'data')
    project = sync_bundled_show(store, show)
    assert project.bundle_id == BUNDLE_ID and project.name == 'Black box'
    assert [m.filename for m in project.media] == ['001_Bell.wav', 'BRS_Crowd.wav']
    assert [c.layers[0].media_id for c in project.cues] == [m.id for m in project.media]  # one cue per file
    crowd = project.media[1]
    assert crowd.stereo_mode == 'width' and store.media_path(project.id, crowd.media_relpath).is_file()
    project.cues.pop(0)  # operator deletes a cue in the app
    store.save(project)
    write_wav(show / 'audio' / 'Door.wav', 1)
    again = sync_bundled_show(store, show)
    assert again.id == project.id and len(store.all()) == 1
    # Later files join the audio library only; cues stay as the operator left them.
    assert [m.filename for m in again.media] == ['001_Bell.wav', 'BRS_Crowd.wav', 'Door.wav']
    assert [c.id for c in again.cues] == [c.id for c in project.cues]
    assert sync_bundled_show(store, tmp_path / 'missing') is None


def impulse_response(room, channel):
    block = np.zeros((4096, 4), dtype=np.float32)
    block[0, channel] = 1
    return room.process(block)


def arrival(signal):
    return int(np.argmax(np.abs(signal) > 1e-4))


def test_virtual_room_centre_left_right_and_rear():
    room = VirtualRoom(corners())
    left_front = impulse_response(room, 0)
    assert np.abs(left_front[:, 0]).sum() > np.abs(left_front[:, 1]).sum()  # CH1 louder in left ear
    assert arrival(left_front[:, 0]) < arrival(left_front[:, 1])            # and earlier there
    room = VirtualRoom(corners())
    right_front, right_rear = impulse_response(room, 1), impulse_response(VirtualRoom(corners()), 2)
    assert np.abs(right_front[:, 1]).sum() > np.abs(right_front[:, 0]).sum()
    assert arrival(right_front[:, 1]) == arrival(right_rear[:, 1])  # centre: equal distance
    # Rear speaker is darker: less sample-to-sample energy in its near-ear response.
    assert np.abs(np.diff(right_rear[:200, 1])).sum() < np.abs(np.diff(right_front[:200, 1])).sum()


def test_virtual_room_off_centre_listener_hears_near_speaker_first_and_louder():
    near, far = VirtualRoom(corners(), pose=(2, 2, 0)), VirtualRoom(corners(), pose=(2, 2, 0))
    ch2 = impulse_response(near, 1)   # front-right speaker, 1.41 m away
    ch4 = impulse_response(far, 3)    # rear-left speaker, 7.07 m away
    assert arrival(ch2.sum(axis=1)) + round((7.07 - 1.41) / 343 * 48000) - 40 < arrival(ch4.sum(axis=1))
    assert np.abs(ch2).max() > 3 * np.abs(ch4).max()


def test_virtual_monitor_stream_and_pose_api(tmp_path, monkeypatch):
    import sounddevice
    monkeypatch.setattr(sounddevice, 'OutputStream', lambda **kw: SimpleNamespace(start=lambda: None, stop=lambda: None, close=lambda: None))
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        p = c.post('/api/projects', json={'name': 'mon'}).json()
        c.post('/api/audio/arm', json={'project_id': p['id']})
        assert c.post('/api/simulation/monitor-pose', json={'x_m': 1, 'y_m': -2, 'head_deg': 450}).status_code == 200
        status = c.post('/api/simulation/monitor', json={'device_index': 0}).json()
        stream = app.state.stage.stream
        assert isinstance(stream, VirtualMonitorStream) and stream.room.pose == (1, -2, 90)
        assert status['simulation']['monitor_mode'] == 'virtual'
        out = np.zeros((512, 2), dtype=np.float32)
        app.state.stage.mixer.master_mute = False
        app.state.stage.mixer.speaker_test(2)
        stream.callback(out, 512, None, None)
        assert np.abs(out).max() > 0 and app.state.stage.audio_error is None
        assert c.post('/api/simulation/monitor', json={'device_index': 0, 'mode': 'sum'}).json()['simulation']['monitor_mode'] == 'sum'
        c.post('/api/audio/disconnect')


def test_repository_show_folder_is_real_audio():
    folder = Path(__file__).resolve().parents[1].joinpath('show', 'audio')
    files = sorted([*folder.glob('*.flac'), *folder.glob('*.wav')])
    if not files:
        pytest.skip('no bundled show audio in this checkout')
    for path in files:
        info = sf.info(path)
        assert info.samplerate in (44100, 48000, 96000) and info.channels == 2
        assert path.stat().st_size < 95 * 1024 * 1024  # GitHub rejects files over 100 MB


def test_bundle_applies_stage_layout_only_when_creating(tmp_path):
    show = tmp_path / 'show'
    (show / 'audio').mkdir(parents=True)
    write_wav(show / 'audio' / 'a.wav', 1)
    (show / 'stage.json').write_text('{"speakers":[' + ','.join(
        f'{{"name":"S{c}","angle_deg":{a},"distance_m":4.2426,"output_channel":{c}}}'
        for a, c in [(315, 1), (45, 2), (135, 3), (225, 4)]) + ']}', encoding='utf-8')
    store = ProjectStore(tmp_path / 'data')
    project = sync_bundled_show(store, show)
    assert [s.distance_m for s in project.speakers] == [4.2426] * 4
    project.speakers[0].trim_db = -2  # later operator edits survive the next launch
    store.save(project)
    assert sync_bundled_show(store, show).speakers[0].trim_db == -2


def test_repository_stage_layout_is_valid():
    path = Path(__file__).resolve().parents[1] / 'show' / 'stage.json'
    if path.is_file():
        import json
        assert len(Project.model_validate(json.loads(path.read_text(encoding='utf-8'))).speakers) == 4
