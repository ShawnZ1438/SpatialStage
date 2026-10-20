from pathlib import Path
p=Path(__file__).resolve().parents[1]/'stagespatialcue/static/app.js'
s=p.read_text()

def sub(old,new,expected=1):
    global s
    ct=s.count(old)
    if ct != expected:
        raise RuntimeError(f'Expected {expected}, got {ct}: {old[:110]}')
    s=s.replace(old,new)

sub('/* StageSpatialCue — local-only show control v0.1; no frontend audio processing. */', '/* SpatialStage v0.2 — localhost control; multichannel output rendered in Python. */')
sub("state.inputChoice=state.project.preferred_input_device == null ? '' : String(state.project.preferred_input_device);", "renderGlobalEnvelope();")
sub("""  $('inputSelect').innerHTML='<option value="">None / not routed</option>' + state.devices.inputs.map(d=>`<option value="${d.index}">${h(d.name)} (${d.channels} in)</option>`).join('');
  $('inputSelect').value=state.inputChoice;
""", "")
sub("$('inputSelect').addEventListener('change',e=>{if(!state.project)return;state.inputChoice=e.target.value;state.project.preferred_input_device=e.target.value===''?null:Number(e.target.value);scheduleSave();notify('Input preference saved; live microphone monitoring is not enabled.');});", "")
sub("""  $('goButton').disabled=!next || !connected || mute;""", """  $('goButton').disabled=!next || !connected || mute;
  $('cutGoButton').disabled=!next || !connected || mute;""")
sub("""function renderEverything() {
  renderTransport(); renderRows(); renderInspector(); renderMaster();
}""", """function renderEverything() {
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
}""")
sub("""    <div class="field-row" style="margin-top:11px">
      ${inputField('Replace crossfade (s)','transition_s',fmt(c.transition_s),{min:0,max:60})}
      ${inputField('Pre-wait after GO (s)','pre_wait_s',fmt(c.pre_wait_s),{min:0})}
    </div>""", """    <div class="field-row" style="margin-top:11px">
      ${selectField('Replace transition','replace_style',c.replace_style||'crossfade',[['crossfade','Crossfade'],['cut','De-click cut (5 ms)']])}
      ${inputField('Transition (s)','transition_s',fmt(c.transition_s),{min:0,max:60})}
    </div>
    <div class="field-row" style="margin-top:11px">
      ${inputField('Pre-wait before audio (s)','pre_wait_s',fmt(c.pre_wait_s),{min:0})}
      <div class="extra-hint">CUT GO overrides replacement style and pre-wait. Fade GO respects Cue start mode.</div>
    </div>""")
sub("""    <div class="section-label">DIRECTION MODULATION <button id="addPoint" class="secondary">＋ KEYFRAME</button></div>
    <div id="envelopeHost" class="envelope"></div>
    <div class="envelope-help">X = elapsed seconds. Y = direction offset (°). Drag a dot or click anywhere to add a keyframe. 360° = one complete clockwise revolution.</div>
    <div class="point-actions">
      ${inputField('Point time (s)','point_time',fmt(c.modulation[state.selectedPoint]?.time_s??0))}
      ${inputField('Offset (°)','point_offset',fmt(c.modulation[state.selectedPoint]?.offset_deg??0))}
      <button id="deletePoint" class="danger" title="Delete selected keyframe">−</button>
    </div>
    <div class="extra-hint">Audio is downmixed to mono before spatialization. Changes to a playing cue take effect next time it runs; global rotation is live.</div>
    <button id="deleteCue" class="danger" style="margin-top:17px;width:100%">Delete selected cue</button>""", """    <div class="section-label">ANGULAR DIRECTION ENVELOPE</div>
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
    <button id="deleteCue" class="danger" style="margin-top:17px;width:100%">Delete selected cue</button>""")
sub("""  const [px,py]=xyForDeg(c.position_deg,79,cx,cy);""", """  const [px,py]=xyForDeg(c.position_deg,79,cx,cy);
  const active=state.status?.mixer?.voices?.find(v=>v.cue_id===c.id&&v.state==='playing');
  const previewBearing=(c.position_deg + state.project.global_rotation_deg + currentShowOffset() +
    directionOffsetAt(c,active?.elapsed_s||0)+36000)%360;
  const [gx,gy]=xyForDeg(previewBearing,72,cx,cy);""")
sub("""    <line x1="148" y1="125" x2="${px}" y2="${py}" stroke="#52dccd" stroke-width="3.5" stroke-linecap="round"/><circle cx="${px}" cy="${py}" r="8" fill="#52dccd" stroke="#c3fff2" stroke-width="2"/>""", """    <line x1="148" y1="125" x2="${gx}" y2="${gy}" stroke="#f0bd6c" stroke-width="2" stroke-dasharray="5 4"/><circle cx="${gx}" cy="${gy}" r="5" fill="#f0bd6c"/>
    <line x1="148" y1="125" x2="${px}" y2="${py}" stroke="#52dccd" stroke-width="3.5" stroke-linecap="round"/><circle cx="${px}" cy="${py}" r="8" fill="#52dccd" stroke="#c3fff2" stroke-width="2"/>""")
