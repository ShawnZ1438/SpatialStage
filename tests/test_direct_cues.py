from io import BytesIO
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from stagespatialcue.server import create_app

def test_direct_cue_controls(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        p=c.post('/api/projects',json={'name':'Controls'}).json();pid=p['id']
        buf=BytesIO();sf.write(buf,np.zeros(48000),48000,format='WAV')
        p=c.post(f'/api/projects/{pid}/upload',files=[('files',(f'{i}.wav',buf.getvalue(),'audio/wav')) for i in range(3)]).json()['project']
        ids=[x['id'] for x in p['cues']]
        for q in p['cues']:q.update(continue_mode='auto_continue',pre_wait_s=3,start_mode='layer')
        c.put(f'/api/projects/{pid}',json=p)
        def arm(i):return c.post('/api/audio/arm',json={'project_id':pid,'index':i})
        def audition(i):return c.post('/api/audio/audition',json={'project_id':pid,'cue_id':ids[i]})
        arm(3)
        assert audition(0).status_code==400
        c.post('/api/simulation/connect')
        assert audition(0).status_code==400
        assert c.get(f'/api/projects/{pid}/preflight').json()['ok']
        c.post('/api/audio/master',json={'mute':False,'db':-30})
        a=audition(1);assert a.status_code==200,a.text
        st=a.json();assert st['next_cue_id']==ids[1]
        assert len(st['mixer']['voices'])==1
        assert st['mixer']['voices'][0]['cue_id']==ids[1]
        assert st['mixer']['voices'][0]['state']=='playing'
        p['cues'].reverse()
        assert c.put(f'/api/projects/{pid}',json=p).status_code==400
        c.post('/api/audio/panic')
        assert arm(0).json()['next_cue_id']==ids[0]
        assert audition(0).status_code==400
        assert c.put(f'/api/projects/{pid}',json=p).status_code==200
        assert c.get(f'/api/projects/{pid}').json()['cues']==p['cues']
        assert arm(0).json()['next_cue_id']==ids[2]
        c.post('/api/audio/master',json={'mute':False,'db':-30})
        assert audition(0).status_code==200
        c.post('/api/audio/stop')
        assert arm(1).json()['next_cue_id']==ids[1]
        c.post('/api/audio/panic')
