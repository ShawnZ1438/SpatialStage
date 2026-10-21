import numpy as np
from stagespatialcue.mixer import Mixer
from stagespatialcue.models import Project, Cue, ModPoint


def cue(**kwargs):
    return Cue(title='test', gain_db=0, fade_in_s=0, fade_out_s=0, **kwargs)


def test_four_channel_render_and_mute():
    mx=Mixer(Project(),sample_rate=1000)
    mx.master_db=0
    mx.queue(cue(position_deg=45),np.ones(100,dtype=np.float32))
    out=mx.render(20)
    assert np.count_nonzero(out)==0  # conservative mute on startup
    mx.master_mute=False
    out=mx.render(20)
    assert out[0,1] == 0
    assert np.all(np.diff(out[:,1]) >= 0)
    assert np.allclose(out[15:,1],1)
    assert np.count_nonzero(out[:,[0,2,3]])==0


def test_replace_transitions_old_voice_to_new():
    mx=Mixer(Project(),sample_rate=1000)
    mx.master_mute=False;mx.master_db=-18
    v1=mx.queue(cue(position_deg=315,start_mode='layer'),np.ones(1000,dtype=np.float32))
    mx.render(100)
    v2=mx.queue(cue(position_deg=135,start_mode='replace',transition_s=0.05),np.ones(200,dtype=np.float32))
    assert v1.stop_frame==100
    assert v1.end_frame==150
    assert v2.start_frame==100
    mx.render(200)
    assert all(v.cue.id != v1.cue.id for v in mx.voices)


def test_queue_waits_for_ends_and_prewait():
    mx=Mixer(Project(),sample_rate=1000)
    v1=mx.queue(cue(start_mode='layer'),np.ones(100,dtype=np.float32))
    v2=mx.queue(cue(start_mode='queue',pre_wait_s=0.025),np.ones(50,dtype=np.float32))
    assert v1.start_frame==0
    assert v2.start_frame==125


def test_modulation_moves_power_between_speakers():
    mx=Mixer(Project(),sample_rate=1000)
    mx.master_mute=False;mx.master_db=-18
    mx.render(20)  # settle master unmute independently of spatial motion
    c=cue(position_deg=45,modulation=[ModPoint(time_s=0,offset_deg=0),ModPoint(time_s=1,offset_deg=90)])
    mx.queue(c,np.ones(1000,dtype=np.float32))
    out=mx.render(1000)
    assert out[0,1]>0 and np.sum(out[0,[0,2,3]])<.0001
    assert out[999,2]>0
    assert np.max(np.abs(np.diff(out[:,1])))<0.003


def test_panic_immediate_mute_and_kills_voices():
    mx=Mixer(Project(),sample_rate=1000)
    mx.queue(cue(),np.ones(100,dtype=np.float32))
    mx.panic()
    assert mx.master_mute
    assert not mx.voices
    assert not np.any(mx.render(30))


def test_speaker_test_only_one_channel():
    mx=Mixer(Project(),sample_rate=48000)
    mx.master_mute=False;mx.master_db=0
    mx.speaker_test(3)
    out=mx.render(2048)
    assert np.max(np.abs(out[:,2]))>0
    assert np.max(np.abs(out[:,[0,1,3]]))==0


def test_lifecycle_records_render_frame_not_wall_clock():
    mx=Mixer(Project(),sample_rate=1000)
    mx.queue(cue(start_mode='layer',pre_wait_s=0.015),np.ones(20,dtype=np.float32))
    mx.render(50)
    records=mx.drain_events()
    assert [e['event'] for e in records]==['cue_audio_start','cue_audio_end']
    assert [e['frame'] for e in records]==[15,35]
    assert not mx.drain_events()
