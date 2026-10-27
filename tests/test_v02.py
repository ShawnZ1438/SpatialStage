"""SpatialStage v0.2 regression suite: geometry, envelopes and live transitions."""
from io import BytesIO

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from stagespatialcue.mixer import Mixer
from stagespatialcue.models import PlaybackSpec, Project, DirectionADSR, ModPoint
from legacy import with_cues
from stagespatialcue.server import create_app
from stagespatialcue.spatial import (
    adsr_offsets, calibration_preview, polar_from_xy, xy_from_polar, vbap_gains,
)


def tone(n=1000):
    return np.ones(n,dtype=np.float32)


def plain_cue(**kwargs):
    return PlaybackSpec(gain_db=0,fade_in_s=0,fade_out_s=0,**kwargs)


def layered(project, **kwargs):
    """Project with one single-layer cue; returns it and that layer's playback spec."""
    p = with_cues(project, [dict(gain_db=0, fade_in_s=0, fade_out_s=0, filename='a.wav',
                                 media_relpath='media/a.wav', **kwargs)])
    return p, p.cue_specs(p.cues[0])[0]


def test_stage_center_geometry_and_labels():
    p=Project()
    assert [(s.output_channel,s.angle_deg) for s in p.speakers]==[(1,315),(2,45),(3,135),(4,225)]
    for s in p.speakers:
        x,y=xy_from_polar(s.angle_deg,s.distance_m)
        angle,distance=polar_from_xy(x,y)
        assert np.isclose(angle,s.angle_deg)
        assert np.isclose(distance,s.distance_m)
    assert np.allclose(vbap_gains(270,p.speakers),[[0.70710678,0,0,0.70710678]],atol=1e-5)


def test_calibration_is_theoretical_and_center_aligned():
    p=Project()
    p.speakers[0].distance_m=2
    hints=calibration_preview(p.speakers)
    assert hints[0]['suggested_extra_delay_ms'] == round(1000/343,2)
    assert hints[1]['suggested_extra_delay_ms'] == 0
    assert hints[0]['suggested_relative_gain_db'] < 0
    assert hints[0]['pointing_at_center_deg'] == 135


def test_direction_adsr_attack_decay_sustain_release():
    e=DirectionADSR(attack_s=1,peak_offset_deg=90,decay_s=1,sustain_offset_deg=45,release_s=2,release_offset_deg=0)
    t=np.array([0,.5,1,1.5,2,5,8,9,10])
    assert np.allclose(adsr_offsets(t,10,e),[0,45,90,67.5,45,45,45,22.5,0])
    short=adsr_offsets(np.array([0,.5,1]),1,e)
    assert np.isfinite(short).all() and short[-1]==0


def test_global_show_offset_and_manual_rotation_affect_live_voice():
    p=Project(global_envelope_enabled=True,global_modulation=[ModPoint(time_s=0,offset_deg=0),ModPoint(time_s=.1,offset_deg=90)])
    p,spec=layered(p,position_deg=45,start_mode='layer')
    mx=Mixer(p,sample_rate=1000)
    mx.master_mute=False;mx.master_db=0
    mx.render(20)  # master ramp is distinct from cue transition
    mx.queue(spec,tone(1000))
    out=mx.render(150)
    assert out[0,1]>.99 and np.count_nonzero(out[0,[0,2,3]])==0
    assert out[140,2]>.99 and out[140,1]<.01
    p.global_rotation_deg=90
    mx.update_project(p)
    rotated=mx.render(50)
    assert rotated[-1,3]>.99  # 45 + global 90 + show 90 = 225


def test_editing_live_cue_retargets_existing_voice_without_restarting_samples():
    p,spec=layered(Project(),position_deg=45,start_mode='layer'); mx=Mixer(p,sample_rate=1000)
    mx.master_mute=False;mx.master_db=0
    voice=mx.queue(spec,tone(1000))
    mx.render(40)
    revised=p.model_copy(deep=True);revised.cues[0].layers[0].position_deg=135
    mx.update_project(revised)
    out=mx.render(100)
    assert voice.start_frame==0 and mx.frame==140
    assert out[-1,2]>.99 and out[-1,1]<.01


def test_cut_go_bypasses_queue_and_prewait_with_short_declick():
    mx=Mixer(Project(auto_replace=True),sample_rate=1000)
    v1=mx.queue(plain_cue(start_mode='layer'),tone(1000))
    mx.render(100)
    c2=plain_cue(start_mode='queue',pre_wait_s=7,transition_s=3)
    v2=mx.queue(c2,tone(400),force_cut=True)
    assert v2.start_frame==100
    assert v1.stop_frame==100 and v1.stop_fade_frames==5
    assert v1.end_frame==105
    assert v2.start_fade_frames==5


def test_no_transition_applied_when_starting_into_silence():
    mx=Mixer(Project(),sample_rate=1000);mx.master_mute=False;mx.master_db=0
    mx.render(20)  # master ramp is distinct from cue transition
    mx.queue(plain_cue(position_deg=45,start_mode='replace',transition_s=2.5),tone(100))
    out=mx.render(10)
    assert out[0,1]>.99


def test_server_calibration_preview_and_cue_audio_swap(tmp_path):
    app=create_app(tmp_path)
    client=TestClient(app,base_url='http://127.0.0.1:8765')
    project=client.post('/api/projects',json={'name':'Sound show'}).json()
    pid=project['id']
    preview=client.post('/api/calibration/preview',json=project)
    assert preview.status_code==200 and not preview.json()['measured']
    assert not preview.json()['delay_applied']
    wave=BytesIO();sf.write(wave,np.zeros(4800,dtype=np.float32),48000,format='WAV')
    uploaded=client.post(f'/api/projects/{pid}/upload',files=[('files',('001_car.wav',wave.getvalue(),'audio/wav'))]).json()
    media=uploaded['project']['media'][0]
    assert uploaded['project']['cues'][0]['layers'][0]['media_id']==media['id']
    swapped=BytesIO();sf.write(swapped,np.zeros(9600,dtype=np.float32),48000,format='WAV')
    res=client.post(f'/api/projects/{pid}/media/{media["id"]}/replace',files={'file':('engine.wav',swapped.getvalue(),'audio/wav')})
    assert res.status_code==200,res.text
    assert res.json()['media']['duration_s']==.2
    assert res.json()['project']['media'][0]['filename']=='engine.wav'
    from stagespatialcue import __version__
    assert client.get('/api/health').json()['version']==__version__


def test_hot_repatch_requires_mute(tmp_path):
    app=create_app(tmp_path)
    client=TestClient(app,base_url='http://127.0.0.1:8765')
    p=client.post('/api/projects',json={'name':'Show'}).json()
    stage=app.state.stage
    stage.arm(p['id']);stage.stream=type('FakeStream',(),{'active':True})()
    stage.mixer.master_mute=False
    p['speakers'][0]['trim_db']=-3
    blocked=client.put('/api/projects/'+p['id'],json=p)
    assert blocked.status_code==400
    assert app.state.store.get(p['id']).speakers[0].trim_db==0
    stage.mixer.master_mute=True
    allowed=client.put('/api/projects/'+p['id'],json=p)
    assert allowed.status_code==200
