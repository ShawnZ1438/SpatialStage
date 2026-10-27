/* SpatialStage v0.4 — localhost control; multichannel output rendered in Python.
   Core: project, saving, devices, transport, master, stage setup, AutoCal.
   The audio library, cue list, stage map and inspectors live in editor.js. */
'use strict';
const $ = (id) => document.getElementById(id);
const h = (str) => String(str ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v, fallback=0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
const fmt = (v, d=2) => num(v).toFixed(d);
const state = {project:null, projects:[], selectedCueId:null, selectedLayerId:null, selectedMediaId:null,
  devices:{outputs:[],inputs:[]}, status:null, saveTimer:null, transportEpoch:0, editSpeakers:null,
  lastError:'', outputChoice:'', saveState:'saved'};
let toastTimer;

async function api(path, options={}) {
  const res = await fetch('/api' + path, {headers:options.body && !(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {}, ...options});
  const type = res.headers.get('content-type') || '';
  const response = type.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = response?.detail;
    // Pydantic 422 lists: show the human message of the first problem.
    const text = typeof detail === 'string' ? detail : Array.isArray(detail) && detail[0]?.msg ? detail[0].msg.replace(/^Value error, /, '') : JSON.stringify(detail ?? response);
    throw new Error(text);
  }
  return response;
}
async function post(path, data) { return api(path, {method:'POST', body:JSON.stringify(data ?? {})}); }
function notify(message, error=false) {
  $('eventLog').textContent = message;
  $('toast').textContent = message;
  $('toast').className = 'toast visible' + (error ? ' error':'');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>$('toast').className='toast', 3500);
}
function report(error) { console.error(error); notify(I18N.error(String(error.message || error)), true); }

/* ---------- project data helpers (shared with editor.js) ---------- */
const currentCue = () => state.project?.cues.find(c=>c.id===state.selectedCueId);
const mediaById = id => state.project?.media.find(m=>m.id===id);
function playDuration(m) { const end = m?.trim_end_s || m?.duration_s || 0; return Math.max(0, end - (m?.trim_start_s || 0)); }
// Longest layer (delay + trimmed sound); Infinity when a layer loops.
function cueDuration(c) {
  let longest = 0;
  for (const l of c?.layers || []) {
    if (l.muted) continue;
    const m = mediaById(l.media_id);
    if (m?.loop) return Infinity;
    longest = Math.max(longest, (l.delay_s || 0) + playDuration(m));
  }
  return longest;
}
function cueDisplayNumber(c, index) { return /^待定/.test(c.title) ? '—' : (c.title.match(/^(\d{2})\s*·/)?.[1] || String(index+1).padStart(3,'0')); }
function fmtDuration(seconds) { return seconds === Infinity ? '∞' : seconds ? `${fmt(seconds,1)} s` : '—'; }

