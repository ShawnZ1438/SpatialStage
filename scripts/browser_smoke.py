"""Portable browser regression test using a temporary local project directory.

Install development extras and `python -m playwright install chromium` first.
Default: spawn a local server with isolated test data. No actual audio is played.
"""
from __future__ import annotations

import argparse
import base64
import re
import httpx
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import wave

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def silent_wave() -> bytes:
    stream = BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b'\x00\x00' * 4800)
    return stream.getvalue()


# HTML5 drag & drop with real DragEvents inside the page (works in Chromium and WebKit).
DRAG = """([source, target, fx, fy]) => {
  const src = document.querySelector(source), dst = document.querySelector(target);
  const r = dst.getBoundingClientRect(), x = r.left + r.width * fx, y = r.top + r.height * fy;
  const dt = new DataTransfer();
  const fire = (el, type) => el.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt, clientX: x, clientY: y}));
  fire(src, 'dragstart'); fire(dst, 'dragenter'); fire(dst, 'dragover'); fire(dst, 'drop'); fire(src, 'dragend');
}"""


def exercise(base_url: str, browser_path: str | None, screenshot: Path, inline_transport=False, engine='chromium'):
    with sync_playwright() as playwright:
        kwargs = {'headless': True}
        if browser_path:
            kwargs['executable_path'] = browser_path
        print(f'Launching {engine}', flush=True)
        browser = getattr(playwright, engine).launch(**kwargs)  # webkit = Safari's engine
        print(f'{engine} ready', flush=True)
        page = browser.new_page(viewport={'width': 1570, 'height': 950})
        page.set_default_timeout(10000)
        page.add_init_script("try{localStorage.setItem('spatialstage.lang','en')}catch(e){}")  # assertions use English
        errors = []
        page.on('pageerror', lambda error: (errors.append(str(error)),print('Browser error:',error,flush=True)))
        if inline_transport:
            # Restricted runners may block ALL browser networking. Do not alter
            # their policy: execute our own assets in an offline DOM and bridge
            # only this temporary server's /api through the Python test process.
            def local_api(path, method, headers, body, files):
                if not path.startswith('/api/'):
                    raise ValueError('Test bridge accepts /api/ only')
                upload = [(f['key'], (f['name'], base64.b64decode(f['data']), f['type'])) for f in files]
                response = httpx.request(method, base_url+path, headers=headers,
                    content=body if not upload else None, files=upload or None, timeout=10)
                return {'status':response.status_code,'headers':dict(response.headers),'body':response.text}
            page.expose_function('__local_api', local_api)

        def load_page():
            if not inline_transport:
                page.goto(base_url, wait_until='domcontentloaded')
                return
            print('Loading offline DOM', flush=True)
            page.goto('about:blank')
            html=(ROOT/'stagespatialcue/static/index.html').read_text()
            html=re.sub(r'<script[^>]*src=[^>]*></script>', '', html)
            html=re.sub(r'<link[^>]*stylesheet[^>]*>', '', html)
            css=(ROOT/'stagespatialcue/static/style.css').read_text()
            page.set_content(html.replace('</head>', '<style>'+css+'</style></head>'),wait_until='domcontentloaded')
            print('Offline DOM ready', flush=True)
            page.evaluate("""() => {
              window.fetch=async(resource,options={})=>{
                const files=[];let body=options.body??null;
                if(body instanceof FormData){
                  for(const [key,file] of body.entries()){
                    const bytes=new Uint8Array(await file.arrayBuffer());
                    let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
                    files.push({key,name:file.name,type:file.type,data:btoa(binary)});
                  }
                  body=null;
                }
                const response=await window.__local_api(String(resource),options.method||'GET',options.headers||{},body,files);
                return new Response(response.body,{status:response.status,headers:response.headers});
              };
            }""")
            for script in ['i18n.js', 'save-queue.js', 'stage-map.js', 'app.js', 'simulation.js', 'editor.js']:
                page.add_script_tag(content=(ROOT/'stagespatialcue/static'/script).read_text(encoding='utf-8'))
        load_page()
        print('Scripts loaded', flush=True)
        page.wait_for_selector('#projectSelect option', state='attached')
        expect(page.locator('#goButton')).to_be_disabled()
        wav = silent_wave()
        def drag(source, target, fx=.5, fy=.5):
            page.evaluate(DRAG, [source, target, fx, fy])
        def upload(names):
            page.locator('#fileInput').set_input_files([
                {'name':name, 'mimeType':'audio/wav', 'buffer':wav} for name in names
            ])
        upload(['002_Car.wav', '001_Footsteps.wav'])
        expect(page.locator('#libraryList .lib-item')).to_have_count(2)
        expect(page.locator('.lib-name').nth(0)).to_have_text('Footsteps')
        assert page.locator('#performCues .perf-cue').count() == 0  # the library never creates cues by itself
        # Two cues from the library: the drop zone, then the sound designer button.
        drag('#libraryList .lib-item:nth-child(2)', '.cue-dropzone')
        expect(page.locator('#performCues .perf-cue')).to_have_count(1)
        page.locator('#libraryList .lib-item').nth(0).click()
        page.locator('[data-md="new-cue"]').click()
        expect(page.locator('#performCues .perf-cue')).to_have_count(2)
        assert page.locator('#performCues .perf-cue .title').all_text_contents() == ['Car', 'Footsteps']
        # Hold the pointer down across at least one status poll: the row must survive.
        page.evaluate("window.__rowProbe=document.querySelector('#performCues .perf-cue')")
        page.locator('#performCues .perf-cue').first.hover()
        page.mouse.down()
        page.wait_for_timeout(650)
        assert page.evaluate("window.__rowProbe===document.querySelector('#performCues .perf-cue')")
        page.mouse.up()
        page.locator('#cueDown').click()  # Car is selected: move it below Footsteps
        expect(page.locator('#performCues .perf-cue .title').nth(0)).to_have_text('Footsteps')
        upload(['003_Wind.wav'])
        expect(page.locator('#libraryList .lib-item')).to_have_count(3)
        drag('#libraryList .lib-item:nth-child(3)', '.cue-dropzone')
        expect(page.locator('#performCues .perf-cue')).to_have_count(3)
        assert page.locator('#performCues .perf-cue .title').all_text_contents() == ['Footsteps', 'Car', 'Wind']
        print('PASS library import, cues from library, manual ordering, row identity / held click')

        # Delay PUT acknowledgements, not server storage; reproduce overlapping edits.
        page.evaluate('''() => {
          const original = window.fetch.bind(window);
          window.__pendingSaves=0;
          window.fetch=async(...args)=>{
            const slow=args[1]?.method==='PUT';
            if(slow)window.__pendingSaves++;
            const response=await original(...args);
            if(slow){await new Promise(r=>setTimeout(r,700));window.__pendingSaves--;}
            return response;
          };
        }''')
        rotation = page.locator('#globalRotation')
        rotation.fill('111.11')
        rotation.dispatch_event('input')
        page.wait_for_function('window.__pendingSaves>0')
        rotation.fill('222.22')
        rotation.dispatch_event('input')
        expect(page.locator('#saveIndicator')).to_have_text('Saved locally', timeout=6000)
        pid = page.locator('#projectSelect').input_value()
        saved = page.request.get(base_url + '/api/projects/' + pid).json()
        assert saved['global_rotation_deg'] == 222.22
        print('PASS in-flight save drains newest revision')

        page.locator('#settingsToggle').click()
        channel = page.locator('[data-speaker="0"][data-key="output_channel"]')
        channel.fill('2')  # duplicate routing must fail validation
        channel.dispatch_event('change')
        page.locator('#saveSettings').click()
        expect(page.locator('#saveIndicator')).to_contain_text('Save failed', timeout=5000)
        assert page.locator('#stageDialog').evaluate('(element)=>element.open')
        expect(page.locator('#retrySave')).to_be_visible()
        channel.fill('1')
        channel.dispatch_event('change')
        page.locator('#saveSettings').click()
        expect(page.locator('#stageDialog')).not_to_be_visible(timeout=5000)
        print('PASS failed speaker save remains open; correct/retry acknowledgement')

        # Identity-based NEXT follows the original cue despite moved list positions.
        status = page.request.get(base_url + '/api/audio/status').json()
        project = page.request.get(base_url + '/api/projects/' + pid).json()
        assert status['next_cue_id'] == project['cues'][1]['id']
        load_page()
        expect(page.locator('#performCues .perf-cue')).to_have_count(3)
        expect(page.locator('#globalRotation')).to_have_value('222.22')
        page.locator('#autocalOpen').click()
        expect(page.locator('#autocalDialog')).to_be_visible()
        expect(page.locator('#acCancel')).to_be_disabled()
        page.locator('#autocalClose').click()
        page.locator('.simulation-panel summary').click()
        page.locator('#simConnect').click()
        page.wait_for_function("state.status?.output_mode === 'simulation'")
        assert page.evaluate('state.status.mixer.master_mute')
        page.locator('#simRecord').click()
        page.wait_for_function('state.status?.simulation?.recording === true')
        page.wait_for_function('state.status?.simulation?.captured_seconds > 0')
        page.locator('#simStopRecord').click()
        page.wait_for_function('state.status?.simulation?.recording === false')
        capture=httpx.get(base_url+'/api/simulation/capture.wav')
        assert capture.status_code == 200 and capture.content[:4] == b'RIFF'
        page.locator('#simX').fill('1.2')
        page.locator('#simHead').fill('270')
        print('PASS silent simulation, muted connection, bounded capture download, actor markers')

        # Stage map: two layers in one cue, path drawing, Store / Reset / Recall, Show-mode lock.
        def cue_by_id(cid):
            return next(c for c in page.request.get(base_url + '/api/projects/' + pid).json()['cues'] if c['id'] == cid)
        def map_click(fx, fy):
            page.locator('#performMap').scroll_into_view_if_needed()
            box = page.evaluate("(() => { const r = document.querySelector('#performMap svg').getBoundingClientRect(); return {x:r.x, y:r.y, width:r.width, height:r.height}; })()")
            page.mouse.click(box['x'] + box['width']*fx, box['y'] + box['height']*fy)
        def settled():
            page.wait_for_function('!saveQueue.dirty && !saveQueue.running')
        page.locator('#performCues .perf-cue').nth(0).click()
        cid = page.evaluate('state.selectedCueId')
        page.locator('#performMap').scroll_into_view_if_needed()
        drag('#libraryList .lib-item:nth-child(3)', '#performMap svg', .75, .75)  # Wind, rear right
        settled()
        cue = cue_by_id(cid)
        assert len(cue['layers']) == 2, cue
        wind = cue['layers'][1]
        assert wind['direction_mode'] == 'path' and wind['path'][0]['x_m'] > 1 and wind['path'][0]['y_m'] < -1, wind
        expect(page.locator('#performTarget tr.layer-row')).to_have_count(2)
        page.locator('#performTarget tr.layer-row').nth(0).locator('.layer-name').click()
        map_click(.25, .5)
        page.locator('[data-ly="tool"][data-tool="add"]').click()
        map_click(.75, .5)
        settled()
        first = cue_by_id(cid)['layers'][0]
        assert first['direction_mode'] == 'path' and len(first['path']) == 2, first
        assert first['path'][0]['x_m'] < -1 and first['path'][1]['x_m'] > 1 and first['path'][1]['time_s'] > 0
        page.locator('[data-cue-action="store"]').click()
        expect(page.locator('.perf-preset-state')).to_contain_text('Matches stored preset')
        page.locator('[data-cue-action="reset"]').click()
        settled()
        assert all(len(l['path']) == 1 for l in cue_by_id(cid)['layers'])
        expect(page.locator('.perf-preset-state')).to_contain_text('Changed since stored preset')
        page.locator('[data-cue-action="recall"]').click()
        settled()
        recalled = cue_by_id(cid)
        assert recalled['layers'][0]['path'] == first['path'] and recalled['layers'][1]['path'] == wind['path']
        page.locator('#modePerform').click()
        expect(page.locator('#libraryPanel')).to_be_hidden()
        map_click(.5, .2)
        settled()
        assert cue_by_id(cid)['layers'][0]['path'] == first['path']  # Show mode: map is locked
        load_page()
        expect(page.locator('#modePerform')).to_have_attribute('aria-pressed', 'true')
        page.locator('#modeEdit').click()
        expect(page.locator('#libraryPanel')).to_be_visible()
        if not inline_transport:  # the remembered mode wins after ?mode= is used once
            page.goto(base_url + '/?mode=perform', wait_until='domcontentloaded')
            expect(page.locator('#libraryPanel')).to_be_hidden()
            assert '?' not in page.url
            page.locator('#modeEdit').click()
            page.reload(wait_until='domcontentloaded')
            expect(page.locator('#modeEdit')).to_have_attribute('aria-pressed', 'true')
        print('PASS stage map: drop layer, add path point, store/reset/recall all layers, Show-mode lock, mode memory')

        page.wait_for_selector('#libraryList .lib-item')
        page.locator('#langToggle').click()
        expect(page.locator('#modeEdit')).to_have_text('✎ 编排')
        expect(page.locator('#libraryPanel .section-heading').first).to_have_text('音频库')
        page.locator('#langToggle').click()
        expect(page.locator('#modeEdit')).to_have_text('✎ Design')
        print('PASS zh / English switch')
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        assert not errors, f'Browser exceptions: {errors}'
        print('PASS reload, stable NEXT, AutoCal dialog, zero uncaught browser errors')
        browser.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--spawn', action=argparse.BooleanOptionalAction, default=True,
                        help='Start an isolated localhost server (default). --no-spawn uses an existing test server.')
    parser.add_argument('--inline-transport', action='store_true', help='Offline DOM + local API bridge for network-restricted runners; CI uses normal HTTP navigation')
    parser.add_argument('--browser-path', default=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'))
    parser.add_argument('--engine', choices=['chromium', 'webkit', 'firefox'], default='chromium',
                        help='webkit approximates Safari (python -m playwright install webkit)')
    parser.add_argument('--screenshot', type=Path, default=Path('test-output/browser.png'))
    args = parser.parse_args()
    process = None
    with tempfile.TemporaryDirectory(prefix='spatialstage-browser-') as data:
        try:
            if args.spawn:
                if args.base_url != 'http://127.0.0.1:8765':
                    parser.error('--spawn requires the standard loopback origin on port 8765')
                # Refuse to test against a different process using the fixed operator port.
                try:
                    with urlopen(args.base_url + '/api/health', timeout=.3):
                        raise RuntimeError('Port 8765 is already serving; stop it or use --no-spawn with TEST DATA only')
                except URLError:
                    pass
                env = {**os.environ, 'STAGE_SPATIAL_DATA':data, 'SPATIALSTAGE_DIAGNOSTICS':'0'}
                process = subprocess.Popen([sys.executable,'-m','uvicorn',
                    'stagespatialcue.server:create_app','--factory','--host','127.0.0.1','--port','8765',
                    '--no-access-log'],cwd=ROOT,env=env)
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Test server did not start')
                    try:
                        with urlopen(args.base_url+'/api/health',timeout=.3) as response:
                            health=json.load(response)
                        print('Local server:',health)
                        break
                    except URLError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Test server startup timed out')
            exercise(args.base_url, args.browser_path, args.screenshot, args.inline_transport, args.engine)
        finally:
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
