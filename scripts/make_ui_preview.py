"""Offline front-end visual smoke; injects mocked API only in temp HTML file."""
from pathlib import Path
from playwright.sync_api import sync_playwright

base=Path(__file__).resolve().parents[1]
css=(base/'stagespatialcue/static/style.css').read_text()
js=(base/'stagespatialcue/static/app.js').read_text()
html=(base/'stagespatialcue/static/index.html').read_text()
html=html.replace('<link rel="stylesheet" href="/static/style.css" />',f'<style>{css}</style>')
mock=r'''<script>
let project={schema_version:2,id:'aaaaaaaaaaaa',name:'StageSpatial — Scene I',created_at:'2026-10-20T00:00:00Z',updated_at:'2026-10-20T00:00:00Z',
speakers:[{name:'L · front left',angle_deg:315,distance_m:3,output_channel:1,trim_db:0},{name:'R · front right',angle_deg:45,distance_m:3,output_channel:2,trim_db:0},{name:'RR · rear right',angle_deg:135,distance_m:3,output_channel:3,trim_db:0},{name:'RL · rear left',angle_deg:225,distance_m:3,output_channel:4,trim_db:0}],
distance_compensation:false,global_rotation_deg:0,global_envelope_enabled:true,global_modulation:[{time_s:0,offset_deg:0},{time_s:30,offset_deg:90}],
cues:[{id:'c0001',title:'Opening · Suspended',filename:'001_Opening.wav',media_relpath:'media/001_Opening.wav',duration_s:8.5,color:'cyan',position_deg:0,direction_mode:'keyframes',modulation:[{time_s:0,offset_deg:0},{time_s:2,offset_deg:45},{time_s:6,offset_deg:270}],direction_adsr:{attack_s:.3,peak_offset_deg:90,decay_s:.5,sustain_offset_deg:90,release_s:.3,release_offset_deg:0},gain_db:-7,fade_in_s:.4,fade_out_s:1.2,transition_s:2.5,replace_style:'crossfade',pre_wait_s:0,post_wait_s:1.0,start_mode:'replace',continue_mode:'manual'},
{id:'c0002',title:'Whisper · 9 o’clock',filename:'002_Whisper.wav',duration_s:3.2,position_deg:270,direction_mode:'keyframes',modulation:[{time_s:0,offset_deg:0},{time_s:3.2,offset_deg:90}],direction_adsr:{attack_s:.3,peak_offset_deg:90,decay_s:.5,sustain_offset_deg:90,release_s:.3,release_offset_deg:0},gain_db:-10,fade_in_s:.1,fade_out_s:.4,transition_s:2.5,replace_style:'crossfade',pre_wait_s:0,post_wait_s:0,start_mode:'layer',continue_mode:'manual'},
{id:'c0003',title:'Car · Left → Right',filename:'003_Car.wav',duration_s:5.8,position_deg:270,direction_mode:'adsr',modulation:[{time_s:0,offset_deg:0}],direction_adsr:{attack_s:1.4,peak_offset_deg:90,decay_s:2,sustain_offset_deg:180,release_s:.8,release_offset_deg:180},gain_db:-5,fade_in_s:.2,fade_out_s:.2,transition_s:2.5,replace_style:'crossfade',pre_wait_s:.5,post_wait_s:1,start_mode:'replace',continue_mode:'manual'}]};
let status={project_id:project.id,next_index:0,output_device:null,connected:false,error:null,xruns:0,mixer:{frame:0,seconds:0,show_elapsed_s:0,master_mute:true,master_db:-18,meters:[0,0,0,0],peak_over_count:0,voices:[]}};
const response=(value)=>({ok:true,status:200,headers:{get:()=>"application/json"},json:async()=>value,text:async()=>JSON.stringify(value)});
window.fetch=async function(path,options={}){const url=String(path).replace('/api','');
 if(url==='/projects'&&(!options.method||options.method==='GET'))return response([{id:project.id,name:project.name,count:project.cues.length}]);
 if(url==='/devices')return response({inputs:[],outputs:[]});
 if(url==='/audio/status')return response(status);
 if(url==='/audio/arm'){status.next_index=JSON.parse(options.body).index;return response(status);}
 if(url==='/calibration/preview')return response({measured:false,speaker_hints:project.speakers.map(s=>({...s,channel:s.output_channel,suggested_extra_delay_ms:0,suggested_relative_gain_db:0,pointing_at_center_deg:(s.angle_deg+180)%360}))});
 if(url===`/projects/${project.id}`&&options.method==='PUT'){project=JSON.parse(options.body);return response(project);}
 if(url.startsWith('/projects/'))return response(project);
 return response(status);
};
</script>'''
html=html.replace('<script src="/static/app.js" defer></script>', mock + '<script>' + js + '</script>')
output=Path('/mnt/data/SpatialStage-ui-mock.html')
output.write_text(html)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--allow-file-access-from-files'])
    page=browser.new_page(viewport={'width':1580,'height':950},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(html,wait_until='load')
    page.wait_for_selector('#cueRows tr',timeout=12000)
    print('Rows',page.locator('#cueRows tr').count())
    page.locator('#globalAddPoint').click()
    print('Global points',page.locator('.global-key-row').count())
    page.locator('#settingsToggle').click()
    page.locator('#previewSettings').click()
    print('Calib hints',page.locator('#calibrationHints').inner_text()[:95])
    page.locator('#closeSettings').click()
    page.locator('#cueRows tr').nth(2).click()
    print('ADSR field count',page.locator('[data-cue^="adsr_"]').count())
    page.locator('#cueRows tr').nth(0).click()
    page.screenshot(path='/mnt/data/SpatialStage-v0.2-preview.png',full_page=True)
    print('UI errors',errors)
    browser.close()