async function loadProjectList() {
  state.projects = await api('/projects');
  if (!state.projects.length) {
    const p = await post('/projects', {name:t('newProjectDefault')});
    state.projects = [{id:p.id,name:p.name,count:0}];
  }
  $('projectSelect').innerHTML = state.projects.map(p=>`<option value="${h(p.id)}">${h(p.name)}</option>`).join('');
}
async function switchProject(projectId) {
  await state.mediaOperation;
  await saveNow();
  const incoming=await api('/projects/'+encodeURIComponent(projectId));
  const currentStatus=await api('/audio/status');
  if(currentStatus.project_id!==incoming.id && currentStatus.mixer?.voices?.length){
    if(!confirm(t('confirmSwitchProject'))){
      if(state.project)$('projectSelect').value=state.project.id;
      return;
    }
  }
  state.project=incoming;
  $('projectSelect').value=state.project.id;
  if(currentStatus.project_id===state.project.id && currentStatus.mixer){
    state.status=currentStatus;  // do not replay/re-arm from zero on a browser refresh
  }else{
    state.status=await post('/audio/arm', {project_id:state.project.id,index:0});
  }
  state.selectedCueId=state.project.cues[state.status.next_index]?.id ?? state.project.cues[0]?.id ?? null;
  state.selectedLayerId=null;
  state.selectedMediaId=null;
  $('showName').textContent=state.project.name;
  $('globalRotation').value=fmt(state.project.global_rotation_deg);
  $('distanceComp').checked=!!state.project.distance_compensation;
  renderGlobalEnvelope();
  renderEverything();
}
async function refreshProjectsPreservingSelection() {
  const id = state.project?.id;
  await loadProjectList();
  if (id) $('projectSelect').value = id;
}
function renderSaveState() {
  $('saveIndicator').textContent=t({dirty:'saveDirty',saving:'saving',saved:'saved',error:'saveError'}[state.saveState]);
  $('retrySave').hidden=state.saveState!=='error';
}
const saveQueue = new ProjectSaveQueue({
  snapshot:()=>state.project,
  persist:project=>api('/projects/'+project.id,{method:'PUT',body:JSON.stringify(project)}),
  onState:status=>{state.saveState=status;renderSaveState();},
  onSaved:(snapshot,result,latest)=>{
    if(state.project?.id!==snapshot.id)return;
    state.project.updated_at=result.updated_at;
    if(latest){
      state.project.active_calibration_id=result.active_calibration_id??null;
      state.project.calibration_enabled=!!result.calibration_enabled;
    }
  }
});
function scheduleSave() {
  if (!state.project) return;
  saveQueue.changed();
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(()=>saveNow().catch(report),280);
}
async function saveNow() {
  clearTimeout(state.saveTimer);
  state.saveTimer=null;
  if (!state.project) return;
  saveQueue.changed(); // explicit Save also captures edits without a debounce
  await saveQueue.flush();
}
$('retrySave').addEventListener('click',()=>saveNow().catch(report));
window.addEventListener('beforeunload',e=>{
  if(saveQueue.dirty || saveQueue.running || state.mediaOperation){e.preventDefault();e.returnValue='';}
});
async function loadDevices() {
  const old = state.outputChoice || $('outputSelect').value;
  state.devices=await api('/devices');
  $('outputSelect').innerHTML=`<option value="">${h(t('chooseOutput'))}</option>` + state.devices.outputs.map(d=>`<option value="${d.index}" ${d.channels<4?'disabled':''}>${h(d.name)} (${d.channels} out)${d.channels<4?' — '+h(t('tooFewChannels')):''}</option>`).join('');
  const outputIds=state.devices.outputs.filter(d=>d.channels>=4).map(d=>String(d.index));
  state.outputChoice=outputIds.includes(old) ? old : (outputIds.length===1 ? outputIds[0] : '');
  $('outputSelect').value=state.outputChoice;
  if (state.devices.error) $('audioInfo').textContent=state.devices.error;
}
function renderEverything() {
  renderTransport(); renderMaster(); renderGlobalEnvelope(); renderSaveState();
  globalThis.SpatialEditor?.render(true);
}
function renderGlobalEnvelope() {
  const p=state.project, host=$('globalEnvelopeFields'); if(!p||!host)return;
  $('globalEnvelopeEnabled').checked=!!p.global_envelope_enabled;
  host.innerHTML=(p.global_modulation||[{time_s:0,offset_deg:0}]).map((point,i)=>
    `<div class="global-key-row"><input aria-label="${h(t('globalKeyTime',{n:i+1}))}" type="number" min="0" max="14400" step="0.01" data-global="${i}" data-key="time_s" value="${fmt(point.time_s)}"/><input aria-label="${h(t('globalKeyOffset',{n:i+1}))}" type="number" min="-2160" max="2160" step="0.01" data-global="${i}" data-key="offset_deg" value="${fmt(point.offset_deg)}"/><button data-remove-global="${i}" title="${h(t('remove'))}" ${p.global_modulation.length<=1?'disabled':''}>×</button></div>`
  ).join('');
}
function directionOffsetAt(c,t) {
  if(c.direction_mode==='adsr') {
    const a=c.direction_adsr, duration=Math.max(c.duration_s||1, .001);
    let at=a.attack_s,dt=a.decay_s,rt=a.release_s;
    if(at+dt+rt>duration){const factor=duration/(at+dt+rt);at*=factor;dt*=factor;rt*=factor;}
    if(t<at&&at>0)return a.peak_offset_deg*t/at;
    if(t<at+dt&&dt>0)return a.peak_offset_deg+(a.sustain_offset_deg-a.peak_offset_deg)*(t-at)/dt;
    if(t<duration-rt||rt<=0)return a.sustain_offset_deg;
    if(t>=duration)return a.release_offset_deg;
    return a.sustain_offset_deg+(a.release_offset_deg-a.sustain_offset_deg)*(t-(duration-rt))/rt;
  }
  const pts=c.modulation||[];
  if(!pts.length)return 0;
  if(t<=pts[0].time_s)return pts[0].offset_deg;
  for(let i=1;i<pts.length;i++)if(t<=pts[i].time_s){const prev=pts[i-1],next=pts[i];
    return prev.offset_deg+(next.offset_deg-prev.offset_deg)*(t-prev.time_s)/Math.max(.000001,next.time_s-prev.time_s);}
  return pts.at(-1).offset_deg;
}
function currentShowOffset() {
  const p=state.project;
  if(!p?.global_envelope_enabled)return 0;
  return directionOffsetAt({direction_mode:'keyframes',modulation:p.global_modulation},state.status?.mixer?.show_elapsed_s??0);
}
const startModeLabel = mode => t({replace:'startReplace',layer:'startLayer',queue:'startQueue'}[mode] || 'startReplace');
function renderTransport() {
  const p=state.project;
  if (!p) return;
  const idx=state.status?.next_index ?? 0;
  const next=p.cues[idx];
  $('showName').textContent=p.name;
  $('nextCue').textContent=state.status?.needs_rearm ? t('nextRemoved') : next ? `#${idx+1} · ${next.title}` : t('endOfShow');
  const connected=!!state.status?.connected;
  const mute=state.status?.mixer?.master_mute ?? true;
  let hint = !connected ? t('hintConnect') : mute ? t('hintMuted') : next ? t('hintNext',{mode:startModeLabel(next.start_mode),wait:fmt(next.pre_wait_s),layers:next.layers.length}) : t('hintEnd');
  if(state.status?.needs_rearm)hint=t('hintRemoved');
  else if(state.status?.prepare_error)hint=I18N.error(state.status.prepare_error);
  else if(state.status?.preparing)hint=t('hintPreparing');
  if(state.status?.error)hint=I18N.error(state.status.error);
  $('playbackHint').textContent=hint;
  $('systemState').innerHTML=`<i></i> ${h(connected ? (mute ? t('connectedMuted'):t('engineReady')) : t('engineOffline'))}`;
  $('systemState').className='status'+(connected && !mute?' ready':'');
  $('goButton').disabled=!next || !connected || mute || state.status?.ready===false || !!state.status?.error;
  $('cutGoButton').disabled=!next || !connected || mute || !!state.status?.error;
  $('connectAudio').textContent=state.status?.connected ? t('disconnectAudio') : t('connectAudio');
}
function renderMaster() {
  const mix=state.status?.mixer;
  if(!mix) return;
  $('masterDbLabel').textContent=`${fmt(mix.master_db,0)} dB`;
  if(document.activeElement!==$('masterSlider')) $('masterSlider').value=mix.master_db;
  const mute=!!mix.master_mute;
  $('muteButton').className='mute'+(mute?' on':'');
  $('muteButton').textContent=mute?'● MAIN MUTE · ON':'○ MAIN MUTE · OFF';
  (mix.meters||[0,0,0,0]).forEach((v,i)=>{
    const el=$('meters').children[i]?.querySelector('i');
    if(el) el.style.height = `${Math.max(0,Math.min(100, v*115))}%`;
  });
  $('xrunIndicator').textContent=`XRUNS ${state.status.xruns} · PEAK OVER ${mix.peak_over_count}`;
  if(state.status.connected) {
    $('audioInfo').textContent=`48 kHz · 4 ch · ${mute?t('safeMute'):t('outputActive')}${state.status.error?' · '+I18N.error(state.status.error):''}`;
  }
}
async function poll() {
  try {
    state.status=await api('/audio/status');
    renderTransport(); renderMaster(); globalThis.SpatialEditor?.render();
  } catch(e){ if(state.lastError!==e.message){state.lastError=e.message;report(e);} }
}
async function action(path,payload={},message=''){
  const safetyCommand=['/audio/stop','/audio/panic','/audio/disconnect'].includes(path);
  if(safetyCommand)state.transportEpoch++;
  const epoch=state.transportEpoch;
  try {
    if(['/audio/go','/audio/arm','/audio/skip','/audio/audition','/audio/audition-media'].includes(path)){
      await saveNow();
      if(epoch!==state.transportEpoch)return; // STOP/PANIC cancels a waiting GO
    }
    state.status=await post(path,payload);renderTransport();renderMaster();globalThis.SpatialEditor?.render();if(message)notify(message);
    return true;
  }
  catch(e){report(e);return false;}
}
async function mediaMutation(operation) {
  while (state.mediaOperation) await state.mediaOperation;
  let finish;
  state.mediaOperation = new Promise(resolve=>{finish=resolve;});
  try { return await operation(); }
  finally { state.mediaOperation=null; finish(); }
}
// Files go into the audio library only; drag them into cues from there.
async function uploadFiles(files) {
  if(!files?.length || !state.project) return [];
  return mediaMutation(async()=>{
  const fd=new FormData();
  for(const file of files) fd.append('files',file,file.name);
  $('saveIndicator').textContent=t('importing');
  try {
    await saveNow();
    const data=await api('/projects/'+state.project.id+'/upload?create_cues=false',{method:'POST',body:fd});
    // Merge only the new library items; never restore deleted cues or stale editor fields.
    const known=new Set(state.project.media.map(m=>m.id));
    state.project.media.push(...data.project.media.filter(m=>data.media_ids.includes(m.id) && !known.has(m.id)));
    await saveNow();
    await refreshProjectsPreservingSelection();
    renderEverything();
    notify(t('imported',{n:data.added})+(data.ignored.length?t('importSkipped',{n:data.ignored.length}):''));
    return data.media_ids;
  } catch(e){report(e);renderSaveState();return [];}
  });
}

