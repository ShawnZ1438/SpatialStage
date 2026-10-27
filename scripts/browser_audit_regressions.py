"""Real-browser audit regressions, isolated data/port; physical audio is forbidden."""
import argparse
from io import BytesIO
from pathlib import Path
import socket
import tempfile
import threading
import time
from unittest.mock import patch

import numpy as np
import soundfile as sf
import uvicorn
from playwright.sync_api import sync_playwright, expect

from stagespatialcue.server import create_app


def exercise(page, base):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.add_init_script("try{localStorage.setItem('spatialstage.lang','en')}catch(e){}")  # assertions use English
    page.goto(base + '/?mode=edit', wait_until='domcontentloaded')
    page.wait_for_selector('#projectSelect option', state='attached')
    pid = page.locator('#projectSelect').input_value()
    url = base+'/api/projects/'+pid
    data = BytesIO()
    sf.write(data, np.zeros(4800), 48000, format='WAV')
    upload = {'name':'001_Initial.wav','mimeType':'audio/wav','buffer':data.getvalue()}
    page.locator('#fileInput').set_input_files(upload)
    expect(page.locator('#libraryList .lib-item')).to_have_count(1)
    def saved():
        page.wait_for_function('!state.mediaOperation && !saveQueue.dirty && !saveQueue.running')
        expect(page.locator('#saveIndicator')).to_have_text('Saved locally')
    def edit(selector, value):
        field = page.locator(selector)
        field.fill(str(value)); field.dispatch_event('change')
    saved()
    page.locator('#libraryList .lib-item').first.click()
    page.locator('[data-md="new-cue"]').click()
    expect(page.locator('#performCues .perf-cue')).to_have_count(1)
    title = '[data-cue-field="title"]'
    # Hold real HTTP responses after the server committed their older snapshots.
    for replacement in [False, True]:
        edit(title,'before'); saved()
        held=[]
        def hold(route):
            held.append((route,route.fetch()))
        pattern='**/replace' if replacement else '**/upload*'
        page.route(pattern,hold)
        payload={**upload,'name':'002_Replacement.wav' if replacement else '002_Added.wav'}
        if replacement:
            page.locator('#libraryList .lib-item').first.click()
            page.locator('#replaceMediaFile').set_input_files(payload)
        else:
            page.locator('#fileInput').set_input_files(payload)
        for _ in range(100):
            page.wait_for_timeout(25)
            if held: break
        assert held, 'media response not intercepted'
        edit(title,'edited while media pending')
        page.wait_for_function('!saveQueue.dirty && !saveQueue.running')
        assert page.request.get(url).json()['cues'][0]['title']=='edited while media pending'
        route,response=held.pop();route.fulfill(response=response);page.unroute(pattern)
        saved()
        expect(page.locator(title)).to_have_value('edited while media pending')
        edit('[data-cue-field="gain_db"]',-12);saved()  # later PUT must not persist the old title
        page.goto(base + '/?mode=edit', wait_until='domcontentloaded');page.wait_for_selector('#performCues .perf-cue')
        page.locator('#performCues .perf-cue').first.click()
        expect(page.locator(title)).to_have_value('edited while media pending')
        project=page.request.get(url).json()
        assert project['cues'][0]['gain_db']==-12 and len(project['cues'])==1 and len(project['media'])==2
        if replacement: assert project['media'][0]['filename']=='002_Replacement.wav'
        print('PASS real media race and persistence:', 'replace' if replacement else 'import', flush=True)
    bearing = '[data-layer-field="position_deg"]'
    edit(bearing,360);saved()
    expect(page.locator(bearing)).to_have_value('0.00')
    assert page.request.get(url).json()['cues'][0]['layers'][0]['position_deg']==0
    page.goto(base + '/?mode=edit', wait_until='domcontentloaded');page.wait_for_selector('#performCues .perf-cue')
    page.locator('#performCues .perf-cue').first.click()
    expect(page.locator(bearing)).to_have_value('0.00')
    assert page.locator('#performMap .sm-point.angle').is_visible()
    print('PASS 360 input, saved zero, reload and map render',flush=True)
    # Real geometry editor: place CH2 directly atop CH1; invalid save stays open.
    page.locator('#settingsToggle').click()
    for key in ['x_m','y_m']:
        value=page.locator(f'[data-speaker="0"][data-key="{key}"]').input_value()
        field=page.locator(f'[data-speaker="1"][data-key="{key}"]')
        field.fill(value);field.dispatch_event('change')
    page.locator('#saveSettings').click()
    expect(page.locator('#saveIndicator')).to_contain_text('Save failed')
    expect(page.locator('#stageDialog')).to_be_visible()
    field=page.locator('[data-speaker="1"][data-key="x_m"]')
    field.fill('2.12');field.dispatch_event('change');page.locator('#saveSettings').click()
    expect(page.locator('#stageDialog')).not_to_be_visible();saved()
    for angles in [[0,0,120,240],[0,120,240,359.999],[0,120,240,360]]:
        project=page.request.get(url).json()
        for speaker,angle in zip(project['speakers'],angles): speaker['angle_deg']=angle
        assert page.request.put(url,data=project).status==422
    print('PASS geometry editor rejection/recovery and circular duplicate API validation',flush=True)
    # Native output attempts are replaced by a failing driver; no soundcard is opened.
    page.locator('#outputSelect').select_option('0')
    page.locator('#connectAudio').click()
    expect(page.locator('#toast')).to_contain_text('Output connection failed')
    assert not page.request.get(base+'/api/audio/status').json()['connected']
    page.locator('.simulation-panel summary').click()
    page.locator('#simListen').click()
    expect(page.locator('#simDevice option')).to_have_count(1)
    page.locator('#simListen').click()
    expect(page.locator('#toast')).to_contain_text('Output connection failed')
    status=page.request.get(base+'/api/audio/status').json()
    assert not status['connected'] and status['mixer']['master_mute']
    assert page.request.post(base+'/api/audio/connect',data={'device_index':-999}).status==422
    assert not errors, errors
    print('PASS controlled hardware/stereo connection errors, muted state; zero page errors',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-path')
    args=parser.parse_args()
    port=8767
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',port))  # refuse an occupied test port
    with tempfile.TemporaryDirectory(prefix='spatialstage-audit-') as data:
        app=create_app(Path(data))
        class PortAdapter:
            async def __call__(self,scope,receive,send):
                if scope['type']=='http':
                    headers=[]
                    for key,value in scope['headers']:
                        if key==b'host' and value==b'127.0.0.1:8767': value=b'127.0.0.1:8765'
                        if key==b'origin' and value==b'http://127.0.0.1:8767': value=b'http://127.0.0.1:8765'
                        headers.append((key,value))
                    scope={**scope,'headers':headers}
                await app(scope,receive,send)
        def forbidden(*args,**kwargs):
            raise RuntimeError('test driver unavailable; physical audio forbidden')
        device={'name':'Test unavailable output','max_output_channels':4,'max_input_channels':0}
        with patch('sounddevice.query_devices',lambda index=None:[device] if index is None else device), \
             patch('sounddevice.check_output_settings',lambda **kw:None), \
             patch('sounddevice.OutputStream',forbidden), patch('sounddevice.InputStream',forbidden), \
             patch('sounddevice.playrec',forbidden):
            server=uvicorn.Server(uvicorn.Config(PortAdapter(),host='127.0.0.1',port=port,log_level='error'))
            thread=threading.Thread(target=server.run,daemon=True);thread.start()
            try:
                for _ in range(100):
                    if server.started: break
                    time.sleep(.05)
                assert server.started, 'isolated server did not start'
                with sync_playwright() as pw:
                    options={'headless':True,'args':['--mute-audio']}
                    if args.browser_path: options['executable_path']=args.browser_path
                    browser=pw.chromium.launch(**options)
                    try:
                        exercise(browser.new_page(viewport={'width':1600,'height':1050}),f'http://127.0.0.1:{port}')
                    finally: browser.close()
            finally:
                server.should_exit=True;thread.join(5)


if __name__=='__main__': main()
