from io import BytesIO

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from legacy import cue_files, with_cues
from stagespatialcue.server import create_app
from stagespatialcue.models import Project


def test_projects_and_upload_sort_and_export(tmp_path):
    app=create_app(tmp_path)
    client=TestClient(app,base_url="http://127.0.0.1:8765")
    p=client.post('/api/projects',json={'name':'Experiment A'}).json()
    assert p['name']=='Experiment A'
    assert len(client.get('/api/projects').json())==1
    wave=BytesIO()
    sf.write(wave,np.zeros(4800,dtype=np.float32),48000,format='WAV')
    data=wave.getvalue()
    upload=client.post(f"/api/projects/{p['id']}/upload",files=[
        ('files',('002_Background.wav',data,'audio/wav')),
        ('files',('001_Whisper.wav',data,'audio/wav')),
        ('files',('._hidden.wav',data,'audio/wav')),
    ])
    assert upload.status_code==200,upload.text
    result=upload.json()
    assert result['added']==2
    media=result['project']['media']
    assert media[0]['filename']=='001_Whisper.wav' and media[0]['name']=='Whisper'
    assert media[0]['duration_s']==.1
    assert media[1]['filename']=='002_Background.wav'
    assert cue_files(result['project'])==['001_Whisper.wav','002_Background.wav']
    saved=client.get(f"/api/projects/{p['id']}").json()
    assert len(saved['cues'])==2
    library_only=client.post(f"/api/projects/{p['id']}/upload?create_cues=false",
                             files=[('files',('003_Rain.wav',data,'audio/wav'))]).json()
    assert len(library_only['project']['media'])==3 and len(library_only['project']['cues'])==2
    assert library_only['cue_ids']==[] and len(library_only['media_ids'])==1
    export=client.get(f"/api/projects/{p['id']}/export")
    assert export.status_code==200 and export.content[:2]==b'PK'
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200


def test_safe_validation_and_operator_state(tmp_path):
    client=TestClient(create_app(tmp_path),base_url="http://127.0.0.1:8765")
    p=client.post('/api/projects',json={'name':'Show'}).json()
    pid=p['id']
    assert client.post('/api/audio/arm',json={'project_id':pid,'index':0}).status_code==200
    assert client.get('/api/audio/status').json()['mixer']['master_mute']
    assert client.post('/api/audio/go',json={'project_id':pid}).status_code==400
    assert client.post('/api/audio/test',json={'channel':5}).status_code==422
    p['speakers'][0]['output_channel']=p['speakers'][1]['output_channel']
    assert client.put(f'/api/projects/{pid}',json=p).status_code==422
    p['speakers'][0]['output_channel']=1
    assert client.put(f'/api/projects/{pid}',json=p).status_code==200
    assert client.get('/api/projects/../etc/passwd').status_code in {404,400}
    assert client.post('/api/projects',headers={'Origin':'https://malicious.example'},json={'name':'bad'}).status_code==403


def test_auto_continue_and_follow_are_scheduled_by_sample_frame(tmp_path):
    from stagespatialcue.audio import StageController
    from stagespatialcue.storage import ProjectStore
    store=ProjectStore(tmp_path)
    project=store.create('Chain')
    fs=48000
    path=store.directory(project.id)/'media'
    path.mkdir()
    for idx in (1,2,3):
        sf.write(path/f'{idx}.wav',np.zeros(4800,dtype=np.float32),fs)
    c1=dict(title='A',filename='1.wav',media_relpath='media/1.wav',duration_s=.1,start_mode='layer',continue_mode='auto_continue',post_wait_s=.02,fade_in_s=0,fade_out_s=0)
    c2=dict(title='B',filename='2.wav',media_relpath='media/2.wav',duration_s=.1,start_mode='layer',continue_mode='auto_follow',post_wait_s=.03,fade_in_s=0,fade_out_s=0)
    c3=dict(title='C',filename='3.wav',media_relpath='media/3.wav',duration_s=.1,start_mode='layer',fade_in_s=0,fade_out_s=0)
    project=store.save(with_cues(project,[c1,c2,c3]))
    stage=StageController(store)
    stage.arm(project.id)
    stage.stream=type('FakeStream',(),{'active':True})()
    stage.mixer.master_mute=False
    stage.preflight(project.id)
    status=stage.go(project.id)
    assert status['next_index']==3
    assert [v.start_frame for v in stage.mixer.voices]==[0,int(.02*fs),int(.15*fs)]
    stage.mixer.render(10000)
    stage.status()
    assert not (store.directory(project.id)/'events.jsonl').exists()  # default: no research/participant logs