$('projectSelect').addEventListener('change',e=>switchProject(e.target.value).catch(report));
$('renameProject').addEventListener('click',async()=>{
  if(!state.project)return;
  const name=prompt(t('promptRename'),state.project.name);
  if(!name?.trim())return;
  state.project.name=name.trim().slice(0,100);
  $('showName').textContent=state.project.name;
  try {await saveNow();await refreshProjectsPreservingSelection();notify(t('projectRenamed'));}catch(e){report(e);}
});
$('newProject').addEventListener('click',async()=>{
  const name=prompt(t('promptNewProject'),t('newProjectDefault'));if(!name?.trim())return;
  try {await saveNow();const p=await post('/projects',{name:name.trim()});await refreshProjectsPreservingSelection();await switchProject(p.id);notify(t('projectCreated',{name:p.name}));}catch(e){report(e);}
});
$('exportProject').addEventListener('click',async()=>{
  try {await saveNow();if(state.project) window.location.href=`/api/projects/${state.project.id}/export`;}catch(e){report(e);}
});
$('refreshDevices').addEventListener('click',()=>loadDevices().then(()=>notify(t('devicesRefreshed'))).catch(report));
$('outputSelect').addEventListener('change',e=>state.outputChoice=e.target.value);

$('connectAudio').addEventListener('click',async()=>{
  try {
    if(state.status?.connected){state.status=await post('/audio/disconnect');notify(t('audioDisconnected'));}
    else {
      if(!state.outputChoice) throw new Error(t('chooseFourOutputs'));
      state.status=await post('/audio/connect',{device_index:Number(state.outputChoice)});
      notify(t('audioConnected'));
    }
    renderEverything();
  } catch(e){report(e);}
});
$('muteButton').addEventListener('click',()=>{
  if(!state.status?.connected){notify(t('connectFirst'),true);return;}
  const current=state.status?.mixer;
  action('/audio/master',{mute:!current?.master_mute,db:current?.master_db ?? -18},!current?.master_mute?t('muteOn'):t('muteOff'));
});
$('masterSlider').addEventListener('input',e=>{$('masterDbLabel').textContent=`${e.target.value} dB`;});
$('masterSlider').addEventListener('change',e=>action('/audio/master',{mute:state.status?.mixer?.master_mute??true,db:Number(e.target.value)},t('masterChanged')));
$('speakerTests').addEventListener('click',async()=>{
  const value=prompt(t('promptTestChannel'),'1');
  if(value==null)return;
  const ch=Number(value);
  if(!Number.isInteger(ch)||ch<1||ch>4){notify(t('chooseChannel'),true);return;}
  action('/audio/test',{channel:ch},t('testSent',{ch}));
});
$('globalRotation').addEventListener('input',e=>{
  if(!state.project)return;
  state.project.global_rotation_deg=Math.max(-3600,Math.min(3600,num(e.target.value)));
  scheduleSave();
});
$('globalEnvelopeEnabled').addEventListener('change',e=>{if(state.project){state.project.global_envelope_enabled=e.target.checked;scheduleSave();}});
$('globalAddPoint').addEventListener('click',()=>{if(!state.project)return;
  const arr=state.project.global_modulation;
  arr.push({time_s:Math.round((arr.at(-1)?.time_s||0)+5),offset_deg:arr.at(-1)?.offset_deg||0});
  arr.sort((a,b)=>a.time_s-b.time_s);scheduleSave();renderGlobalEnvelope();});
