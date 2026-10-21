"""Deterministic tests; no hardware or real microphone is used."""
import json
import sys
import types
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from stagespatialcue.autocal import AutoCalConfig, analyze_channel, make_stimulus, recommendations
from stagespatialcue.mixer import Mixer, SAMPLE_RATE
from stagespatialcue.models import Project
from stagespatialcue.server import create_app


def client_and_app(tmp_path, monkeypatch):
    sd = types.ModuleType("sounddevice")
    monkeypatch.setitem(sys.modules,"sounddevice",sd)

    def fake_devices(which=None):
        devices = [
            {'name': 'XLR input on shared 4-out interface', 'max_input_channels': 2, 'max_output_channels': 4},
            {'name': 'Stereo headphones', 'max_input_channels': 0, 'max_output_channels': 2},
        ]
        return devices if which is None else devices[which]

    sd.query_devices = fake_devices
    app = create_app(tmp_path)
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    project = client.post('/api/projects', json={'name': 'Calibration test'}).json()
    app.state.stage.arm(project['id'])
    return client, app, project['id']


def inject_fake_measurement(app, noise=1e-6, clip=False):
    gains = [.2, .4, .25, .3]
    lags = [560, 850, 690, 750]
    rng = np.random.default_rng(113)

    def capture(out, config, samplerate):
        ch = int(np.flatnonzero(np.max(np.abs(out), axis=0) > 0)[0])
        x = out[:, ch]
        delay = lags[ch]
        y = np.zeros(len(x), dtype=np.float64)
        y[delay:] = x[:-delay] * gains[ch]
        y += rng.normal(0, noise, len(y))
        if clip:
            y[1000] = 1.0
        return y

    app.state.autocal.capture = capture


def wait_status(client, pid):
    deadline = time.monotonic() + 9
    while time.monotonic() < deadline:
        status = client.get(f'/api/projects/{pid}/autocal/run').json()
        if status['state'] in ('completed', 'failed'):
            return status
        time.sleep(.04)
    raise AssertionError('AutoCal did not complete within simulated test budget')


def test_stimulus_is_bounded_and_analysis_finds_delay():
    x = make_stimulus(-30)
    assert len(x) > SAMPLE_RATE
    assert np.max(abs(x)) < 10 ** (-29 / 20)
    delay=400
    y = np.zeros_like(x)
    y[delay:] = .35*x[:-delay]
    result = analyze_channel(x, y, 1)
    assert result['passed']
    assert result['arrival_samples'] == delay
    assert len(result['frequency_db_relative_to_1khz']) == 7
    assert len(result['impulse_preview_normalized']) <= 90
    assert result['snr_db'] > 30


def test_config_is_fixed_scope():
    assert AutoCalConfig().model_dump(include={'measurement_points', 'optimization', 'microphone_type', 'experimental_eq'}) == {
        'measurement_points': 1, 'optimization': 'balanced', 'microphone_type': 'xlr', 'experimental_eq': False}
    for field, value in [('measurement_points', 9),('optimization','area'),('microphone_type','usb'),('experimental_eq',True)]:
        with pytest.raises(ValueError):
            AutoCalConfig(**{field:value})


def test_relative_recommendations_never_boost():
    fake = [dict(channel=i+1, relative_input_dbfs=v, arrival_samples=d, passed=True)
            for i,(v,d) in enumerate([(-42,500),(-38,600),(-45,300),(-41,750)])]
    r = recommendations(fake)
    assert r['quality_ok']
    assert r['channel_gain_db'] == [-3,-7,0,-4]
    assert r['channel_delay_ms'][3] == 0
    assert all(0 <= v <= 30 for v in r['channel_delay_ms'])


def test_delays_continuous_across_blocks_and_muting_flushes():
    mix = Mixer(Project())
    mix.set_calibration([-6.0,0,0,0], [3.0,0,0,0])
    impulse=np.zeros((500,4),dtype=np.float32);impulse[0,0]=1.0
    with mix.lock:
        r1=impulse.copy(); mix._calibrated_output(r1[:80])
        r2=impulse[80:230].copy();mix._calibrated_output(r2)
        out=np.concatenate([r1[:80],r2])
    assert int(np.argmax(out[:,0])) == 144
    assert abs(float(out[144,0]) - 10**(-6/20)) < 1e-6
    mix.panic()
    mix.render(40)
    assert all(not len(buf) or np.max(abs(buf))==0 for buf in mix._delay_buffers)
    with pytest.raises(ValueError):
        mix.set_calibration([1,0,0,0],[0,0,0,0])


