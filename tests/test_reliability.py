"""Additional guardrails adjacent to the P0/P1 fixes; simulated devices only."""
import asyncio
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from types import SimpleNamespace
from zipfile import ZipFile

import numpy as np
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from stagespatialcue.http_safety import RequestSizeLimit
from stagespatialcue.models import Cue, Project
from stagespatialcue.server import create_app
from test_regressions import make_chain, plain, running_mixer


def test_next_tracks_identity_through_reorder_and_import(tmp_path):
    stage, p = make_chain(tmp_path)
    stage.arm(p.id, cue_id=p.cues[1].id)
    target = stage.next_cue_id
    p.cues.reverse()
    stage.store.save(p)
    stage.sync(p)
    assert stage.next_cue_id == target and stage.status()['next_index'] == 0
    p.cues.insert(0, Cue(title='new row'))
    stage.store.save(p)
    stage.sync(p)
    assert stage.next_cue_id == target and stage.status()['next_index'] == 1


def test_deleting_next_requires_explicit_rearm(tmp_path):
    stage, p = make_chain(tmp_path)
    stage.arm(p.id, cue_id=p.cues[1].id)
    p.cues.pop()
    stage.store.save(p)
    stage.sync(p)
    assert stage.status()['needs_rearm']
    assert stage.next_cue_id is None
    with pytest.raises(ValueError, match='removed'):
        stage.go(p.id)
    assert not stage.mixer.voices
    stage.arm(p.id, cue_id=p.cues[0].id)
    assert not stage.needs_rearm


def test_arm_accepts_id_and_rejects_missing_id(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    project = app.state.store.create('ID arm')
    project.cues = [Cue(), Cue()]
    app.state.store.save(project)
    result = client.post('/api/audio/arm', json={'project_id':project.id,'cue_id':project.cues[1].id})
    assert result.status_code == 200
    assert result.json()['next_cue_id'] == project.cues[1].id
    assert client.post('/api/audio/arm', json={'project_id':project.id,'cue_id':'missing'}).status_code == 400


def test_cold_go_rejects_immediately_never_decodes_or_partially_schedules(tmp_path, monkeypatch):
    stage, p = make_chain(tmp_path)
    stage._loader.shutdown(wait=True)
    stage.cache.clear()
    def forbidden(*args):
        raise AssertionError('GO called the decoder')
    monkeypatch.setattr('stagespatialcue.audio.decode_audio', forbidden)
    target = stage.next_cue_id
    with pytest.raises(ValueError, match='not ready'):
        stage.go(p.id)
    assert stage.next_cue_id == target
    assert not stage.mixer.voices


def test_decoder_does_not_hold_controller_lock(tmp_path, monkeypatch):
    stage, p = make_chain(tmp_path, ('manual', 'manual'), (0,0))
    stage._loader.shutdown(wait=True)
    from concurrent.futures import ThreadPoolExecutor
    stage._loader = ThreadPoolExecutor(max_workers=1)
    stage.cache.clear()
    entered, release = Event(), Event()
    def slow_decode(*args):
        entered.set()
        assert release.wait(4), 'test failed to release simulated decoder'
        return np.ones(4800, dtype=np.float32)
    monkeypatch.setattr('stagespatialcue.audio.decode_audio', slow_decode)
    try:
        stage.arm(p.id, cue_id=p.cues[1].id)
        assert entered.wait(2)
        assert stage.lock.acquire(blocking=False), 'decoder holds controller lock'
        stage.lock.release()
        assert stage.status()['preparing']
        with pytest.raises(ValueError, match='not ready'):
            stage.go(p.id)
    finally:
        release.set()
        stage._loader.shutdown(wait=True)
    assert stage.status()['ready']


def test_inactive_stream_latches_mute_and_rejects_go(tmp_path):
    stage, p = make_chain(tmp_path)
    stage.go(p.id)
    stage.stream.active = False
    status = stage.status()
    assert not status['connected']
    assert status['error'] and status['mixer']['master_mute']
    assert not stage.mixer.voices
    with pytest.raises(ValueError, match='Reconnect'):
        stage.go(p.id)


@pytest.mark.parametrize('field,value', [('fade_in_s', 2), ('fade_out_s', 4)])
def test_live_fade_edits_are_smoothed_without_restarting_audio(field, value):
    mx = running_mixer()
    cue = plain(position_deg=315, start_mode='layer')
    project = Project(cues=[cue])
    mx.update_project(project)
    voice = mx.queue(cue, np.ones(5000,dtype=np.float32))
    before = mx.render(1500)
    edited = project.model_copy(deep=True)
    setattr(edited.cues[0], field, value)
    mx.update_project(edited)
    output = mx.render(40)
    assert output[0,0] == pytest.approx(before[-1,0],abs=1e-6)
    assert np.max(abs(np.diff(output[:,0]))) < .03
    assert voice.start_frame == 30


def test_future_replacements_do_not_erase_earlier_fade_schedule():
    mx = running_mixer()
    a = mx.queue(plain(position_deg=315),np.ones(6000,dtype=np.float32))
    mx.queue(plain(position_deg=45,transition_s=2),np.ones(3000,dtype=np.float32),anchored_frame=1030)
    mx.queue(plain(position_deg=135,transition_s=2),np.ones(3000,dtype=np.float32),anchored_frame=2030)
    out = mx.render(3100)
    assert out[2000,0] == pytest.approx(.5,abs=.002)
    assert a.end_frame == 3030  # never extended to 4030


def test_project_exports_exclude_diagnostics_and_temporary_files(tmp_path):
    app = create_app(tmp_path)
    store = app.state.store
    p = store.create('Clean backup')
    folder = store.directory(p.id)
    (folder/'events.jsonl').write_text('operator private log')
    (folder/'.save-stray').write_text('temporary data')
    (folder/'autocal').mkdir()
    (folder/'autocal'/'config.json').write_text('{}')
    with store.export_zip(p.id) as stream, ZipFile(stream) as archive:
        assert set(archive.namelist()) == {'project.json','autocal/config.json'}


def test_importing_server_does_not_create_project_directory(tmp_path):
    data = tmp_path/'not-created'
    env = {**os.environ, 'STAGE_SPATIAL_DATA':str(data)}
    subprocess.run([sys.executable,'-c','import stagespatialcue.server'],env=env,check=True)
    assert not data.exists()


def test_foreign_localhost_ports_and_null_origin_are_rejected(tmp_path):
    client = TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765')
    for origin in ['http://localhost:3000','http://127.0.0.1:9999','null','https://localhost:8765']:
        assert client.post('/api/projects',headers={'Origin':origin},json={'name':'bad'}).status_code==403
    assert client.post('/api/projects',headers={'Origin':'http://localhost:8765'},json={'name':'ok'}).status_code==200


def test_body_limit_rejects_content_length_before_reading():
    calls = []
    async def app(*args):
        calls.append(True)
    middleware = RequestSizeLimit(app, max_bytes=100)
    messages = []
    async def receive():
        raise AssertionError('body must not be read')
    async def send(message):
        messages.append(message)
    asyncio.run(middleware({'type':'http','method':'POST','headers':[(b'content-length',b'101')]},receive,send))
    assert not calls and messages[0]['status'] == 413


def test_body_limit_counts_chunked_requests():
    app = FastAPI()
    app.add_middleware(RequestSizeLimit,max_bytes=20)
    @app.post('/')
    async def body(request: Request):
        return {'bytes':len(await request.body())}
    client = TestClient(app)
    response = client.post('/',content=iter([b'1234567890']*3))
    assert response.status_code == 413