$('globalEnvelopeFields').addEventListener('change',e=>{
  const i=Number(e.target.dataset.global),key=e.target.dataset.key;
  if(!state.project || !Number.isInteger(i)||!state.project.global_modulation[i]||!key)return;
  const val=num(e.target.value);
  state.project.global_modulation[i][key]=key==='time_s'?Math.min(14400,Math.max(0,val)):Math.min(2160,Math.max(-2160,val));
  state.project.global_modulation.sort((a,b)=>a.time_s-b.time_s);
  renderGlobalEnvelope();scheduleSave();
});
$('globalEnvelopeFields').addEventListener('click',e=>{
  const b=e.target.closest('[data-remove-global]');if(!b||!state.project)return;
  if(state.project.global_modulation.length<=1)return;
  state.project.global_modulation.splice(Number(b.dataset.removeGlobal),1);
  renderGlobalEnvelope();scheduleSave();
});
$('distanceComp').addEventListener('change',e=>{if(!state.project)return;state.project.distance_compensation=e.target.checked;scheduleSave();});
$('goButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id,cut:false},t('fadeGoDone'));});
$('cutGoButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id,cut:true},t('cutGoDone'));});
$('stopButton').addEventListener('click',()=>action('/audio/stop',{},t('stopDone')));
$('skipButton').addEventListener('click',()=>action('/audio/skip',{},t('skipDone')));
$('panicButton').addEventListener('click',()=>action('/audio/panic',{},t('panicDone')));
$('preflight').addEventListener('click',async()=>{
  if(!state.project)return;
  try {await saveNow();const r=await api('/projects/'+state.project.id+'/preflight');
    notify(r.ok?t('preflightOk',{cues:r.count,files:r.files,mib:r.decoded_mib}):t('preflightIssues',{issues:r.issues.map(I18N.error).join(' | ')}),!r.ok);}
  catch(e){report(e);}
});
$('folderInput').addEventListener('change',e=>{uploadFiles([...e.target.files]);e.target.value='';});
$('fileInput').addEventListener('change',e=>{uploadFiles([...e.target.files]);e.target.value='';});
document.addEventListener('keydown',e=>{
  if(e.shiftKey && e.key==='Escape'){e.preventDefault();$('panicButton').click();return;}
  if(e.repeat || e.metaKey || e.ctrlKey || e.altKey && e.code!=='ArrowDown')return;
  const tag=e.target.tagName;
  if(['INPUT','TEXTAREA','SELECT'].includes(tag)||e.target.isContentEditable||$('stageDialog').open||$('autocalDialog').open)return;
  // Space is always GO outside text fields. A focused button/link/summary is blurred
  // first so its native Space activation never fires as well (no double GO, no re-click).
  if(e.code==='Space'){e.preventDefault();if(['BUTTON','A','SUMMARY'].includes(tag))e.target.blur?.();$('goButton').click();}
  else if(e.key.toLowerCase()==='c' && !e.shiftKey){e.preventDefault();$('cutGoButton').click();}
  else if(e.key.toLowerCase()==='s' && !e.shiftKey){e.preventDefault();$('stopButton').click();}
  else if(e.altKey && e.key==='ArrowDown'){e.preventDefault();$('skipButton').click();}
  else if(e.shiftKey && e.key==='Escape'){e.preventDefault();$('panicButton').click();}
});
function speakerXY(s) {const a=s.angle_deg*Math.PI/180;return {x_m:s.distance_m*Math.sin(a),y_m:s.distance_m*Math.cos(a)};}
function renderSpeakerFields() {
  $('speakerFields').innerHTML=`<div class="speaker-grid"><small>${h(t('speaker'))}</small><small>${h(t('speakerX'))}</small><small>${h(t('speakerY'))}</small><small>${h(t('outputCh'))}</small><small>${h(t('trimDb'))}</small></div>`+
    state.editSpeakers.map((s,i)=>`<div class="speaker-grid"><input data-speaker="${i}" data-key="name" type="text" value="${h(s.name)}"/><input data-speaker="${i}" data-key="x_m" type="number" step="0.01" value="${fmt(s.x_m)}"/><input data-speaker="${i}" data-key="y_m" type="number" step="0.01" value="${fmt(s.y_m)}"/><input data-speaker="${i}" data-key="output_channel" type="number" min="1" max="4" step="1" value="${s.output_channel}"/><input data-speaker="${i}" data-key="trim_db" type="number" min="-30" max="12" step="0.1" value="${fmt(s.trim_db,1)}"/></div>`).join('');
}
$('settingsToggle').addEventListener('click',()=>{
  if(!state.project)return;
  state.editSpeakers=structuredClone(state.project.speakers).map(s=>({...s,...speakerXY(s)}));
  renderSpeakerFields();
  $('calibrationHints').textContent=t('setupHint');
  renderSetupMap();
  $('stageDialog').showModal();
});
$('speakerFields').addEventListener('change',e=>{
  const i=Number(e.target.dataset.speaker),key=e.target.dataset.key;
  if(!Number.isInteger(i)||!state.editSpeakers?.[i]||!key)return;
  const s=state.editSpeakers[i];s[key]=e.target.type==='number'?num(e.target.value):e.target.value;
  if(key==='x_m'||key==='y_m'){
    const dist=Math.hypot(s.x_m,s.y_m);
    if(dist>.0001){s.distance_m=Math.round(dist*10000)/10000;s.angle_deg=Math.round(((Math.atan2(s.x_m,s.y_m)*180/Math.PI+360)%360)*100)/100;}
  }
  renderSetupMap();
});
// Theoretical centre-point hints drawn on the map; nothing is applied automatically.
function renderSetupMap() {
  const host=$('setupMap'), speakers=state.editSpeakers;
  if(!host||!speakers)return;
  try {
    const far=Math.max(...speakers.map(s=>s.distance_m)), sorted=speakers.map(s=>s.distance_m).sort((a,b)=>a-b);
    const median=(sorted[1]+sorted[2])/2;
    const notes=speakers.map(s=>`${fmt(s.angle_deg,1)}° · ${fmt(s.distance_m,2)} m · +${fmt((far-s.distance_m)/0.343,2)} ms · ${fmt(20*Math.log10(s.distance_m/median),1)} dB`);
    host.innerHTML=StageMap.svg({speakers,notes,size:520,labels:stageLabels()});
  } catch(e) { host.textContent=t('mapUnavailable')+e.message; }
}
const stageLabels = () => ({front:t('mapFront'), actor:t('mapActor')});
function stagedSpeakerPayload() {return state.editSpeakers.map(({x_m,y_m,...s})=>s);}
$('previewSettings').addEventListener('click',async()=>{
  if(!state.project)return;
  try {const candidate={...state.project,speakers:stagedSpeakerPayload()};
    const r=await post('/calibration/preview',candidate);
    $('calibrationHints').textContent=r.speaker_hints.map(s=>t('calibrationLine',{ch:s.channel,name:s.name,angle:fmt(s.angle_deg),dist:fmt(s.distance_m,2),face:fmt(s.pointing_at_center_deg),delay:fmt(s.suggested_extra_delay_ms),gain:fmt(s.suggested_relative_gain_db)})).join('\n')+'\n'+t('calibrationNote');
  }catch(e){$('calibrationHints').textContent=I18N.error(String(e.message));report(e);}
});
function closeSettings(){$('stageDialog').close();}
$('closeSettings').addEventListener('click',closeSettings);
$('cancelSettings').addEventListener('click',closeSettings);
$('saveSettings').addEventListener('click',async()=>{
  const old=state.project.speakers;
  state.project.speakers=stagedSpeakerPayload();
  try {await saveNow();closeSettings();renderEverything();notify(t('geometrySaved'));}
  catch(e){state.project.speakers=old;report(e);}
});
let dataRoot='';
function renderDataLocation() { $('dataLocation').textContent=t('dataLocation',{path:dataRoot||t('localFolder')}); }
async function boot(){
  try {const health=await api('/health'); dataRoot=health.runtime?.data_root||''; renderDataLocation();
    await loadProjectList();await switchProject(state.projects[0].id);await loadDevices();setInterval(poll,450);notify(t('readyMessage'));}
  catch(e){report(e);}
}

/* AutoCal: explicit XLR measurements with local JSON sessions and review gate. */
const ac = {report:null, overview:null, run:null, loading:false, lastState:'', projectId:null};
const acDialog = $('autocalDialog');
const acPath = () => `/projects/${encodeURIComponent(state.project.id)}/autocal`;
const acPalette = ['#71baf6','#62d5b2','#f2ba76','#b9a3fa'];
function acRenderDevices(config) {
  const inputs=state.devices.inputs||[], outputs=(state.devices.outputs||[]).filter(d=>d.channels>=4);
  $('acInputDevice').innerHTML=`<option value="">${h(t('acChooseInput'))}</option>`+inputs.map(d=>`<option value="${d.index}">${h(d.name)} (${d.channels} in)</option>`).join('');
  $('acOutputDevice').innerHTML=`<option value="">${h(t('acChooseOutput'))}</option>`+outputs.map(d=>`<option value="${d.index}">${h(d.name)} (${d.channels} out)</option>`).join('');
  $('acInputDevice').value=config.input_device_index==null?'':String(config.input_device_index);
  const out=config.output_device_index??(state.outputChoice!==''?Number(state.outputChoice):null);
  $('acOutputDevice').value=out==null?'':String(out);
  $('acInputChannel').value=config.input_channel??1;
  $('acLevel').value=String(config.stimulus_dbfs??-30);
}
function acCurrentConfig() {
  return {
    measurement_points:1, optimization:'balanced', microphone_type:'xlr', experimental_eq:false,
    input_device_index:$('acInputDevice').value===''?null:Number($('acInputDevice').value),
    input_channel:Number($('acInputChannel').value),
    output_device_index:$('acOutputDevice').value===''?null:Number($('acOutputDevice').value),
    stimulus_dbfs:Number($('acLevel').value)
  };
}
function acBars(values,units,zeroMin=false) {
  if(!values?.length)return `<span class="micro">${h(t('acNoData'))}</span>`;
  const min=zeroMin?0:Math.min(...values,-65), max=zeroMin?Math.max(...values,1):Math.max(...values,-12);
  return `<svg viewBox="0 0 540 126" role="img" aria-label="${h(t('acLevels'))}">
    ${values.map((v,i)=>{
      const y=9+i*29;
      const x=70,available=340;
      const norm=Math.max(0,Math.min(1,(v-min)/(max-min||1)));
      return `<text x="6" y="${y+12}" fill="#bad1dc" font-size="11">CH${i+1}</text><rect x="${x}" y="${y}" width="${available}" height="17" rx="4" fill="#2e3f4d"/><rect x="${x}" y="${y}" width="${Math.max(2,norm*available)}" height="17" rx="4" fill="${acPalette[i]}"/><text x="${x+available+12}" y="${y+13}" fill="#c8d6e1" font-size="11">${fmt(v,2)} ${units}</text>`;
    }).join('')}
  </svg>`;
}
function acResponseCurve(results) {
  if(!results?.length)return `<span class="micro">${h(t('acNoCurves'))}</span>`;
  const width=540, height=210, left=45,right=13,top=15,bottom=29, x=(i)=>left+i*(width-left-right)/6;
  const y=(db)=>top+(24-Math.max(-24,Math.min(24,db)))/48*(height-top-bottom);
  return `<svg viewBox="0 0 ${width} ${height+15}" role="img" aria-label="${h(t('acResponse'))}">
    ${[-24,-12,0,12,24].map(v=>`<line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="#405565" stroke-dasharray="3 5"/><text x="3" y="${y(v)+4}" font-size="10" fill="#9db0bc">${v}dB</text>`).join('')}
    ${[125,250,500,1000,2000,4000,8000].map((v,i)=>`<text x="${x(i)}" y="${height+7}" font-size="9" fill="#9db0bc" text-anchor="middle">${v>=1000?v/1000+'k':v}</text>`).join('')}
    ${results.map((r,i)=>`<polyline fill="none" stroke-width="2.6" stroke="${acPalette[i]}" points="${(r.frequency_db_relative_to_1khz||[]).map((v,j)=>x(j)+','+y(v)).join(' ')}"/>`).join('')}
    ${results.map((r,i)=>`<circle cx="${left+12+i*74}" cy="${height+22}" r="4" fill="${acPalette[i]}"/><text x="${left+23+i*74}" y="${height+26}" font-size="10" fill="#bccfd9">CH${r.channel}</text>`).join('')}
  </svg>`;
}
function acRenderReport() {
  const r=ac.report;
  if(!r) {
    $('acMetrics').innerHTML=`<p class="micro">${h(t('acNoSession'))}</p>`;
    $('acLevelChart').innerHTML='';$('acDelayChart').innerHTML='';$('acFrequencyChart').innerHTML='';
  } else {
    const rows=r.results||[], rec=r.recommendations||{};
    const quality=r.quality_ok ? `<p class="ac-success">${h(t('acQualityOk'))}</p>` : `<p class="ac-alert">${h(t('acQualityBad'))}</p>`;
    $('acMetrics').innerHTML=`<p class="micro">${h(t('acSessionLine',{id:r.id,at:r.created_at,status:r.status}))}</p>`+
      `<table class="ac-metric-table"><thead><tr><th>${h(t('acColChannel'))}</th><th>${h(t('acColArrival'))}</th><th>${h(t('acColLevel'))}</th><th>SNR</th><th>${h(t('acColTrim'))}</th><th>${h(t('acColDelay'))}</th><th>${h(t('acColResult'))}</th></tr></thead><tbody>`+
      rows.map((a,i)=>`<tr><td>CH${a.channel}</td><td>${fmt(a.arrival_ms,2)} ms</td><td>${fmt(a.relative_input_dbfs,1)} dBFS</td><td>${fmt(a.snr_db,1)} dB</td><td>${fmt(rec.channel_gain_db?.[i]??0)} dB</td><td>${fmt(rec.channel_delay_ms?.[i]??0,3)} ms</td><td>${a.passed?'✓':'⚠'}</td></tr>`).join('')+
      `</tbody></table>${quality}`+
      (rec.warnings||[]).map(w=>`<p class="ac-alert">${h(w)}</p>`).join('')+
      `<p class="micro">${h(t('acFootnote'))}</p>`;
    $('acLevelChart').innerHTML=acBars(rows.map(a=>a.relative_input_dbfs),'dBFS');
    $('acDelayChart').innerHTML=acBars(rows.map(a=>a.arrival_ms),'ms',true);
    $('acFrequencyChart').innerHTML=acResponseCurve(rows);
  }
  const overview=ac.overview;
  $('acActive').textContent=overview?.enabled?t('acActiveOn',{id:overview.active_calibration_id}):t('acActiveOff');
  acUpdateApplyButton();
}
function acUpdateApplyButton() {
  const r=ac.report, running=['running','cancelling'].includes(ac.run?.state);
  $('acApply').disabled=!(r?.status==='review_required' && r.quality_ok &&
    $('acApproveCheck').checked && $('acApproveText').value.trim()==='APPLY' &&
    !running && !state.status?.connected && state.status?.mixer?.master_mute !== false &&
    !(state.status?.mixer?.voices||[]).length);
  $('acDisable').disabled=!ac.overview?.enabled || !!state.status?.connected || running;
  $('acStart').disabled=running;
  $('acCancel').disabled=!running;
  $('acSaveConfig').disabled=running;
  $('acProgress').textContent=running ? t('acRunning',{message:ac.run.message}) :
    ac.run?.state==='cancelled' ? t('acCancelled') :
    ac.run?.state==='failed' ? t('acFailed',{message:I18N.error(ac.run.message)}) :
    ac.run?.state==='completed' ? t('acCompleted') : t('acIdle');
}
async function acLoad(selectedId=null) {
  if(!state.project)return;
  const id=state.project.id;
  const overview=await api(`/projects/${id}/autocal`);
  if(state.project?.id!==id)return;
  ac.overview=overview; ac.run=overview.run; ac.projectId=id;
  const menu=$('acSessionSelect'), choice=selectedId||menu.value||overview.sessions[0]?.id||'';
  menu.innerHTML=`<option value="">${h(t('acChooseSession'))}</option>`+overview.sessions.map(s=>
    `<option value="${h(s.id)}">${h(s.created_at?.slice(0,19))} · ${h(s.status)} · ${h(s.id.slice(0,5))}</option>`).join('');
  const chosen=overview.sessions.some(s=>s.id===choice)?choice:(overview.sessions[0]?.id||'');
  menu.value=chosen;
  ac.report=chosen?await api(`/projects/${id}/autocal/sessions/${chosen}`):null;
  acRenderReport();
  return overview;
}
async function acOpen() {
  if(!state.project)return;
  try {
    await saveNow();await loadDevices();
    const v=await acLoad();
    acRenderDevices(v.config);
    $('acSafe').checked=false;$('acApproveCheck').checked=false;$('acApproveText').value='';
    acDialog.showModal();acUpdateApplyButton();
  } catch(e){report(e);}
}
$('autocalOpen').addEventListener('click',acOpen);
$('autocalClose').addEventListener('click',()=>acDialog.close());
$('acSessionSelect').addEventListener('change',async e=>{
  try {ac.report=e.target.value?await api(acPath()+`/sessions/${e.target.value}`):null;
    $('acApproveCheck').checked=false;$('acApproveText').value='';acRenderReport();}catch(err){report(err);}
});
async function acSave(){
  if(!state.project)throw Error(t('noProject'));
  const config=acCurrentConfig();
  if(config.input_device_index===null||config.output_device_index===null)throw Error(t('acSelectBoth'));
  const selected=(state.devices.inputs||[]).find(d=>d.index===config.input_device_index);
  if(!selected||selected.channels<config.input_channel)throw Error(t('acChannelMissing'));
  const val=await api(acPath()+'/config',{method:'PUT',body:JSON.stringify(config)});
  ac.overview.config=val;return val;
}
$('acSaveConfig').addEventListener('click',async()=>{try{await acSave();notify(t('acSaved'));}catch(e){report(e);}});
$('acStart').addEventListener('click',async()=>{
  try {
    if(!$('acSafe').checked)throw Error(t('acConfirmSafe'));
    if(state.status?.connected)throw Error(t('acDisconnectFirst'));
    await acSave();
    ac.run=await post(acPath()+'/start',{hardware_ready:true});
    $('acApproveCheck').checked=false;$('acApproveText').value='';acUpdateApplyButton();
    notify(t('acStarted'));
  }catch(e){report(e);}
});
$('acCancel').addEventListener('click',async()=>{
  try {ac.run=await post(acPath()+'/cancel');acUpdateApplyButton();}catch(e){report(e);}
});
async function acPoll(){
  if(!acDialog.open||!state.project||ac.projectId!==state.project.id||!['running','cancelling'].includes(ac.run?.state))return;
  try{
    const fresh=await api(acPath()+'/run');
    const prev=ac.run?.state;ac.run=fresh;acUpdateApplyButton();
    if(['running','cancelling'].includes(prev)&&!['running','cancelling'].includes(fresh.state)){
      await acLoad(fresh.state==='completed'?fresh.session_id:null);
      if(fresh.state==='failed')report(new Error(fresh.message));
    }
  }catch(e){report(e);}
}
setInterval(acPoll,800);
$('acApproveCheck').addEventListener('change',acUpdateApplyButton);
$('acApproveText').addEventListener('input',acUpdateApplyButton);
$('acApply').addEventListener('click',async()=>{
  if(!ac.report||$('acApply').disabled)return;
  try {
    const r=await post(acPath()+`/sessions/${ac.report.id}/apply`,{confirm:'APPLY'});
    state.project=r.project;
    await acLoad(r.session.id);
    notify(t('acApplied'));
  }catch(e){report(e);}
});
$('acDisable').addEventListener('click',async()=>{
  if(!ac.overview?.enabled)return;
  try {
    const r=await post(acPath()+'/disable');
    state.project=r.project;await acLoad();
    notify(t('acDisabled'));
  }catch(e){report(e);}
});

/* Language: re-render everything that is built in script. */
I18N.onChange(()=>{
  renderEverything(); renderDataLocation();
  if(state.editSpeakers && $('stageDialog').open){renderSpeakerFields();renderSetupMap();}
  if(acDialog.open){acRenderDevices(acCurrentConfig());acRenderReport();}
  $('outputSelect').options[0] && ($('outputSelect').options[0].textContent=t('chooseOutput'));
});

boot();

/* Direct cue controls (top bar), shared with the cue list. */
let auditionBusy=false, lastAuditionAt=0;
async function prepareCue(id) {
  if(!id)return;
  state.selectedCueId=id;
  if(await action('/audio/arm',{project_id:state.project.id,cue_id:id},t('cuePrepared')))renderEverything();
}
function auditionReady() {
  if(!state.status?.connected){notify(t('auditionNotConnected'),true);return false;}
  if(state.status?.mixer?.master_mute){notify(t('auditionMuted'),true);return false;}
  return true;
}
async function auditionCue(id) {
  if(!id || auditionBusy || Date.now()-lastAuditionAt<600 || !auditionReady())return;
  auditionBusy=true;state.selectedCueId=id;
  try {if(await action('/audio/audition',{project_id:state.project.id,cue_id:id},t('auditionDone')))lastAuditionAt=Date.now();}
  finally {auditionBusy=false;renderEverything();}
}
async function auditionMedia(id) {
  if(!id || auditionBusy || !auditionReady())return;
  auditionBusy=true;
  try {await action('/audio/audition-media',{project_id:state.project.id,media_id:id},t('auditionMediaDone',{name:mediaById(id)?.name||''}));}
  finally {auditionBusy=false;}
}
async function moveCue(id,to) {
  const from=state.project.cues.findIndex(c=>c.id===id);
  if(from<0 || to<0 || to>=state.project.cues.length || from===to)return;
  try {
    const status=await api('/audio/status');
    if(status.mixer?.voices?.length){notify(t('stopBeforeReorder'),true);return;}
    await saveNow();
    const old=[...state.project.cues];
    state.project.cues.splice(to,0,state.project.cues.splice(from,1)[0]);
    state.selectedCueId=id;
    try {scheduleSave();await saveNow();notify(t('orderSaved',{n:to+1}));}
    catch(e){state.project.cues=old;throw e;}
    renderEverything();
  } catch(e){report(e);}
}
$('cueFirst').onclick=()=>prepareCue(state.project?.cues[0]?.id);
$('cueStart').onclick=()=>prepareCue(state.selectedCueId);
$('cueAudition').onclick=()=>auditionCue(state.selectedCueId);
$('cueUp').onclick=()=>moveCue(state.selectedCueId,state.project.cues.findIndex(c=>c.id===state.selectedCueId)-1);
$('cueDown').onclick=()=>moveCue(state.selectedCueId,state.project.cues.findIndex(c=>c.id===state.selectedCueId)+1);
