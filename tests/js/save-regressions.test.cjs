'use strict';
// Run the real browser app in a tiny DOM harness; no frontend framework required.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
function harness() {
  const elements = new Map();
  const documentListeners={};
  const classList = () => ({add(){}, remove(){}, toggle(){}, contains(){return false;}});
  const get = id => {
    if (!elements.has(id)) elements.set(id, {textContent:'', value:'', innerHTML:'', listeners:{}, options:[],
      addEventListener(type, fn) {this.listeners[type] = fn;}, setAttribute(){}, focus(){},
      querySelector(){return null;}, querySelectorAll(){return [];}, contains(){return false;},
      close() {this.closed = true;}, showModal() {}, classList:classList()});
    return elements.get(id);
  };
  const context = vm.createContext({console:{error(){}}, setInterval(){}, setTimeout(){return 1;}, clearTimeout(){},
    structuredClone, FormData, Blob, URLSearchParams, requestAnimationFrame(){}, performance:{now:()=>0},
    location:{search:'', pathname:'/'}, history:{replaceState(){}}, confirm:()=>true,
    localStorage:{getItem:key=>key==='spatialstage.lang'?'en':null, setItem(){}},
    document:{getElementById:get, readyState:'complete', documentElement:{}, body:{classList:classList()}, activeElement:null,
      addEventListener(type,fn){documentListeners[type]=fn;}, querySelector(){return null;}, querySelectorAll(){return [];}},
    window:{addEventListener(){}}, requests:[], responses:[], rejectNext:false});
  for (const name of ['i18n.js', 'save-queue.js', 'stage-map.js'])
    vm.runInContext(fs.readFileSync(path.join(root, 'stagespatialcue/static', name), 'utf8'), context);
  const app = fs.readFileSync(path.join(root,'stagespatialcue/static/app.js'),'utf8').replace(/^boot\(\);?\s*$/m, '');
  vm.runInContext(app, context);
  vm.runInContext(fs.readFileSync(path.join(root,'stagespatialcue/static/editor.js'),'utf8'), context);
  vm.runInContext(`
    state.project={id:'123456abcdef',name:'A',updated_at:'old',media:[],cues:[],speakers:[]};
    api=async(path,options)=>{
      requests.push({path, body:JSON.parse(options.body)});
      return await new Promise((resolve,reject)=>responses.push({resolve,reject}));
    };
  `, context);
  return {context,get,documentListeners,run:code=>vm.runInContext(code,context)};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('edits made during an in-flight save are drained before Save resolves', async()=>{
  const h=harness();
  const first=h.run('saveNow()');
  assert.equal(h.context.requests.length,1);
  h.run("state.project.name='latest'; scheduleSave();");
  const second=h.run('saveNow()');
  h.context.responses[0].resolve({updated_at:'v1'});
  await tick();
  assert.equal(h.context.requests.length,2,'latest edit was silently dropped while saveBusy');
  assert.equal(h.context.requests[1].body.name,'latest');
  let resolved=false; second.then(()=>{resolved=true;}); await tick();
  assert.equal(resolved,false,'Save resolved before latest edit reached server');
  h.context.responses[1].resolve({updated_at:'v2'});
  await Promise.all([first,second]);
  assert.equal(h.get('saveIndicator').textContent,'Saved locally');
});

test('failed saves reject, keep dirty state, and explicit retry saves latest edit', async()=>{
  const h=harness();
  const first=h.run('saveNow()');
  const failed=assert.rejects(first,/offline/);
  h.context.responses[0].reject(new Error('offline'));
  await failed;
  assert.match(h.get('saveIndicator').textContent,/failed/i);
  h.run("state.project.name='retry';");
  const retry=h.run('saveNow()');
  assert.equal(h.context.requests[1].body.name,'retry');
  h.context.responses[1].resolve({updated_at:'v2'});
  await retry;
  assert.equal(h.get('saveIndicator').textContent,'Saved locally');
});

test('speaker dialog stays open when the save fails', async()=>{
  const h=harness();
  h.run('state.editSpeakers=[];');
  const saving=h.get('saveSettings').listeners.click();
  h.context.responses[0].reject(new Error('invalid layout'));
  await saving;
  assert.notEqual(h.get('stageDialog').closed,true);
  assert.notEqual(h.get('eventLog').textContent,'Speaker geometry saved. Test all four channels before rehearsal.');
});

test('speaker Save waits for a preceding in-flight save AND its own snapshot', async()=>{
  const h=harness();
  // Rendering is orthogonal to this test; run the real dialog event handler.
  h.run("renderEverything=()=>{}; state.editSpeakers=[{name:'new geometry',x_m:1,y_m:1}];");
  const first=h.run('saveNow()');
  const settings=h.get('saveSettings').listeners.click();
  h.context.responses[0].resolve({updated_at:'old-ack'});
  await tick();
  assert.equal(h.context.requests.length,2);
  assert.notEqual(h.get('stageDialog').closed,true,'dialog closed on the wrong save acknowledgement');
  assert.equal(h.context.requests[1].body.speakers[0].name,'new geometry');
  h.context.responses[1].resolve({updated_at:'new-ack'});
  await Promise.all([first,settings]);
  assert.equal(h.get('stageDialog').closed,true);
});

test('a failed trailing save never reports the latest edits as saved', async()=>{
  const h=harness();
  const first=h.run('saveNow()');
  h.run("state.project.name='latest'; scheduleSave();");
  const result=assert.rejects(first,/late failure/);
  h.context.responses[0].resolve({updated_at:'first'});
  await tick();
  h.context.responses[1].reject(new Error('late failure'));
  await result;
  assert.match(h.get('saveIndicator').textContent,/failed/i);
  assert.equal(h.run('saveQueue.dirty'),true);
});

test('STOP cancels a GO waiting for a slow save; no deferred playback', async()=>{
  const h=harness();
  h.run(`renderTransport=()=>{};renderMaster=()=>{};
    sent=[];post=async(path)=>{sent.push(path);return {};};`);
  const go=h.run("action('/audio/go',{project_id:state.project.id})");
  await h.run("action('/audio/stop')");
  h.context.responses[0].resolve({updated_at:'late'});
  await go;
  assert.deepEqual(Array.from(h.run('sent')),['/audio/stop']);
});


test('delayed import adds only the new library items, never stale or deleted ones', async()=>{
  const h=harness();
  h.run(`state.project.media=[{id:'a',name:'before'},{id:'b',name:'delete'}];
    renderEverything=()=>{}; refreshProjectsPreservingSelection=async()=>{};
    saved=[]; saveNow=async()=>saved.push(structuredClone(state.project));
    api=async()=>new Promise(resolve=>{uploadAck=resolve;});`);
  const pending=h.run("uploadFiles([new Blob(['x'])])"); await tick();
  h.run(`state.project.media[0].name='during import'; state.project.media.pop(); state.project.global_rotation_deg=77;
    uploadAck({added:1,ignored:[],media_ids:['c'],project:{cues:[],media:[{id:'a',name:'before'},{id:'b',name:'delete'},{id:'c',name:'new'}]}});`);
  const ids=await pending;
  assert.deepEqual(Array.from(ids),['c']);
  assert.equal(h.run('state.project.media[0].name'),'during import');
  assert.equal(h.run('state.project.media.map(m=>m.id).join()'),'a,c');
  assert.equal(h.run('saved.at(-1).global_rotation_deg'),77);
  assert.equal(h.run('saved.at(-1).media[0].name'),'during import');
});

test('delayed file replacement updates the library item and keeps edits made meanwhile', async()=>{
  const h=harness();
  h.run(`state.project.media=[{id:'m',name:'before',gain_db:-6,filename:'old.wav'}]; state.selectedMediaId='m';
    SpatialEditor.render=()=>{}; saveNow=async()=>{}; scheduleSave=()=>{};
    api=async()=>new Promise(resolve=>{mediaAck=resolve;});`);
  const pending=h.get('mediaDesigner').listeners.change({target:{id:'replaceMediaFile',files:[new Blob(['x'])],dataset:{}}});
  await tick();
  h.run(`state.project.media[0].gain_db=-12;`);
  h.run(`mediaAck({media:{id:'m',filename:'replacement.wav',media_relpath:'media/replacement.wav',duration_s:2,source_channels:1}})`);
  await pending;
  assert.equal(h.run('state.project.media[0].filename'),'replacement.wav');
  assert.equal(h.run('state.project.media[0].gain_db'),-12);
});

test('360 bearing input is zero while angular keyframe offsets remain unwrapped',async()=>{
  const h=harness();
  h.run(`state.project.media=[{id:'m',name:'s'}];
    state.project.cues=[{id:'a',layers:[{id:'L',media_id:'m',position_deg:270,direction_mode:'keyframes',modulation:[{time_s:0,offset_deg:0}],path:[]}]}];
    state.selectedCueId='a'; state.selectedLayerId='L'; changed=()=>{};`);
  const change=h.get('performTarget').listeners.change;
  const field=(dataset,value)=>({target:{dataset,value,type:'number',closest:()=>null}});
  await change(field({layerField:'position_deg'},'360'));
  assert.equal(h.run('state.project.cues[0].layers[0].position_deg'),0);
  await change(field({kf:'0',k:'offset_deg'},'360'));
  assert.equal(h.run('state.project.cues[0].layers[0].modulation[0].offset_deg'),360);
});

test('cue duration is the longest layer (delay + trimmed sound); a loop never ends',()=>{
  const h=harness();
  h.run(`state.project.media=[{id:'a',duration_s:10,trim_start_s:2,trim_end_s:0},{id:'b',duration_s:3,trim_start_s:0,trim_end_s:0,loop:false}];`);
  assert.equal(h.run(`cueDuration({layers:[{media_id:'a',delay_s:0},{media_id:'b',delay_s:6}]})`),9);
  assert.equal(h.run(`cueDuration({layers:[{media_id:'a',delay_s:0},{media_id:'b',delay_s:6,muted:true}]})`),8);
  h.run(`state.project.media[1].loop=true;`);
  assert.equal(h.run(`cueDuration({layers:[{media_id:'b',delay_s:0}]})`),Infinity);
});

test('server errors are translated in 中文 and passed through in English',()=>{
  const h=harness();
  assert.equal(h.run(`I18N.error('Audio not ready: Rain. Run Preflight / wait for ARM preload before GO')`),'Audio not ready: Rain. Run Preflight / wait for ARM preload before GO');
  h.run(`renderEverything=()=>{}; renderDataLocation=()=>{}; render=()=>{}; I18N.setLang('zh')`);
  assert.match(h.run(`I18N.error('Audio not ready: Rain. Run Preflight / wait for ARM preload before GO')`),/音频未就绪：Rain/);
  assert.equal(h.run(`t('cueCount',{n:3})`),'3 条');
});


test('Space never GOes from text fields; on a focused button it blurs and GOes exactly once',()=>{
 const h=harness();let goes=0,panics=0,blurs=0;
 h.get('goButton').click=()=>goes++;h.get('panicButton').click=()=>panics++;
 const key=(tag,extra={})=>({target:{tagName:tag,blur(){blurs++;}},code:'Space',key:' ',preventDefault(){},...extra});
 for(const tag of ['INPUT','SELECT','TEXTAREA'])h.documentListeners.keydown(key(tag));
 assert.equal(goes,0);
 for(const tag of ['BUTTON','A','SUMMARY'])h.documentListeners.keydown(key(tag));
 assert.equal(goes,3);assert.equal(blurs,3);
 h.documentListeners.keydown(key('BODY'));assert.equal(goes,4);assert.equal(blurs,3);
 h.documentListeners.keydown(key('INPUT',{key:'Escape',code:'Escape',shiftKey:true}));assert.equal(panics,1);
});
test('PDF cue numbering preserves gaps and leaves unresolved material unnumbered',()=>{
 const h=harness();assert.equal(h.run("cueDisplayNumber({title:'05 · 合唱'},0)"),'05');
 assert.equal(h.run("cueDisplayNumber({title:'待定 · 洗衣机'},9)"),'—');
});

test('STOP cancels selected GO while its audio preparation is pending', async()=>{
  const h=harness();
  h.run(`renderTransport=()=>{};renderMaster=()=>{};saveNow=async()=>{};
    sent=[];post=async(path)=>{sent.push(path);
      if(path==='/audio/prepare-go')return new Promise(resolve=>{prepareAck=resolve;});
      return {};};`);
  const go=h.run("action('/audio/go',{project_id:state.project.id,cue_id:'selected'})");
  await tick();
  await h.run("action('/audio/stop')");
  h.run('prepareAck({ok:true})');await go;
  assert.deepEqual(Array.from(h.run('sent')),['/audio/prepare-go','/audio/stop']);
});
