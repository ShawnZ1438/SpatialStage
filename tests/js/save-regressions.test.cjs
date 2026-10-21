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
    structuredClone, FormData, document:{getElementById:get,addEventListener(){},querySelector(){return null;}},
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