def test_end_to_end_review_and_approval_gate(tmp_path, monkeypatch):
    client, app, pid = client_and_app(tmp_path,monkeypatch)
    inject_fake_measurement(app)
    url=f'/api/projects/{pid}/autocal'
    assert client.get(url).json()['config']['optimization']=='balanced'
    config = AutoCalConfig(input_device_index=0, output_device_index=0).model_dump()
    assert client.put(url+'/config',json=config).status_code == 200
    assert client.post(url+'/start',json={'hardware_ready':False}).status_code == 400
    assert client.post(url+'/start',json={'hardware_ready':True}).status_code == 200
    status=wait_status(client,pid)
    assert status['state']=='completed', status
    sid=status['session_id']
    profile=client.get(f'{url}/sessions/{sid}').json()
    assert profile['status']=='review_required' and profile['quality_ok']
    assert [a['channel'] for a in profile['results']]==[1,2,3,4]
    assert [a['arrival_samples'] for a in profile['results']]==[560,850,690,750]
    assert profile['recommendations']['channel_gain_db'][1] < 0
    assert profile['recommendations']['channel_delay_ms'][1] == 0
    assert profile['configuration']['experimental_eq'] is False
    assert 'raw_audio' not in str(profile)
    assert json.loads((Path(tmp_path)/pid/'autocal'/'config.json').read_text())['input_channel']==1
    assert client.post(f'{url}/sessions/{sid}/apply',json={'confirm':''}).status_code==400
    assert not client.get(url).json()['enabled']
    # Forged editor JSON cannot bypass approval.
    project = client.get(f'/api/projects/{pid}').json()
    project['active_calibration_id']=sid;project['calibration_enabled']=True
    check=client.put(f'/api/projects/{pid}',json=project)
    assert check.status_code==200 and not check.json()['calibration_enabled']
    result=client.post(f'{url}/sessions/{sid}/apply',json={'confirm':'APPLY'})
    assert result.status_code==200,result.text
    assert result.json()['project']['calibration_enabled']
    assert client.get(url).json()['active_calibration_id']==sid
    assert app.state.stage.mixer.calibration_gain_db[1]<0
    # Wrong speaker routing can never silently retain a calibration profile.
    project=client.get(f'/api/projects/{pid}').json()
    project['speakers'][0]['distance_m']+=.01
    changed=client.put(f'/api/projects/{pid}',json=project)
    assert changed.status_code==200,changed.text
    assert changed.json()['active_calibration_id'] is None
    assert not changed.json()['calibration_enabled']
    assert app.state.stage.mixer.calibration_gain_db==[0.0]*4
    assert client.post(f'{url}/sessions/{sid}/apply',json={'confirm':'APPLY'}).status_code==400


def test_reject_low_quality_capture(tmp_path,monkeypatch):
    client,app,pid=client_and_app(tmp_path,monkeypatch)
    inject_fake_measurement(app,clip=True)
    url=f'/api/projects/{pid}/autocal'
    client.put(url+'/config',json=AutoCalConfig(input_device_index=0,output_device_index=0).model_dump())
    client.post(url+'/start',json={'hardware_ready':True})
    run=wait_status(client,pid)
    assert run['state']=='completed'
    sid=run['session_id']
    report=client.get(f'{url}/sessions/{sid}').json()
    assert not report['quality_ok']
    assert all(not r['passed'] for r in report['results'])
    assert client.post(f'{url}/sessions/{sid}/apply',json={'confirm':'APPLY'}).status_code==400


def test_mic_config_api_validation(tmp_path, monkeypatch):
    client,_,pid=client_and_app(tmp_path,monkeypatch)
    url=f'/api/projects/{pid}/autocal'
    assert client.put(url+'/config',json={'experimental_eq':True}).status_code==422
    assert client.put(url+'/config',json={'measurement_points':9}).status_code==422
    assert client.put(url+'/config',json={'microphone_type':'usb'}).status_code==422
