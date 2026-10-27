from io import BytesIO

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from stagespatialcue.models import Cue, CueLayer, MediaItem, Project
from stagespatialcue.server import create_app
from stagespatialcue.spatial import vbap_gains


@pytest.mark.parametrize('angles', [[0,0,120,240], [0,120,240,360], [0,120,240,359.999], [45,45.001,180,270]])
def test_duplicate_and_wrap_near_duplicate_speakers_rejected(tmp_path, angles):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        p=c.post('/api/projects',json={'name':'geometry'}).json()
        for s,a in zip(p['speakers'],angles): s['angle_deg']=a
        assert c.put('/api/projects/'+p['id'],json=p).status_code==422


def test_360_canonical_persistence_and_render(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        p=c.post('/api/projects',json={'name':'bearing'}).json()
        media=MediaItem()
        p['media']=[media.model_dump()]
        p['cues']=[Cue(layers=[CueLayer(media_id=media.id)]).model_dump()];p['cues'][0]['layers'][0]['position_deg']=360
        result=c.put('/api/projects/'+p['id'],json=p)
        assert result.status_code==200 and result.json()['cues'][0]['layers'][0]['position_deg']==0
        assert c.get('/api/projects/'+p['id']).json()['cues'][0]['layers'][0]['position_deg']==0
        np.testing.assert_array_equal(vbap_gains(360,Project().speakers),vbap_gains(0,Project().speakers))


@pytest.mark.parametrize('route', ['/api/audio/connect','/api/simulation/monitor'])
@pytest.mark.parametrize('failure', ['query','open','start','close'])
def test_device_failures_are_controlled_muted_disconnected(tmp_path,monkeypatch,route,failure):
    import sounddevice as sd
    def query(*args,**kwargs):
        if failure=='query': raise RuntimeError('device disappeared')
        return {'name':'mock','max_output_channels':4}
    class Device:
        def __init__(self,**kwargs):
            if failure=='open': raise sd.PortAudioError('cannot open')
        def start(self): raise sd.PortAudioError('cannot start')
        def stop(self): pass
        def close(self):
            if failure=='close': raise sd.PortAudioError('cannot close')
    monkeypatch.setattr(sd,'query_devices',query)
    monkeypatch.setattr(sd,'check_output_settings',lambda **kw:None)
    monkeypatch.setattr(sd,'OutputStream',Device)
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8765',raise_server_exceptions=False) as c:
        p=c.post('/api/projects',json={'name':'device'}).json()
        c.post('/api/audio/arm',json={'project_id':p['id']})
        assert c.post(route,json={'device_index':-999}).status_code==422
        result=c.post(route,json={'device_index':999})
        assert result.status_code==400, result.text
        assert 'reconnect' in result.json()['detail']
        status=c.get('/api/audio/status').json()
        assert not status['connected'] and status['mixer']['master_mute']
        assert app.state.stage.stream is None
        assert not app.state.stage.mixer.voices


@pytest.mark.parametrize('replacement',[False,True])
def test_media_commit_rereads_edits_made_during_decode(tmp_path,monkeypatch,replacement):
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        p=c.post('/api/projects',json={'name':'before'}).json()
        media=MediaItem(name='original sound')
        project=Project.model_validate(p);project.media=[media];project.cues=[Cue(title='original')]
        app.state.store.save(project)
        def duration(path):
            latest=app.state.store.get(project.id)
            latest.name='edited during upload';latest.cues[0].title='edited cue'
            app.state.store.save(latest)
            return .1
        monkeypatch.setattr('stagespatialcue.server.audio_duration',duration)
        monkeypatch.setattr('stagespatialcue.audio.audio_duration',duration)  # uploads via media_item
        wave=BytesIO();sf.write(wave,np.zeros(4800),48000,format='WAV')
        suffix=f'/media/{media.id}/replace' if replacement else '/upload'
        r=c.post('/api/projects/'+project.id+suffix,files={('file' if replacement else 'files'):('001.wav',wave.getvalue(),'audio/wav')})
        assert r.status_code==200
        latest=app.state.store.get(project.id)
        assert latest.name=='edited during upload' and latest.cues[0].title=='edited cue'
