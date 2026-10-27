"""Stage-map XY paths, centre spread and stored spatial presets."""
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stagespatialcue.mixer import Mixer
from stagespatialcue.models import (Cue, CueLayer, LayerPreset, MediaItem, PathPoint, PlaybackSpec, Project,
                                   SpatialPreset, Speaker)
from stagespatialcue.server import create_app
from stagespatialcue.spatial import path_xy, point_gains, vbap_gains


def corner_speakers(d=3.0):
    """6 m x 6 m room, one speaker per corner, default L/R/RR/RL routing."""
    return Project(speakers=[
        Speaker(name='L', angle_deg=315, distance_m=d*np.sqrt(2), output_channel=1),
        Speaker(name='R', angle_deg=45, distance_m=d*np.sqrt(2), output_channel=2),
        Speaker(name='RR', angle_deg=135, distance_m=d*np.sqrt(2), output_channel=3),
        Speaker(name='RL', angle_deg=225, distance_m=d*np.sqrt(2), output_channel=4),
    ]).speakers


def test_point_on_speaker_is_that_speaker_and_centre_is_all_four():
    speakers = corner_speakers()
    assert np.allclose(point_gains(3, 3, speakers)[0], [0, 1, 0, 0], atol=1e-6)
    assert np.allclose(point_gains(-3, -3, speakers)[0], [0, 0, 0, 1], atol=1e-6)
    assert np.allclose(point_gains(0, 0, speakers)[0], [.5, .5, .5, .5], atol=1e-6)


def test_edge_points_match_pairwise_vbap_and_power_is_constant():
    speakers = corner_speakers()
    edge = np.linspace(-3, 3, 13)  # the square joining the corner speakers
    x = np.concatenate([edge, np.full(13, 3.0), edge, np.full(13, -3.0)])
    y = np.concatenate([np.full(13, 3.0), edge, np.full(13, -3.0), edge])
    angles = np.rad2deg(np.arctan2(x, y))
    assert np.allclose(point_gains(x, y, speakers), vbap_gains(angles, speakers), atol=1e-5)
    assert np.allclose(point_gains(1.5*x, 1.5*y, speakers), vbap_gains(angles, speakers), atol=1e-5)
    grid = np.linspace(-4, 4, 17)
    gx, gy = np.meshgrid(grid, grid)
    gains = point_gains(gx.ravel(), gy.ravel(), speakers)
    assert np.allclose(np.sum(gains**2, axis=1), 1, atol=1e-5)


def test_path_through_centre_has_no_jump_between_opposite_pairs():
    speakers = corner_speakers()
    x = np.linspace(-3, 3, 6001)  # left wall to right wall through the actor
    gains = point_gains(x, np.zeros_like(x), speakers)
    assert np.max(np.abs(np.diff(gains, axis=0))) < 0.01
    assert gains[0, 0] == pytest.approx(gains[0, 3]) and gains[0, 1] < 1e-6
    assert gains[-1, 1] == pytest.approx(gains[-1, 2]) and gains[-1, 0] < 1e-6


def test_rotation_turns_the_map_like_global_rotation():
    speakers = corner_speakers()
    front = point_gains(0, 4.24, speakers, rotation_deg=45)[0]
    assert np.argmax(front) == 1  # 0° + 45° -> front-right speaker


def test_path_interpolates_and_holds_ends():
    pts = [PathPoint(time_s=1, x_m=-2, y_m=0), PathPoint(time_s=3, x_m=2, y_m=2)]
    x, y = path_xy(np.array([0, 1, 2, 3, 9]), pts)
    assert np.allclose(x, [-2, -2, 0, 2, 2]) and np.allclose(y, [0, 0, 1, 2, 2])


def test_path_mode_requires_points_and_sorts_them():
    with pytest.raises(ValidationError):
        CueLayer(media_id='m', direction_mode='path', path=[])
    layer = CueLayer(media_id='m', direction_mode='path',
                     path=[PathPoint(time_s=2, x_m=1, y_m=0), PathPoint(time_s=0, x_m=0, y_m=1)])
    assert [p.time_s for p in layer.path] == [0, 2]


def test_mixer_moves_a_path_cue_from_left_to_right():
    p = Project(speakers=corner_speakers())
    cue = PlaybackSpec(gain_db=0, fade_in_s=0, fade_out_s=0, start_mode='layer', direction_mode='path',
                       path=[PathPoint(time_s=0, x_m=-3, y_m=0), PathPoint(time_s=1, x_m=3, y_m=0)])
    mixer = Mixer(p, sample_rate=1000)
    mixer.master_mute = False
    mixer.master_db = 0
    mixer.render(20)  # settle the master ramp
    mixer.queue(cue, np.ones(1000, dtype=np.float32))
    out = mixer.render(1000)
    start, end = out[20], out[-1]
    assert start[0] > .6 and start[3] > .6 and start[1] < .05
    assert end[1] > .6 and end[2] > .6 and end[0] < .05
    assert np.allclose(np.sum(out[30:]**2, axis=1), 1, atol=.02)


def test_status_reports_live_path_position():
    p = Project(speakers=corner_speakers())
    cue = PlaybackSpec(direction_mode='path', path=[PathPoint(time_s=0, x_m=0, y_m=2), PathPoint(time_s=1, x_m=2, y_m=0)])
    mixer = Mixer(p, sample_rate=1000)
    mixer.queue(cue, np.ones(1000, dtype=np.float32))
    mixer.render(500)
    voice = mixer.status()['voices'][0]
    assert voice['position_xy'] == [1.0, 1.0] and voice['position_deg'] == 45


def test_preset_and_path_survive_project_save(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8765')
    project = client.post('/api/projects', json={'name': 'perform'}).json()
    media = MediaItem(name='wind')
    layer = CueLayer(media_id=media.id, direction_mode='path', path=[PathPoint(time_s=0, x_m=1, y_m=2)])
    cue = Cue(layers=[layer])
    cue.spatial_preset = SpatialPreset(layers=[LayerPreset(layer_id=layer.id, direction_mode='path', path=layer.path)],
                                       stored_at='2026-10-26T00:00:00Z')
    project['media'] = [media.model_dump(mode='json')]
    project['cues'] = [cue.model_dump(mode='json')]
    saved = client.put(f"/api/projects/{project['id']}", json=project)
    assert saved.status_code == 200, saved.text
    again = client.get(f"/api/projects/{project['id']}").json()['cues'][0]
    assert again['layers'][0]['path'] == [{'time_s': 0, 'x_m': 1, 'y_m': 2}]
    assert again['spatial_preset']['layers'][0]['direction_mode'] == 'path'
    assert again['spatial_preset']['layers'][0]['layer_id'] == layer.id
