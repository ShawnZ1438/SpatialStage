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
  const get = id => {
    if (!elements.has(id)) elements.set(id, {textContent:'', value:'', innerHTML:'', listeners:{},
      addEventListener(type, fn) {this.listeners[type] = fn;},
      close() {this.closed = true;}, showModal() {}, classList:{add(){},remove(){}}});
    return elements.get(id);
  };
  const context = vm.createContext({console:{error(){}}, setInterval(){}, setTimeout(){return 1;}, clearTimeout(){},
    structuredClone, FormData, Blob, document:{getElementById:get,addEventListener(){},querySelector(){return null;}},
    window:{addEventListener(){}}, requests:[], responses:[], rejectNext:false});
  const queuePath = path.join(root, 'stagespatialcue/static/save-queue.js');
  if (fs.existsSync(queuePath)) vm.runInContext(fs.readFileSync(queuePath,'utf8'), context);
  const app = fs.readFileSync(path.join(root,'stagespatialcue/static/app.js'),'utf8').replace(/^boot\(\);?\s*$/m, '');
  vm.runInContext(app, context);
  vm.runInContext(`
    state.project={id:'123456abcdef',name:'A',updated_at:'old',cues:[],speakers:[]};
    api=async(path,options)=>{
      requests.push({path, body:JSON.parse(options.body)});
      return await new Promise((resolve,reject)=>responses.push({resolve,reject}));
    };
  `, context);
  return {context,get,run:code=>vm.runInContext(code,context)};
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
  h.run("renderDial=()=>{}; state.editSpeakers=[{name:'new geometry',x_m:1,y_m:1}];");
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
  h.run(`renderTransport=()=>{};renderRows=()=>{};renderMaster=()=>{};
    sent=[];post=async(path)=>{sent.push(path);return {};};`);
  const go=h.run("action('/audio/go',{project_id:state.project.id})");
  await h.run("action('/audio/stop')");
  h.context.responses[0].resolve({updated_at:'late'});
  await go;
  assert.deepEqual(Array.from(h.run('sent')),['/audio/stop']);
});


test('delayed import merges new IDs without restoring edited or deleted cues', async()=>{
  const h=harness();
  h.run(`state.project.cues=[{id:'a',title:'before'},{id:'b',title:'delete'}];
    renderEverything=()=>{}; refreshProjectsPreservingSelection=async()=>{};
    saved=[]; saveNow=async()=>saved.push(structuredClone(state.project));
    api=async()=>new Promise(resolve=>{uploadAck=resolve;});`);
  const pending=h.run("uploadFiles([new Blob(['x'])])"); await tick();
  h.run(`state.project.cues[0].title='during import'; state.project.cues.pop(); state.project.global_rotation_deg=77;
    uploadAck({added:1,ignored:[],project:{cues:[{id:'a',title:'before'},{id:'b',title:'delete'},{id:'c',title:'new'}]}});`);
  await pending;
  assert.equal(h.run('state.project.cues[0].title'),'during import');
  assert.equal(h.run('state.project.cues.map(c=>c.id).join()'),'a,c');
  assert.equal(h.run('saved.at(-1).global_rotation_deg'),77);
  assert.equal(h.run('saved.at(-1).cues[0].title'),'during import');
});

test('delayed media replacement keeps edits and never resurrects a deleted cue', async()=>{
  for(const deleted of [false,true]) {
    const h=harness();
    h.run(`state.project.cues=[{id:'a',title:'before',gain_db:-6}]; state.selectedCueId='a';
      renderEverything=()=>{}; saveNow=async()=>{};
      api=async()=>new Promise(resolve=>{mediaAck=resolve;});`);
    const pending=h.get('inspectorContent').listeners.change({target:{id:'replaceCueAudio',files:[new Blob(['x'])]}});
    await tick();
    h.run(deleted?`state.project.cues=[];`:`state.project.cues[0].title='after';state.project.cues[0].gain_db=-12;`);
    h.run(`mediaAck({cue:{filename:'replacement.wav',media_relpath:'media/replacement.wav',duration_s:2,title:'stale',gain_db:0}})`);
    await pending;
    if(deleted)assert.equal(h.run('state.project.cues.length'),0);
    else {
      assert.equal(h.run('state.project.cues[0].title'),'after');
      assert.equal(h.run('state.project.cues[0].gain_db'),-12);
      assert.equal(h.run('state.project.cues[0].filename'),'replacement.wav');
    }
  }
});

test('360 bearing input is zero while angular envelope offsets remain unwrapped',async()=>{
  const h=harness();h.run(`state.project.cues=[{id:'a',position_deg:270,modulation:[{time_s:0,offset_deg:0}]}];state.selectedCueId='a';renderRows=()=>{};renderInspector=()=>{};`);
  const change=h.get('inspectorContent').listeners.change;
  await change({target:{dataset:{cue:'position_deg'},value:'360'}});
  assert.equal(h.run('state.project.cues[0].position_deg'),0);
  await change({target:{dataset:{cue:'point_offset'},value:'360'}});
  assert.equal(h.run('state.project.cues[0].modulation[0].offset_deg'),360);
});
