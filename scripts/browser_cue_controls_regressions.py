"""Isolated scroll/selected-GO regression using silent samples and no hardware."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import wave
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from stagespatialcue.models import Project
from stagespatialcue.storage import ProjectStore
from stagespatialcue.server import create_app
from stagespatialcue.simulation import SimulationStream
from browser_cue_scroll_checks import check_cue_scroll


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--engine',default='chromium');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='spatialstage-cue-controls-') as tmp:
        store=ProjectStore(Path(tmp))
        data=json.loads((ROOT/'show/project-template.json').read_text());data.pop('id')
        project=Project.model_validate(data)
        folder=store.directory(project.id)/'media';folder.mkdir(parents=True)
        with wave.open(str(folder/'silent.wav'),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b'\x00\x00'*4800)
        for item in project.media:
            (folder/(item.id+'.wav')).write_bytes((folder/'silent.wav').read_bytes())
            item.media_relpath='media/'+item.id+'.wav';item.trim_start_s=0;item.trim_end_s=0;item.loop=False
        for cue in project.cues:
            cue.continue_mode='manual';cue.pre_wait_s=0
        store.save(project)
        store.get(project.id)
        # Deterministic silent mixer stepping; this adapter never opens a device.
        with patch.object(SimulationStream,'start',lambda s:setattr(s,'active',True)), TestClient(create_app(store.root),base_url='http://127.0.0.1:8765') as client, sync_playwright() as pw:
            browser=getattr(pw,args.engine).launch(headless=True,**({'executable_path':args.browser_path} if args.browser_path else {}))
            page=browser.new_page(viewport={'width':1570,'height':950});errors=[];page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE ERROR:',e)))
            page.add_init_script("""window.__testIntervals=[];const originalInterval=window.setInterval;
                window.setInterval=(...args)=>{const id=originalInterval(...args);window.__testIntervals.push(id);return id;};""")
            def route(req):
                q=req.request
                r=client.request(q.method,q.url,content=q.post_data_buffer,headers={k:v for k,v in q.headers.items() if k not in ['host','content-length']})

                if r.status_code>=400:print('HTTP ERROR:',q.url,r.status_code,r.text[:500])
                req.fulfill(status=r.status_code,body=r.content,headers={k:v for k,v in r.headers.items() if k.lower() not in ['content-length','transfer-encoding','content-encoding']})
            page.route('http://127.0.0.1:8765/**',route)
            page.goto('http://127.0.0.1:8765');expect(page.locator('.perf-cue')).to_have_count(30)
            for theme in ['dark','graphite','warm','light']:
                page.select_option('#themeSelect',theme)
                for lang,names,label in [('en',['Deep Sea','Graphite','Warm Grey','Light'],'Theme'),('zh',['深海','石墨','暖灰','浅色'],'配色')]:
                    if page.get_attribute('html','lang')!=lang:page.locator('#langToggle').click()
                    assert page.locator('#themeSelect option').all_text_contents()==names
                    assert page.locator('#themeSelect').get_attribute('aria-label')==label
                    page.locator('#modeEdit').click();page.locator('#modePerform').click()
                    page.locator('#sidebarToggle').click()
                    page.evaluate('window.__testIntervals.forEach(clearInterval)')
                    page.wait_for_load_state('networkidle')
                    page.reload();expect(page.locator('.perf-cue')).to_have_count(30)
                    assert page.locator('#themeSelect').input_value()==theme
                    assert page.get_attribute('html','data-theme')==theme
                    assert page.locator('#themeSelect option').all_text_contents()==names
            print('PASS 4 themes x 2 languages, label/aria, mode/sidebar switching and reload persistence')
            before=page.evaluate('JSON.stringify({...state.project,updated_at:null})')
            for width in [1570,1024]:
                page.set_viewport_size({'width':width,'height':950})
                check_cue_scroll(page)
            assert page.evaluate('JSON.stringify({...state.project,updated_at:null})')==before
            assert client.post('/api/simulation/connect').status_code==200
            page.evaluate('poll()');expect(page.locator('#goButton')).to_be_disabled()
            assert client.post('/api/audio/master',json={'mute':False,'db':-60}).status_code==200
            page.evaluate('poll()')
            assert client.get(f'/api/projects/{project.id}/preflight').json()['ok']
            for index in [29,0,14]:
                assert client.post('/api/audio/master',json={'mute':False,'db':-60}).status_code==200
                page.evaluate('poll()')
                row=page.locator('.perf-cue').nth(index);row.click();expect(page.locator('#goButton')).to_be_enabled()
                original_next=page.evaluate('state.status.next_index')
                assert client.get('/api/audio/status').json()['next_index']==original_next
                page.locator('#goButton').click()
                page.wait_for_function('(i)=>state.status.next_index===i && !fadeGoPending',arg=index+1)
                assert client.get('/api/audio/status').json()['next_index']==index+1
                if index<29:
                    # Row overlap is independent, including after explicit selection.
                    page.locator('.perf-cue').nth(5).locator('.cue-play').click()
                    page.wait_for_function('(id)=>state.status.mixer.voices.some(v=>v.cue_id===id)',arg=project.cues[5].id)
                    assert client.get('/api/audio/status').json()['next_index']==index+1
                    page.locator('#goButton').click()
                    page.wait_for_function('(i)=>state.status.next_index===i && !fadeGoPending',arg=index+2)
                page.locator('#panicButton').click()
                page.wait_for_function('!state.status.mixer.voices.length')
            # Rapid duplicate activation while save/decode is pending schedules once.
            assert client.post('/api/audio/master',json={'mute':False,'db':-60}).status_code==200
            page.evaluate('poll()')
            page.locator('.perf-cue').nth(10).click()
            page.evaluate("$('goButton').click();$('goButton').click()")
            page.wait_for_function('state.status.next_index===11 && !fadeGoPending')
            assert client.get('/api/audio/status').json()['next_index']==11
            assert not errors,errors
            assert page.evaluate('JSON.stringify({...state.project,updated_at:null})')==before
            browser.close()
            print('PASS selected FADE GO first/middle/last, repeated continuation, overlap, PANIC recovery, duplicate activation, mute gate; project unchanged; silent adapter only')

if __name__=='__main__':main()
