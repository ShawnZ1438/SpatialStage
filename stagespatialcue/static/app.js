/* SpatialStage v0.2 — localhost control; multichannel output rendered in Python. */
'use strict';
const $ = (id) => document.getElementById(id);
const h = (str) => String(str ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v, fallback=0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
const fmt = (v, d=2) => num(v).toFixed(d);
const state = {project:null, projects:[], selectedCueId:null, devices:{outputs:[],inputs:[]}, status:null, saveTimer:null, saveBusy:false, editSpeakers:null, selectedPoint:0, draggingDial:false, draggingPoint:-1, lastError:'', outputChoice:'', inputChoice:''};
let toastTimer;

async function api(path, options={}) {
  const res = await fetch('/api' + path, {headers:options.body && !(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {}, ...options});
  const type = res.headers.get('content-type') || '';
  const response = type.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = response?.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail ?? response));
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
function report(error) { console.error(error); notify(String(error.message || error), true); }
const currentCue = () => state.project?.cues.find(c=>c.id===state.selectedCueId);

async function loadProjectList() {
  state.projects = await api('/projects');
  if (!state.projects.length) {
    const p = await post('/projects', {name:'New stage session'});
    state.projects = [{id:p.id,name:p.name,count:0}];
  }
  $('projectSelect').innerHTML = state.projects.map(p=>`<option value="${h(p.id)}">${h(p.name)}</option>`).join('');
}
async function switchProject(projectId) {
  if (state.saveTimer) await saveNow();
  const incoming=await api('/projects/'+encodeURIComponent(projectId));
  const currentStatus=await api('/audio/status');
  if(currentStatus.project_id!==incoming.id && currentStatus.mixer?.voices?.length){
    if(!confirm('Switching projects will mute/stop active audio. Continue?')){
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
  state.selectedPoint=0;
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
function scheduleSave() {
  if (!state.project) return;
  $('saveIndicator').textContent='Unsaved changes';
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(()=>saveNow().catch(report),280);
}
async function saveNow() {
  clearTimeout(state.saveTimer);
  state.saveTimer=null;
  if (!state.project || state.saveBusy) return;
  state.saveBusy=true;
  try {
    const result = await api('/projects/'+state.project.id,{method:'PUT',body:JSON.stringify(state.project)});
    state.project.updated_at=result.updated_at;
    $('saveIndicator').textContent='Saved locally';
  } catch (e) { $('saveIndicator').textContent='Save failed'; report(e); }
  finally { state.saveBusy=false; }
}
async function loadDevices() {
  const old = state.outputChoice || $('outputSelect').value;
  state.devices=await api('/devices');
  $('outputSelect').innerHTML='<option value="">Choose output interface</option>' + state.devices.outputs.map(d=>`<option value="${d.index}" ${d.channels<4?'disabled':''}>${h(d.name)} (${d.channels} out)${d.channels<4?' — too few':''}</option>`).join('');
  const outputIds=state.devices.outputs.filter(d=>d.channels>=4).map(d=>String(d.index));
  state.outputChoice=outputIds.includes(old) ? old : (outputIds.length===1 ? outputIds[0] : '');
  $('outputSelect').value=state.outputChoice;
  if (state.devices.error) $('audioInfo').textContent=state.devices.error;
}
function renderEverything() {
  renderTransport(); renderRows(); renderInspector(); renderMaster(); renderGlobalEnvelope();
}
function renderGlobalEnvelope() {
  const p=state.project, host=$('globalEnvelopeFields'); if(!p||!host)return;
  $('globalEnvelopeEnabled').checked=!!p.global_envelope_enabled;
  host.innerHTML=(p.global_modulation||[{time_s:0,offset_deg:0}]).map((point,i)=>
    `<div class="global-key-row"><input aria-label="Global keyframe ${i+1} time seconds" type="number" min="0" max="14400" step="0.01" data-global="${i}" data-key="time_s" value="${fmt(point.time_s)}"/><input aria-label="Global keyframe ${i+1} angle offset" type="number" min="-2160" max="2160" step="0.01" data-global="${i}" data-key="offset_deg" value="${fmt(point.offset_deg)}"/><button data-remove-global="${i}" title="Remove point" ${p.global_modulation.length<=1?'disabled':''}>×</button></div>`
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
function renderTransport() {
  const p=state.project;
  if (!p) return;
  const idx=state.status?.next_index ?? 0;
  const next=p.cues[idx];
  $('showName').textContent=p.name;
  $('nextCue').textContent=next ? `${String(idx+1).padStart(3,'0')}  ·  ${next.title}` : '— END OF SHOW —';
  const connected=!!state.status?.connected;
  const mute=state.status?.mixer?.master_mute ?? true;
  $('playbackHint').textContent= !connected ? 'Connect a 4-output CoreAudio device' : mute ? 'OUTPUT MUTED · unmute deliberately before GO' : next ? `${next.start_mode.toUpperCase()} · ${fmt(next.pre_wait_s)} s pre-wait` : 'Select a row and ARM to play it again';
  $('systemState').innerHTML=`<i></i> ${connected ? (mute ? 'Connected / muted':'Engine ready') : 'Engine offline'}`;
  $('systemState').className='status'+(connected && !mute?' ready':'');
  $('goButton').disabled=!next || !connected || mute;
  $('cutGoButton').disabled=!next || !connected || mute;
  $('cueCount').textContent=`${p.cues.length} cues`;
}
function cueState(c, i) {
  const voices=state.status?.mixer?.voices ?? [];
  const active=voices.find(v=>v.cue_id===c.id && v.state==='playing');
  const pending=voices.find(v=>v.cue_id===c.id && v.state==='queued');
  if(active) return ['playing','LIVE'];
  if(pending) return ['queued','WAIT'];
  if(i===(state.status?.next_index ?? 0)) return ['next','NEXT'];
  if(i<(state.status?.next_index ?? 0)) return ['done','FIRED'];
  return ['idle','STBY'];
}
function renderRows() {
  if(!state.project) return;
  const cues=state.project.cues;
  $('emptyCues').style.display=cues.length?'none':'block';
  $('cueRows').innerHTML=cues.map((c,i)=>{
    const [s,txt]=cueState(c,i);
    const sel=c.id===state.selectedCueId?' selected':'';
    const duration = c.duration_s ? `${fmt(c.duration_s,1)} s` : '—';
    return `<tr class="${sel}" data-id="${h(c.id)}" aria-selected="${!!sel}">
      <td><span class="cue-state ${s}"><i></i>${txt}</span></td><td class="number">${String(i+1).padStart(3,'0')}</td>
      <td><span class="cue-title" title="${h(c.title)}">${h(c.title)}</span><span class="cue-subtitle" title="${h(c.filename)}">${h(c.filename)}</span></td>
      <td>${{replace:'REPLACE',layer:'LAYER',queue:'WAIT'}[c.start_mode]||'—'}</td><td class="deg">${fmt(c.position_deg)}°</td><td>${fmt(c.gain_db,1)} dB</td><td>${duration}</td>
      <td><div class="row-btns"><button data-move="-1" title="Move up" ${i===0?'disabled':''}>↑</button><button data-move="1" title="Move down" ${i===cues.length-1?'disabled':''}>↓</button></div></td>
    </tr>`;
  }).join('');
  const voices=state.status?.mixer?.voices??[];
  $('queueSummary').textContent=voices.length?voices.map(v=>`${v.title} (${v.state} ${fmt(v.elapsed_s,1)} s)`).join(' · '):'No scheduled audio';
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
    $('audioInfo').textContent=`48 kHz · 4 ch · ${mute?'SAFE MUTE ACTIVE':'Output active'}${state.status.error?' · '+state.status.error:''}`;
  }
}
function inputField(label,key,value,opts={}) {
  const type=opts.type||'number';const step=opts.step??'0.01';
  return `<label>${h(label)}<input data-cue="${h(key)}" type="${type}" ${type==='number'?`step="${step}" ${opts.min!=null?`min="${opts.min}"`:''} ${opts.max!=null?`max="${opts.max}"`:''}`:''} value="${h(value)}" /></label>`;
}
function selectField(label,key,value,choices) {
  return `<label>${h(label)}<select data-cue="${h(key)}">${choices.map(([id,title])=>`<option value="${id}" ${id===value?'selected':''}>${h(title)}</option>`).join('')}</select></label>`;
}
function renderInspector() {
  const c=currentCue();
  $('inspectTitle').textContent=c?.title ?? 'Select a cue';
  $('armSelected').disabled=!c;
  if(!c){$('inspectorContent').innerHTML='<p class="small-muted">Select a cue from the stack to edit it.</p>';return;}
  $('inspectorContent').innerHTML=`
    <div class="dial-wrap"><div id="spatialDial"></div><div class="dial-caption">Drag the pointer to place a virtual source · 0.01° precision</div></div>
    <div class="section-label">POSITION & LEVEL</div>
    <div class="field-row three">
      ${inputField('Bearing (°)','position_deg',fmt(c.position_deg),{min:0,max:359.99})}
      ${inputField('Cue gain (dB)','gain_db',fmt(c.gain_db),{min:-90,max:12})}
      <label>Media duration (s)<input type="number" readonly value="${fmt(c.duration_s,2)}" title="Detected from decoded media; not editable"></label>
    </div>
    <div class="section-label">TRIGGER & TRANSITION</div>
    <label class="full-label">Cue title<input type="text" data-cue="title" value="${h(c.title)}"></label>
    <div class="field-row" style="margin-top:11px">
      ${selectField('Start action','start_mode',c.start_mode,[['replace','Replace / de-click'],['layer','Layer / parallel'],['queue','Wait for active sounds']])}
      ${selectField('Auto-next','continue_mode',c.continue_mode,[['manual','Manual GO'],['auto_continue','From this cue start'],['auto_follow','After this cue ends']])}
    </div>
    <div class="field-row" style="margin-top:11px">
      ${inputField('Fade in (s)','fade_in_s',fmt(c.fade_in_s),{min:0})}
      ${inputField('Fade out (s)','fade_out_s',fmt(c.fade_out_s),{min:0})}
    </div>
    <div class="field-row" style="margin-top:11px">
      ${selectField('Replace transition','replace_style',c.replace_style||'crossfade',[['crossfade','Crossfade'],['cut','De-click cut (5 ms)']])}
      ${inputField('Transition (s)','transition_s',fmt(c.transition_s),{min:0,max:60})}
    </div>
    <div class="field-row" style="margin-top:11px">
      ${inputField('Pre-wait before audio (s)','pre_wait_s',fmt(c.pre_wait_s),{min:0})}
      <div class="extra-hint">CUT GO overrides replacement style and pre-wait. Fade GO respects Cue start mode.</div>
    </div>
    <div class="field-row" style="margin-top:11px">
      ${inputField('Post-wait auto-next (s)','post_wait_s',fmt(c.post_wait_s),{min:0})}
      <div class="extra-hint">Manual mode ignores post-wait. Queued mode waits for the last active cue.</div>
    </div>
    <div class="section-label">ANGULAR DIRECTION ENVELOPE</div>
    ${selectField('Modulation curve','direction_mode',c.direction_mode||'keyframes',[['keyframes','Free keyframes / moving sound'],['adsr','ADSR direction offset']])}
    <div class="direction-mode-help">Final angle = cue base + cue offset + global rotation + global show offset. Values are signed, unwrapped degrees; +360° is one clockwise revolution. ADSR below changes <b>direction</b>, not sound volume.</div>
    ${c.direction_mode==='adsr' ? `
      <div class="adsr-meta">
        ${inputField('Attack (s)','adsr_attack_s',fmt(c.direction_adsr.attack_s),{min:0})}
        ${inputField('Peak offset (°)','adsr_peak_offset_deg',fmt(c.direction_adsr.peak_offset_deg))}
        ${inputField('Decay (s)','adsr_decay_s',fmt(c.direction_adsr.decay_s),{min:0})}
        ${inputField('Sustain offset (°)','adsr_sustain_offset_deg',fmt(c.direction_adsr.sustain_offset_deg))}
        ${inputField('Release (s)','adsr_release_s',fmt(c.direction_adsr.release_s),{min:0})}
        ${inputField('Release final offset (°)','adsr_release_offset_deg',fmt(c.direction_adsr.release_offset_deg))}
      </div>` : `<div class="section-label">FREE KEYFRAMES <button id="addPoint" class="secondary">＋ KEYFRAME</button></div>`}
    <div id="envelopeHost" class="envelope"></div>
    <div class="envelope-help">X = time within source clip (s); Y = relative angular offset (°). ${c.direction_mode==='adsr'?'ADSR phases are proportional-compressed when the sound is too short.': 'Drag a dot, or click to add a keyframe.'}</div>
    ${c.direction_mode==='keyframes' ? `<div class="point-actions">
      ${inputField('Point time (s)','point_time',fmt(c.modulation[state.selectedPoint]?.time_s??0))}
      ${inputField('Offset (°)','point_offset',fmt(c.modulation[state.selectedPoint]?.offset_deg??0))}
      <button id="deletePoint" class="danger" title="Delete selected keyframe">−</button>
    </div>`:''}
    <div class="extra-hint">Changing angle, gain, ADSR or free keyframes will update active sound after autosave (~300 ms); replacing the media file does not alter pre-scheduled audio buffers.</div>
    <label class="swap-button">⇆ Replace this Cue's audio file<input id="replaceCueAudio" type="file" accept=".wav,.aif,.aiff,.flac,.ogg,.mp3,.aac,.m4a"></label>
    <button id="deleteCue" class="danger" style="margin-top:17px;width:100%">Delete selected cue</button>
  `;
  renderDial(); renderEnvelope();
}
function xyForDeg(angle,r=95,cx=148,cy=125) {return [cx+r*Math.sin(angle*Math.PI/180),cy-r*Math.cos(angle*Math.PI/180)];}
function renderDial() {
  const c=currentCue(); if(!c||!$('spatialDial'))return;
  const stage=state.project;
  const cx=148,cy=125,r=95;
  const [px,py]=xyForDeg(c.position_deg,79,cx,cy);
  const active=state.status?.mixer?.voices?.find(v=>v.cue_id===c.id&&v.state==='playing');
  const previewBearing=(c.position_deg + state.project.global_rotation_deg + currentShowOffset() +
    directionOffsetAt(c,active?.elapsed_s||0)+36000)%360;
  const [gx,gy]=xyForDeg(previewBearing,72,cx,cy);
  const speakerDots=stage.speakers.map((s,i)=>{
    const [x,y]=xyForDeg(s.angle_deg,93,cx,cy);
    return `<g><circle cx="${x}" cy="${y}" r="14" fill="#14384a" stroke="#64b3ce" stroke-width="1.5"/><text x="${x}" y="${y+3.8}" text-anchor="middle" fill="#cceaf8" font-size="10" font-weight="650">${s.output_channel}</text></g>`;
  }).join('');
  $('spatialDial').innerHTML=`<svg id="dialSvg" viewBox="0 0 296 250" role="slider" aria-label="Spatial angle dial" aria-valuemin="0" aria-valuemax="360" aria-valuenow="${c.position_deg}">
    <circle cx="148" cy="125" r="95" fill="none" stroke="#385364" stroke-width="1.5"/>
    <circle cx="148" cy="125" r="70" fill="none" stroke="#304755" stroke-width=".75" stroke-dasharray="2 5"/>
    <path d="M148 21V230 M45 125H251" stroke="#355065" stroke-width="1" stroke-dasharray="3 6"/>
    <text x="148" y="15" fill="#8daab9" font-size="10" text-anchor="middle">0°</text><text x="274" y="129" fill="#8daab9" font-size="10" text-anchor="middle">90°</text><text x="148" y="247" fill="#8daab9" font-size="10" text-anchor="middle">180°</text><text x="24" y="129" fill="#8daab9" font-size="10" text-anchor="middle">270°</text>
    <line x1="148" y1="125" x2="${gx}" y2="${gy}" stroke="#f0bd6c" stroke-width="2" stroke-dasharray="5 4"/><circle cx="${gx}" cy="${gy}" r="5" fill="#f0bd6c"/>
    <line x1="148" y1="125" x2="${px}" y2="${py}" stroke="#52dccd" stroke-width="3.5" stroke-linecap="round"/><circle cx="${px}" cy="${py}" r="8" fill="#52dccd" stroke="#c3fff2" stroke-width="2"/>
    ${speakerDots}<circle cx="148" cy="125" r="19" fill="#193b39" stroke="#51a298" stroke-width="1"/><text x="148" y="129" fill="#a4e7df" text-anchor="middle" font-size="9">ACTOR</text>
  </svg>`;
}
function pointView(c) {
  const duration=Math.max(1,c.duration_s||1,c.modulation.at(-1)?.time_s||0);
  const toX=t=>24+Math.max(0,Math.min(1,t/duration))*288;
  const toY=v=>68-Math.max(-360,Math.min(360,v))*0.13;
  return {duration,toX,toY};
}
function renderEnvelope() {
  const c=currentCue(), host=$('envelopeHost'); if(!c||!host)return;
  const {duration,toX,toY}=pointView(c);
  const points = c.direction_mode==='adsr'
    ? Array.from({length:101},(_,i)=>{const t=i*duration/100;return [toX(t),toY(directionOffsetAt(c,t))];})
    : c.modulation.map(p=>[toX(p.time_s),toY(p.offset_deg)]);
  host.innerHTML=`<svg id="envelopeSvg" viewBox="0 0 336 146" preserveAspectRatio="none" role="img" aria-label="Editable direction modulation envelope">
    <line x1="24" y1="68" x2="312" y2="68" stroke="#4b6980" stroke-width="1"/><line x1="24" y1="9" x2="24" y2="126" stroke="#4b6980"/>
    <path d="M24 21H312 M24 115H312" stroke="#2b3d50" stroke-dasharray="3 5"/>
    <text x="3" y="23" fill="#718ba1" font-size="9">+360</text><text x="13" y="71" fill="#718ba1" font-size="9">0</text><text x="2" y="117" fill="#718ba1" font-size="9">−360</text>
    <text x="25" y="139" fill="#7891a8" font-size="10">0 s</text><text x="311" y="139" text-anchor="end" fill="#7891a8" font-size="10">${fmt(duration,1)} s</text>
    <path d="${points.map(([x,y],i)=>(i?'L':'M')+x+','+y).join(' ')}" stroke="#5bd6ca" fill="none" stroke-width="2.5"/>
    ${c.direction_mode==='keyframes'?points.map(([x,y],i)=>`<circle data-point="${i}" cx="${x}" cy="${y}" r="${i===state.selectedPoint?6:4.5}" fill="${i===state.selectedPoint?'#fff4c5':'#4ed2c4'}" stroke="#3ea89c" stroke-width="1.3"/>`).join(''):''}
  </svg>`;
}
function svgLocal(svg, event) {
  const pt=svg.createSVGPoint();pt.x=event.clientX;pt.y=event.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}
function dialSet(event) {
  const svg=$('dialSvg');if(!svg)return;
  const pt=svgLocal(svg,event);
  const angle=(Math.atan2(pt.x-148,125-pt.y)*180/Math.PI+360)%360;
  const cue=currentCue();if(!cue)return;
  cue.position_deg=Number(Math.min(359.99,Math.round(angle*100)/100).toFixed(2));
  const input=document.querySelector('[data-cue="position_deg"]');if(input)input.value=fmt(cue.position_deg);
  renderDial();renderRows();
}
function envelopePosition(event) {
  const svg=$('envelopeSvg');if(!svg)return null;
  const pt=svgLocal(svg,event),c=currentCue();if(!c)return null;
  const {duration}=pointView(c);
  return {x:pt.x,y:pt.y, time:Math.round(Math.max(0,Math.min(duration,(pt.x-24)/288*duration))*100)/100, offset:Math.round(Math.max(-360,Math.min(360,(68-pt.y)/.13))*100)/100};
}
function pointEdits() {
  const c=currentCue();if(!c)return;
  const p=c.modulation[state.selectedPoint];if(!p)return;
  const timeInput=document.querySelector('[data-cue="point_time"]');if(timeInput)timeInput.value=fmt(p.time_s);
  const offsetInput=document.querySelector('[data-cue="point_offset"]');if(offsetInput)offsetInput.value=fmt(p.offset_deg);
}
async function poll() {
  try {
    state.status=await api('/audio/status');
    renderTransport(); renderRows(); renderMaster();
    if(!state.draggingDial && state.draggingPoint<0)renderDial();
  } catch(e){ if(state.lastError!==e.message){state.lastError=e.message;report(e);} }
}
async function action(path,payload={},message=''){
  try {state.status=await post(path,payload);renderTransport();renderRows();renderMaster();if(message)notify(message);}
  catch(e){report(e);}
}
async function uploadFiles(files) {
  if(!files?.length || !state.project) return;
  const fd=new FormData();
  for(const file of files) fd.append('files',file,file.name);
  $('saveIndicator').textContent='Importing…';
  try {
    await saveNow();
    const data=await api('/projects/'+state.project.id+'/upload',{method:'POST',body:fd});
    state.project=data.project;
    state.selectedCueId=state.selectedCueId ?? state.project.cues[0]?.id;
    await refreshProjectsPreservingSelection();
    renderEverything();
    notify(`Imported ${data.added} audio file(s)${data.ignored.length ? `; skipped ${data.ignored.length}`:''}.`);
  } catch(e){report(e);}finally{$('saveIndicator').textContent='Saved locally';}
}

$('projectSelect').addEventListener('change',e=>switchProject(e.target.value).catch(report));
$('renameProject').addEventListener('click',async()=>{
  if(!state.project)return;
  const name=prompt('Rename show:',state.project.name);
  if(!name?.trim())return;
  state.project.name=name.trim().slice(0,100);
  $('showName').textContent=state.project.name;
  await saveNow();
  await refreshProjectsPreservingSelection();
  notify('Project renamed.');
});
$('newProject').addEventListener('click',async()=>{
  const name=prompt('Name this show / project:','New stage session');if(!name?.trim())return;
  try {await saveNow();const p=await post('/projects',{name:name.trim()});await refreshProjectsPreservingSelection();await switchProject(p.id);notify(`Created project: ${p.name}`);}catch(e){report(e);}
});
$('exportProject').addEventListener('click',()=>{
  if(state.project) window.location.href=`/api/projects/${state.project.id}/export`;
});
$('refreshDevices').addEventListener('click',()=>loadDevices().then(()=>notify('Audio devices refreshed')).catch(report));
$('outputSelect').addEventListener('change',e=>state.outputChoice=e.target.value);

$('connectAudio').addEventListener('click',async()=>{
  try {
    if(state.status?.connected){state.status=await post('/audio/disconnect');notify('Audio interface disconnected and muted.');}
    else {
      if(!state.outputChoice) throw new Error('Choose an interface with at least four separate output channels.');
      state.status=await post('/audio/connect',{device_index:Number(state.outputChoice)});
      notify('4-channel audio connected. Master remains MUTED for safety.');
    }
    renderEverything();
  } catch(e){report(e);}
});
$('muteButton').addEventListener('click',()=>{
  if(!state.status?.connected){notify('Connect an output device first.',true);return;}
  const current=state.status?.mixer;
  action('/audio/master',{mute:!current?.master_mute,db:current?.master_db ?? -18},!current?.master_mute?'Main mute activated.':'Main mute released; verify sound level.');
});
$('masterSlider').addEventListener('input',e=>{$('masterDbLabel').textContent=`${e.target.value} dB`;});
$('masterSlider').addEventListener('change',e=>action('/audio/master',{mute:state.status?.mixer?.master_mute??true,db:Number(e.target.value)},'Master level changed.'));
$('speakerTests').addEventListener('click',async()=>{
  const value=prompt('Send a quiet, 1-second 440 Hz tone to which output channel? (1–4)\nReduce console and master gain before testing.','1');
  if(value==null)return;
  const ch=Number(value);
  if(!Number.isInteger(ch)||ch<1||ch>4){notify('Choose channel 1, 2, 3, or 4.',true);return;}
  action('/audio/test',{channel:ch},`Speaker test sent to output ${ch}.`);
});
$('globalRotation').addEventListener('input',e=>{
  if(!state.project)return;
  state.project.global_rotation_deg=Math.max(-3600,Math.min(3600,num(e.target.value)));
  scheduleSave();renderDial();
});
$('globalEnvelopeEnabled').addEventListener('change',e=>{if(state.project){state.project.global_envelope_enabled=e.target.checked;scheduleSave();renderDial();}});
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
  renderGlobalEnvelope();renderDial();scheduleSave();
});
$('globalEnvelopeFields').addEventListener('click',e=>{
  const b=e.target.closest('[data-remove-global]');if(!b||!state.project)return;
  if(state.project.global_modulation.length<=1)return;
  state.project.global_modulation.splice(Number(b.dataset.removeGlobal),1);
  renderGlobalEnvelope();renderDial();scheduleSave();
});
$('distanceComp').addEventListener('change',e=>{if(!state.project)return;state.project.distance_compensation=e.target.checked;scheduleSave();});
$('goButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id,cut:false},'FADE GO — normal cue rules.');});
$('cutGoButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id,cut:true},'CUT GO — immediately replace, 5 ms de-click.');});
$('stopButton').addEventListener('click',()=>action('/audio/stop',{},'STOP — all active cues fading to zero.'));
$('skipButton').addEventListener('click',()=>action('/audio/skip',{},'SKIP — moved to next cue without playing.'));
$('panicButton').addEventListener('click',()=>action('/audio/panic',{},'PANIC — all audio killed and master muted.'));
$('armSelected').addEventListener('click',()=>{
  const idx=state.project?.cues.findIndex(c=>c.id===state.selectedCueId);
  if(idx>=0)action('/audio/arm',{project_id:state.project.id,index:idx},`Armed cue ${idx+1}.`);
});
$('preflight').addEventListener('click',async()=>{
  if(!state.project)return;
  try {const r=await api('/projects/'+state.project.id+'/preflight');notify(r.ok?`Preflight OK: ${r.count} cues, ${r.decoded_mib} MiB decoded.`:`Preflight issues: ${r.issues.join(' | ')}`,!r.ok);}
  catch(e){report(e);}
});
$('folderInput').addEventListener('change',e=>{uploadFiles([...e.target.files]);e.target.value='';});
$('fileInput').addEventListener('change',e=>{uploadFiles([...e.target.files]);e.target.value='';});
$('cueRows').addEventListener('click',e=>{
  const tr=e.target.closest('tr[data-id]');if(!tr)return;
  const i=state.project.cues.findIndex(c=>c.id===tr.dataset.id);
  if(i<0)return;
  const move=e.target.closest('button[data-move]');
  if(move){
    const j=i+Number(move.dataset.move);if(j<0||j>=state.project.cues.length)return;
    [state.project.cues[i],state.project.cues[j]]=[state.project.cues[j],state.project.cues[i]];
    scheduleSave();renderRows();notify(`Cue moved to position ${j+1}.`);return;
  }
  state.selectedCueId=tr.dataset.id;state.selectedPoint=0;renderRows();renderInspector();
});
$('inspectorContent').addEventListener('change',async e=>{
  const c=currentCue();if(!c)return;
  if(e.target.id==='replaceCueAudio'){
    const file=e.target.files?.[0];if(!file)return;
    try {await saveNow();const form=new FormData();form.append('file',file,file.name);
      const r=await api(`/projects/${state.project.id}/cues/${c.id}/replace-media`,{method:'POST',body:form});
      state.project=r.project;renderEverything();notify('Media swapped for fresh playback. Already scheduled audio remains unchanged.');
    }catch(err){report(err);}return;
  }
  const key=e.target.dataset.cue;if(!key)return;
  if(key.startsWith('point_')){
    const point=c.modulation[state.selectedPoint];if(!point)return;
    if(key==='point_time')point.time_s=Math.max(0,num(e.target.value));
    if(key==='point_offset')point.offset_deg=Math.max(-2160,Math.min(2160,num(e.target.value)));
    c.modulation.sort((a,b)=>a.time_s-b.time_s);
    state.selectedPoint=c.modulation.indexOf(point);
  } else if(key.startsWith('adsr_')) {
    const field=key.slice(5), val=num(e.target.value);
    c.direction_adsr[field]=field.endsWith('_s')?Math.max(0,val):Math.max(-2160,Math.min(2160,val));
  } else if(key==='position_deg')c[key]=Math.max(0,Math.min(359.99,num(e.target.value)));
  else if(key==='title')c.title=e.target.value.trim()||'Untitled cue';
  else if(e.target.type==='number')c[key]=Math.max(key==='gain_db'?-90:0,num(e.target.value));
  else c[key]=e.target.value;
  scheduleSave();renderRows();renderInspector();
});
$('inspectorContent').addEventListener('pointerdown',e=>{
  const dial=e.target.closest('#dialSvg');
  if(dial){state.draggingDial=true;$('spatialDial').setPointerCapture(e.pointerId);dialSet(e);return;}
  const svg=e.target.closest('#envelopeSvg');
  if(!svg)return;
  const c=currentCue(),p=envelopePosition(e);if(!c||!p||c.direction_mode!=='keyframes')return;
  const hit=e.target.closest('[data-point]');
  if(hit){state.selectedPoint=Number(hit.dataset.point);}
  else {c.modulation.push({time_s:p.time,offset_deg:p.offset});c.modulation.sort((a,b)=>a.time_s-b.time_s);state.selectedPoint=c.modulation.findIndex(x=>x.time_s===p.time&&x.offset_deg===p.offset);scheduleSave();}
  state.draggingPoint=state.selectedPoint;
  $('envelopeHost').setPointerCapture(e.pointerId);renderEnvelope();pointEdits();
});
$('inspectorContent').addEventListener('pointermove',e=>{
  if(state.draggingDial){dialSet(e);return;}
  if(state.draggingPoint<0)return;
  const c=currentCue(),p=envelopePosition(e);if(!c||!p||c.direction_mode!=='keyframes')return;
  const ref=c.modulation[state.draggingPoint];if(!ref)return;
  ref.time_s=p.time;ref.offset_deg=p.offset;
  renderEnvelope();pointEdits();
});
function endDrag(){
  if(state.draggingDial){state.draggingDial=false;scheduleSave();}
  if(state.draggingPoint>=0){
    const c=currentCue(),ref=c?.modulation[state.draggingPoint];
    if(c&&ref){c.modulation.sort((a,b)=>a.time_s-b.time_s);state.selectedPoint=c.modulation.indexOf(ref);}
    state.draggingPoint=-1;renderEnvelope();pointEdits();scheduleSave();
  }
}
$('inspectorContent').addEventListener('pointerup',endDrag);
$('inspectorContent').addEventListener('pointercancel',endDrag);
$('inspectorContent').addEventListener('click',e=>{
  const c=currentCue();if(!c)return;
  if(e.target.closest('#addPoint')){
    const point={time_s:Math.max(0,c.duration_s*0.5),offset_deg:90};
    c.modulation.push(point);c.modulation.sort((a,b)=>a.time_s-b.time_s);
    state.selectedPoint=c.modulation.indexOf(point);renderEnvelope();pointEdits();scheduleSave();
  }
  if(e.target.closest('#deleteCue')){
    const idx=state.project.cues.findIndex(x=>x.id===c.id);
    if(idx>=0 && confirm(`Delete cue ${c.title}? The original audio file stays in the project media folder.`)){
      state.project.cues.splice(idx,1);
      state.selectedCueId=state.project.cues[Math.min(idx,state.project.cues.length-1)]?.id ?? null;
      state.selectedPoint=0;
      scheduleSave();renderEverything();notify('Cue removed from sequence; copied media retained.');
    }
  }
  if(e.target.closest('#deletePoint')){
    if(c.modulation.length<=1){notify('Keep at least one modulation point.');return;}
    c.modulation.splice(state.selectedPoint,1);state.selectedPoint=Math.max(0,state.selectedPoint-1);
    renderEnvelope();pointEdits();scheduleSave();
  }
});
document.addEventListener('keydown',e=>{
  if(e.repeat || e.metaKey || e.ctrlKey || e.altKey && e.code!=='ArrowDown')return;
  const tag=e.target.tagName;
  if(['INPUT','TEXTAREA','SELECT'].includes(tag)||e.target.isContentEditable||$('stageDialog').open)return;
  if(e.code==='Space'){e.preventDefault();$('goButton').click();}
  else if(e.key.toLowerCase()==='c' && !e.shiftKey){e.preventDefault();$('cutGoButton').click();}
  else if(e.key.toLowerCase()==='s' && !e.shiftKey){e.preventDefault();$('stopButton').click();}
  else if(e.altKey && e.key==='ArrowDown'){e.preventDefault();$('skipButton').click();}
  else if(e.shiftKey && e.key==='Escape'){e.preventDefault();$('panicButton').click();}
});
function speakerXY(s) {const a=s.angle_deg*Math.PI/180;return {x_m:s.distance_m*Math.sin(a),y_m:s.distance_m*Math.cos(a)};}
$('settingsToggle').addEventListener('click',()=>{
  if(!state.project)return;
  state.editSpeakers=structuredClone(state.project.speakers).map(s=>({...s,...speakerXY(s)}));
  $('speakerFields').innerHTML='<div class="speaker-grid"><small>Speaker</small><small>X (m) → right</small><small>Y (m) ↑ top</small><small>Output CH</small><small>Trim (dB)</small></div>'+
    state.editSpeakers.map((s,i)=>`<div class="speaker-grid"><input data-speaker="${i}" data-key="name" type="text" value="${h(s.name)}"/><input data-speaker="${i}" data-key="x_m" type="number" step="0.01" value="${fmt(s.x_m)}"/><input data-speaker="${i}" data-key="y_m" type="number" step="0.01" value="${fmt(s.y_m)}"/><input data-speaker="${i}" data-key="output_channel" type="number" min="1" max="4" step="1" value="${s.output_channel}"/><input data-speaker="${i}" data-key="trim_db" type="number" min="-30" max="12" step="0.1" value="${fmt(s.trim_db,1)}"/></div>`).join('');
  $('calibrationHints').textContent='4 speaker positions → bearing and distance automatically calculated. Click Preview calibration to see theoretical hints.';
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
});
function stagedSpeakerPayload() {return state.editSpeakers.map(({x_m,y_m,...s})=>s);}
$('previewSettings').addEventListener('click',async()=>{
  if(!state.project)return;
  try {const candidate={...state.project,speakers:stagedSpeakerPayload()};
    const r=await post('/calibration/preview',candidate);
    $('calibrationHints').textContent=r.speaker_hints.map(s=>`CH ${s.channel} ${s.name}: ${fmt(s.angle_deg)}° / ${fmt(s.distance_m,2)} m · face ${fmt(s.pointing_at_center_deg)}° · suggested extra delay ${fmt(s.suggested_extra_delay_ms)} ms / relative gain ${fmt(s.suggested_relative_gain_db)} dB`).join('\n')+'\nNo time delay is automatically applied. Use low-volume channel tests to verify.';
  }catch(e){$('calibrationHints').textContent=String(e.message);report(e);}
});
function closeSettings(){$('stageDialog').close();}
$('closeSettings').addEventListener('click',closeSettings);
$('cancelSettings').addEventListener('click',closeSettings);
$('saveSettings').addEventListener('click',async()=>{
  const old=state.project.speakers;
  state.project.speakers=stagedSpeakerPayload();
  try {await saveNow();if($('saveIndicator').textContent==='Save failed')throw new Error('Invalid speaker layout. Check channels and angular coverage.');closeSettings();renderDial();notify('Speaker geometry saved. Test all four channels before rehearsal.');}
  catch(e){state.project.speakers=old;report(e);}
});
async function boot(){
  try {await loadProjectList();await switchProject(state.projects[0].id);await loadDevices();setInterval(poll,450);notify('Ready for design. Connect the output interface when prepared.');}
  catch(e){report(e);}
}
boot();
