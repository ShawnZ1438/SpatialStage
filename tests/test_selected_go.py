from types import SimpleNamespace
import pytest
from test_cue_layers import layered_stage
from stagespatialcue.models import Cue, CueLayer


def prepared(tmp_path):
    stage,p=layered_stage(tmp_path,[{}])
    p.cues += [Cue(title=str(i),layers=[CueLayer(media_id=p.media[0].id)]) for i in range(1,4)]
    stage.store.save(p);stage.sync(p);stage.preflight(p.id)
    return stage,p

@pytest.mark.parametrize('index',[0,2,3])
def test_selected_go_rebases_and_repeated_go_continues(tmp_path,index):
    s,p=prepared(tmp_path)
    s.next_index=len(p.cues)
    s.prepare_go(p.id,p.cues[index].id)
    assert s.next_index==len(p.cues)
    s.go(p.id,cue_id=p.cues[index].id)
    assert s.next_index==index+1
    assert s.mixer.voices[-1].cue.group_id==p.cues[index].id
    if index+1<len(p.cues):
        s.go(p.id);assert s.next_index==index+2
    else:
        with pytest.raises(ValueError,match='End of cue list'):s.go(p.id)
    s.stream=None
    s.shutdown()


def test_jump_cancels_old_pending_chain_but_overlap_does_not_steal_next(tmp_path):
    s,p=prepared(tmp_path)
    p.cues[0].continue_mode='auto_follow';p.cues[0].post_wait_s=2
    p.cues[1].pre_wait_s=.5
    p.cues[2].continue_mode='auto_continue';p.cues[2].post_wait_s=.3
    p.cues[3].pre_wait_s=.2
    s.store.save(p);s.sync(p);s.prepare_go(p.id,p.cues[0].id)
    s.go(p.id);s.mixer.render(100)
    assert s.next_index==2
    old_pending=[v for v in s.mixer.voices if v.cue.group_id==p.cues[1].id]
    s.play_cue(p.id,p.cues[3].id)
    assert s.next_index==2 and all(v in s.mixer.voices for v in old_pending)
    s.go(p.id,cue_id=p.cues[2].id)
    assert s.next_index==4 and not any(v in s.mixer.voices for v in old_pending)
    chain=[v for v in s.mixer.voices if v.chain_id and v.cue.group_id in [p.cues[2].id,p.cues[3].id]]
    assert chain[-1].start_frame-chain[0].start_frame==24000
    assert any(v.chain_id is None for v in s.mixer.voices)
    s.stream=None
    s.shutdown()


def test_selected_go_failure_is_atomic_and_respects_safety(tmp_path):
    s,p=prepared(tmp_path)
    for failure in ['mute','device','missing']:
        s.mixer.master_mute=failure=='mute'
        s.stream=SimpleNamespace(active=failure!='device')
        with pytest.raises(ValueError):s.go(p.id,cue_id='missing' if failure=='missing' else p.cues[2].id)
        assert s.next_index==0 and not s.mixer.voices
    s.stream=None
    s.shutdown()


def test_selected_queue_keeps_wait_and_start_mode(tmp_path):
    s,p=prepared(tmp_path)
    p.cues[2].start_mode='queue';p.cues[2].pre_wait_s=.25
    s.store.save(p);s.sync(p)
    s.play_cue(p.id,p.cues[0].id)
    end=max(v.end_frame for v in s.mixer.voices)
    s.go(p.id,cue_id=p.cues[2].id)
    assert s.mixer.voices[-1].start_frame==end+12000
    assert s.next_index==3
    s.stream=None;s.shutdown()


def test_selected_go_decode_failure_keeps_old_pending_chain(tmp_path,monkeypatch):
    s,p=prepared(tmp_path)
    p.cues[0].continue_mode='auto_follow';p.cues[0].post_wait_s=2
    s.store.save(p);s.sync(p);s.go(p.id)
    old=list(s.mixer.voices);next_id=s.next_cue_id
    def unavailable(*args,**kwargs):
        raise ValueError('Audio not ready')
    monkeypatch.setattr(s,'_sources',unavailable)
    with pytest.raises(ValueError,match='not ready'):s.go(p.id,cue_id=p.cues[2].id)
    assert s.mixer.voices==old and s.next_cue_id==next_id
    s.stream=None;s.shutdown()
