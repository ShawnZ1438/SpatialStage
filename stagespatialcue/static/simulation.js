'use strict';
// No alternate cue mixer: preview consumes the Python mixer's captured output.
// Monitor changes never modify production routing or the captured PCM.
$('simConnect').onclick = async () => { if (await action('/simulation/connect')) rememberOutput({kind:'simulation'}); };
$('simRecord').onclick = () => action('/simulation/capture', {recording:true});
$('simStopRecord').onclick = () => action('/simulation/capture', {recording:false});
$('simListen').onclick = async () => {
  try {
    const devices=await api('/devices');
    const select=$('simDevice');
    if(!select.options.length) {
      select.innerHTML=devices.outputs.filter(d=>d.channels>=2).map(d=>`<option value="${d.index}">${h(d.name)}</option>`).join('');
      notify(t('simChooseDevice')); return;
    }
    document.querySelectorAll('.simGain').forEach(e=>e.value=1);
    document.querySelectorAll('.simMute,.simSolo').forEach(e=>e.checked=false);
    const mode=$('simMode').value;
    if(await action('/simulation/monitor',{device_index:Number(select.value),mode})){
      rememberOutput({kind:'monitor',name:select.selectedOptions[0]?.textContent,mode});
      sendPose();
      notify(t(mode==='virtual'?'simVirtualConnected':'simSumConnected'));
    }
  } catch(e) { report(e); }
};
$('simStopListen').onclick=async()=>{ if(await action('/audio/disconnect')) rememberOutput(null); };
function simPose() {
  return {x:Math.max(-6,Math.min(6,num($('simX').value))), y:Math.max(-6,Math.min(6,num($('simY').value))), a:num($('simHead').value)*Math.PI/180};
}
// The virtual monitor renders the speakers as heard from this listener pose.
let poseTimer;
function sendPose() {
  const p=simPose();
  post('/simulation/monitor-pose',{x_m:p.x,y_m:p.y,head_deg:p.a*180/Math.PI}).catch(report);
}
for(const id of ['simX','simY','simHead'])$(id).addEventListener('input',()=>{clearTimeout(poseTimer);poseTimer=setTimeout(sendPose,120);});
function renderSimChannels() {
  const old=[...document.querySelectorAll('#simChannels > div')].map(row=>[row.querySelector('.simGain')?.value??1,row.querySelector('.simMute')?.checked,row.querySelector('.simSolo')?.checked]);
  $('simChannels').innerHTML=[1,2,3,4].map((ch,i)=>`<div><strong>CH${ch}</strong><input class="simGain" type="range" min="0" max="1" step="0.01" value="${old[i]?.[0]??1}" aria-label="${h(t('simGain',{ch}))}"><label><input class="simMute" type="checkbox" ${old[i]?.[1]?'checked':''}>${h(t('simMute'))}</label><label><input class="simSolo" type="checkbox" ${old[i]?.[2]?'checked':''}>${h(t('simSolo'))}</label></div>`).join('');
}
renderSimChannels();
I18N.onChange(renderSimChannels);
$('simChannels').onchange=()=>{
  const gains=[...document.querySelectorAll('.simGain')], mutes=[...document.querySelectorAll('.simMute')], solos=[...document.querySelectorAll('.simSolo')];
  const anySolo=solos.some(e=>e.checked);
  action('/simulation/monitor-gains',{gains:gains.map((g,i)=>mutes[i].checked || (anySolo&&!solos[i].checked)?0:Number(g.value))});
};
function drawSimulation() {
  const project=state.project; if(!project)return;
  const sim=state.status?.simulation;
  $('simChannels').querySelectorAll('input').forEach(e=>e.disabled=!sim?.stereo_monitor);
  $('simStatus').textContent=sim ? [
    t(sim.stereo_monitor?(sim.monitor_mode==='virtual'?'simStatusVirtual':'simStatusSum'):'simStatusSilent'),
    t('simOverload',{n:sim.monitor_peak_over_count||0}),
    t(sim.recording?'simRecording':'simNotRecording'),
    `${sim.captured_seconds.toFixed(2)} / 60 s`,
    t(sim.stereo_monitor?'simNotVerification':'simNoSoundcard')].join(' • ') : t('simDisconnected');
  const c=$('simCanvas'), g=c.getContext('2d'), p=simPose();
  const extent=Math.max(4,...project.speakers.map(s=>s.distance_m+0.8)), scale=150/extent;
  const xy=(x,y)=>[210+x*scale,180-y*scale];
  g.clearRect(0,0,c.width,c.height); g.font='12px sans-serif';
  const pts=project.speakers.map(s=>{const a=s.angle_deg*Math.PI/180;return [s.distance_m*Math.sin(a),s.distance_m*Math.cos(a)];});
  const w=Math.max(...pts.map(q=>Math.abs(q[0]))), d=Math.max(...pts.map(q=>Math.abs(q[1])));
  g.strokeStyle='#71828e';g.setLineDash([5,5]);g.strokeRect(...xy(-w,d),2*w*scale,2*d*scale);g.setLineDash([]);
  g.fillStyle='#c5d1dc';g.fillText(t('mapFront'),150,18);g.fillText(t('simFootprint',{w:fmt(2*w,2),d:fmt(2*d,2)}),125,348);
  for(const s of project.speakers) {
    const a=s.angle_deg*Math.PI/180,[x,y]=xy(s.distance_m*Math.sin(a),s.distance_m*Math.cos(a));
    g.strokeStyle='#375e68';g.beginPath();g.moveTo(x,y);g.lineTo(210,180);g.stroke();
    const level=state.status?.mixer?.meters?.[s.output_channel-1]||0;
    g.fillStyle=level>0.001?'#46e3bb':'#8695a5';g.beginPath();g.arc(x,y,7+level*8,0,Math.PI*2);g.fill();
    g.fillText(`CH${s.output_channel}`,x+10,y);
  }
  for(const v of state.status?.mixer?.voices||[]) {
    if(v.state!=='playing')continue;
    const a=v.position_deg*Math.PI/180;
    g.strokeStyle='#eabf5a';g.beginPath();g.moveTo(210,180);g.lineTo(...xy(2*Math.sin(a),2*Math.cos(a)));g.stroke();
  }
  const [x,y]=xy(p.x,p.y);g.fillStyle='#64aaff';g.beginPath();g.arc(x,y,7,0,Math.PI*2);g.fill();
  g.strokeStyle='#64aaff';g.beginPath();g.moveTo(x,y);g.lineTo(x+25*Math.sin(p.a),y-25*Math.cos(p.a));g.stroke();
}
setInterval(drawSimulation,100);
