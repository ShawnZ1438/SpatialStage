'use strict';
// No alternate cue mixer: preview consumes the Python mixer's captured output.
// Monitor changes never modify production routing or the captured PCM.
$('simConnect').onclick = () => action('/simulation/connect');
$('simRecord').onclick = () => action('/simulation/capture', {recording:true});
$('simStopRecord').onclick = () => action('/simulation/capture', {recording:false});
$('simListen').onclick = async () => {
  try {
    const devices=await api('/devices');
    const select=$('simDevice');
    if(!select.options.length) {
      select.innerHTML=devices.outputs.filter(d=>d.channels>=2).map(d=>`<option value="${d.index}">${h(d.name)}</option>`).join('');
      notify('Choose a stereo monitor device, then click Connect stereo monitor again.'); return;
    }
    document.querySelectorAll('.simGain').forEach(e=>e.value=1);
    document.querySelectorAll('.simMute,.simSolo').forEach(e=>e.checked=false);
    const mode=$('simMode').value;
    if(await action('/simulation/monitor',{device_index:Number(select.value),mode})){
      sendPose();
      notify(`${mode==='virtual'?'Virtual 4-speaker':'Mono sum'} headphone monitor connected, MAIN MUTE remains on. Unmute deliberately, then GO.`);
    }
  } catch(e) { report(e); }
};
$('simStopListen').onclick=()=>action('/audio/disconnect');
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
$('simChannels').innerHTML=[1,2,3,4].map(ch=>`<div><strong>CH${ch}</strong><input class="simGain" type="range" min="0" max="1" step="0.01" value="1" aria-label="Monitor CH${ch} gain"><label><input class="simMute" type="checkbox">Mute</label><label><input class="simSolo" type="checkbox">Solo</label></div>`).join('');
$('simChannels').onchange=()=>{
  const gains=[...document.querySelectorAll('.simGain')], mutes=[...document.querySelectorAll('.simMute')], solos=[...document.querySelectorAll('.simSolo')];
  const anySolo=solos.some(e=>e.checked);
  action('/simulation/monitor-gains',{gains:gains.map((g,i)=>mutes[i].checked || (anySolo&&!solos[i].checked)?0:Number(g.value))});
};
function drawSimulation() {
  const project=state.project; if(!project)return;
  const sim=state.status?.simulation;
  $('simChannels').querySelectorAll('input').forEach(e=>e.disabled=!sim?.stereo_monitor);
  $('simStatus').textContent=sim ? `${sim.stereo_monitor?(sim.monitor_mode==='virtual'?'VIRTUAL 4-SPEAKER HEADPHONES (about -20 dB)':'MONO SUM MONITOR (-26 dB per channel)'):"SILENT ENGINE"} • monitor overload blocks: ${sim.monitor_peak_over_count||0} • ${sim.recording?'RECORDING':'capture stopped'} • ${sim.captured_seconds.toFixed(2)} / 60 s • ${sim.stereo_monitor?(sim.monitor_mode==='virtual'?'approximate binaural preview; NOT four-output verification':'stereo fold-down; NOT four-output verification'):"no soundcard opened"}` : 'Simulation disconnected; hardware mode remains available.';
  const c=$('simCanvas'), g=c.getContext('2d'), p=simPose();
  const extent=Math.max(4,...project.speakers.map(s=>s.distance_m+0.8)), scale=150/extent;
  const xy=(x,y)=>[210+x*scale,180-y*scale];
  g.clearRect(0,0,c.width,c.height); g.font='12px sans-serif';
  g.strokeStyle='#71828e';g.setLineDash([5,5]);g.strokeRect(...xy(-3,3),6*scale,6*scale);g.setLineDash([]);
  g.fillStyle='#c5d1dc';g.fillText('0° / FRONT / +Y',155,18);g.fillText('6 m × 6 m stage footprint',125,348);
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