sub("""  const points=c.modulation.map(p=>[toX(p.time_s),toY(p.offset_deg)]);""", """  const points = c.direction_mode==='adsr'
    ? Array.from({length:101},(_,i)=>{const t=i*duration/100;return [toX(t),toY(directionOffsetAt(c,t))];})
    : c.modulation.map(p=>[toX(p.time_s),toY(p.offset_deg)]);""")
sub("""    ${points.map(([x,y],i)=>`<circle data-point="${i}" cx="${x}" cy="${y}" r="${i===state.selectedPoint?6:4.5}" fill="${i===state.selectedPoint?'#fff4c5':'#4ed2c4'}" stroke="#3ea89c" stroke-width="1.3"/>`).join('')}""", """    ${c.direction_mode==='keyframes'?points.map(([x,y],i)=>`<circle data-point="${i}" cx="${x}" cy="${y}" r="${i===state.selectedPoint?6:4.5}" fill="${i===state.selectedPoint?'#fff4c5':'#4ed2c4'}" stroke="#3ea89c" stroke-width="1.3"/>`).join(''):''}""")
sub("""    state.status=await api('/audio/status');
    renderTransport(); renderRows(); renderMaster();""", """    state.status=await api('/audio/status');
    renderTransport(); renderRows(); renderMaster();
    if(!state.draggingDial && state.draggingPoint<0)renderDial();""")
sub("""$('globalRotation').addEventListener('change',e=>{ """, """$('globalRotation').addEventListener('change',e=>{ """, 0) if False else None
sub("""$('globalRotation').addEventListener('change',e=>{
  if(!state.project)return;
  state.project.global_rotation_deg=Math.max(-3600,Math.min(3600,num(e.target.value)));
  scheduleSave();renderDial();
});""", """$('globalRotation').addEventListener('input',e=>{
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
});""")
sub("""$('goButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id},'GO — next cue triggered.');});""", """$('goButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id,cut:false},'FADE GO — normal cue rules.');});
$('cutGoButton').addEventListener('click',()=>{if(state.project)action('/audio/go',{project_id:state.project.id,cut:true},'CUT GO — immediately replace, 5 ms de-click.');});""")
sub("""$('inspectorContent').addEventListener('change',e=>{
  const key=e.target.dataset.cue,c=currentCue();if(!key||!c)return;""", """$('inspectorContent').addEventListener('change',async e=>{
  const c=currentCue();if(!c)return;
  if(e.target.id==='replaceCueAudio'){
    const file=e.target.files?.[0];if(!file)return;
    try {await saveNow();const form=new FormData();form.append('file',file,file.name);
      const r=await api(`/projects/${state.project.id}/cues/${c.id}/replace-media`,{method:'POST',body:form});
      state.project=r.project;renderEverything();notify('Media swapped for fresh playback. Already scheduled audio remains unchanged.');
    }catch(err){report(err);}return;
  }
  const key=e.target.dataset.cue;if(!key)return;""")
sub("""  } else if(key==='position_deg')c[key]=Math.max(0,Math.min(359.99,num(e.target.value)));""", """  } else if(key.startsWith('adsr_')) {
    const field=key.slice(5), val=num(e.target.value);
    c.direction_adsr[field]=field.endsWith('_s')?Math.max(0,val):Math.max(-2160,Math.min(2160,val));
  } else if(key==='position_deg')c[key]=Math.max(0,Math.min(359.99,num(e.target.value)));""")
sub("""  if(e.repeat || e.metaKey || e.ctrlKey)return;""", """  if(e.repeat || e.metaKey || e.ctrlKey || e.altKey && e.code!=='ArrowDown')return;""")
sub("""  else if(e.key.toLowerCase()==='s' && !e.shiftKey){e.preventDefault();$('stopButton').click();}""", """  else if(e.key.toLowerCase()==='c' && !e.shiftKey){e.preventDefault();$('cutGoButton').click();}
  else if(e.key.toLowerCase()==='s' && !e.shiftKey){e.preventDefault();$('stopButton').click();}""")
# Settings mode entirely replace block between settingsToggle and closeSettings.
start=s.index("$('settingsToggle').addEventListener('click',()=>{")
end=s.index("function closeSettings()",start)
s=s[:start]+'''function speakerXY(s) {const a=s.angle_deg*Math.PI/180;return {x_m:s.distance_m*Math.sin(a),y_m:s.distance_m*Math.cos(a)};}
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
    $('calibrationHints').textContent=r.speaker_hints.map(s=>`CH ${s.channel} ${s.name}: ${fmt(s.angle_deg)}° / ${fmt(s.distance_m,2)} m · face ${fmt(s.pointing_at_center_deg)}° · suggested extra delay ${fmt(s.suggested_extra_delay_ms)} ms / relative gain ${fmt(s.suggested_relative_gain_db)} dB`).join('\\n')+'\\nNo time delay is automatically applied. Use low-volume channel tests to verify.';
  }catch(e){$('calibrationHints').textContent=String(e.message);report(e);}
});
''' +s[end:]
sub("""  const old=state.project.speakers;
  state.project.speakers=state.editSpeakers;""", """  const old=state.project.speakers;
  state.project.speakers=stagedSpeakerPayload();""")
sub("""const c=currentCue(),p=envelopePosition(e);if(!c||!p)return;""", """const c=currentCue(),p=envelopePosition(e);if(!c||!p||c.direction_mode!=='keyframes')return;""", 2)
# Make sure configuration survives refreshing and handlers don't dereference missing input
p.write_text(s)
