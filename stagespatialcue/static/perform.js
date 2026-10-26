/* SpatialStage Performance mode: place/draw the target cue on the stage map before
   it fires; Store / Recall / Reset its spatial preset; lock once the show runs.
   Uses app.js globals ($, h, fmt, num, state, scheduleSave, notify, action...). */
'use strict';
const perf = {follow:true, lastNext:undefined, tool:'position', selected:0, dragging:-1,
  locked:false, previewT:null, targetSig:'', statusAt:0, frame:0};
const PERF_MODE_KEY = 'spatialstage.mode', PERF_LOCK_KEY = 'spatialstage.performLock';

function perfStorage(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { /* private window / blocked storage: per-session only */ }
  return null;
}
const performing = () => document.body.classList.contains('performing');
const perfCueIndex = id => state.project?.cues.findIndex(c => c.id === id) ?? -1;
const perfCueNumber = id => String(perfCueIndex(id) + 1).padStart(3, '0');

function setPerformMode(on) {
  document.body.classList.toggle('performing', on);
  $('modeToggle').textContent = on ? '✎ Edit mode' : '▶ Performance mode';
  $('modeToggle').setAttribute('aria-pressed', String(on));
  perfStorage(PERF_MODE_KEY, on ? 'perform' : 'edit');
  perf.targetSig = '';
  if (on) { perf.follow = true; perf.lastNext = undefined; renderPerform(); }
  else if (state.project) { renderRows(); renderInspector(); }
}

function followNext() {
  const next = state.status?.next_cue_id ?? null;
  if (perf.follow && next !== perf.lastNext && next && perfCueIndex(next) >= 0) {
    state.selectedCueId = next;
    perf.selected = 0;
    perf.previewT = null;
  }
  perf.lastNext = next;
}

function perfTarget() { return currentCue(); }

// Path points are kept sorted by time; keep the selected object selected.
function perfSortPath(cue, keep) {
  cue.path.sort((a, b) => a.time_s - b.time_s);
  perf.selected = Math.max(0, cue.path.indexOf(keep));
}

function perfEnsurePath(cue) {
  if (cue.direction_mode === 'path' && cue.path?.length) return;
  cue.direction_mode = 'path';
  cue.path = [StageMap.bearingPoint(cue.position_deg, state.project.speakers)];
  perf.selected = 0;
}

function perfChanged(message) {
  scheduleSave();
  perf.targetSig = '';
  renderPerform();
  if (message) notify(message);
}

/* ---------- map ---------- */
function perfMapPoint(event) {
  const svg = $('performMap').querySelector('svg');
  const pt = svgLocal(svg, event);
  const g = StageMap.geometry(state.project.speakers);
  const m = g.toMetres(pt.x, pt.y), lim = g.extent;
  return {x: Math.round(Math.max(-lim, Math.min(lim, m.x)) * 100) / 100,
    y: Math.round(Math.max(-lim, Math.min(lim, m.y)) * 100) / 100};
}

function perfSpeakerNotes() {
  const mix = state.status?.mixer;
  return state.project.speakers.map(s => {
    const ch = s.output_channel - 1, notes = [];
    if (s.trim_db) notes.push(`trim ${s.trim_db > 0 ? '+' : ''}${fmt(s.trim_db, 1)} dB`);
    if (mix?.autocal_enabled) notes.push(`AutoCal ${fmt(mix.autocal_gain_db?.[ch], 1)} dB / ${fmt(mix.autocal_delay_ms?.[ch], 2)} ms`);
    return notes.join(' · ');
  });
}

function perfFocusPoint(cue) {
  if (!cue) return null;
  if (cue.direction_mode !== 'path') {
    const p = StageMap.bearingPoint(cue.position_deg, state.project.speakers);
    return {x: p.x_m, y: p.y_m};
  }
  if (perf.previewT != null) return StageMap.pathAt(cue.path, perf.previewT);
  const p = cue.path[perf.selected] || cue.path[0];
  return {x: p.x_m, y: p.y_m};
}

function renderPerformMap() {
  const cue = perfTarget(), host = $('performMap');
  const anglePoint = cue && cue.direction_mode !== 'path' ? perfFocusPoint(cue) : null;
  host.innerHTML = StageMap.svg({
    speakers: state.project.speakers, notes: perfSpeakerNotes(), interactive: !perf.locked,
    path: cue?.direction_mode === 'path' ? cue.path : null, selected: perf.selected,
    anglePoint, gainPoint: perfFocusPoint(cue),
  });
  host.classList.toggle('locked', perf.locked);
  renderPerformLive();
}

// Playing voices and speaker meters, extrapolated between status polls.
function renderPerformLive() {
  const layer = $('performMap').querySelector('.live-layer');
  if (!layer || !state.project) return;
  const g = StageMap.geometry(state.project.speakers), mix = state.status?.mixer;
  const since = (performance.now() - perf.statusAt) / 1000;
  const rotation = state.project.global_rotation_deg + currentShowOffset();
  const parts = [];
  for (const s of state.project.speakers) {
    const level = mix?.meters?.[s.output_channel - 1] || 0, p = StageMap.speakerXY(s);
    if (level > 0.002) parts.push(`<circle cx="${g.px(p.x)}" cy="${g.py(p.y)}" r="${18 + Math.min(1, level * 3) * 16}" class="sm-meter" style="opacity:${0.25 + Math.min(1, level * 3) * 0.6}"/>`);
  }
  for (const v of mix?.voices || []) {
    if (v.state !== 'playing') continue;
    const cue = state.project.cues.find(c => c.id === v.cue_id);
    let p;
    if (cue?.direction_mode === 'path' && cue.path?.length) {
      p = StageMap.rotate(StageMap.pathAt(cue.path, Math.min(v.duration_s, v.elapsed_s + since)), rotation);
      if (cue.path.length > 1) {
        const trail = cue.path.map(q => StageMap.rotate({x: q.x_m, y: q.y_m}, rotation));
        parts.push(`<polyline points="${trail.map(q => `${g.px(q.x)},${g.py(q.y)}`).join(' ')}" class="sm-live-path"/>`);
      }
    } else {
      const b = StageMap.bearingPoint(v.position_deg, state.project.speakers);
      p = {x: b.x_m, y: b.y_m};
    }
    parts.push(`<circle cx="${g.px(p.x)}" cy="${g.py(p.y)}" r="9" class="sm-live"/><text x="${g.px(p.x) + 12}" y="${g.py(p.y) + 4}" class="sm-live-label">${h(perfCueNumber(v.cue_id))} ${h(v.title)}</text>`);
  }
  layer.innerHTML = parts.join('');
}

function perfAnimate() {
  if (performing() && state.project && perf.dragging < 0) renderPerformLive();
  perf.frame = requestAnimationFrame(perfAnimate);
}

/* ---------- side panel ---------- */
function perfPresetText(cue) {
  const stored = cue.spatial_preset?.stored_at ? new Date(cue.spatial_preset.stored_at).toLocaleString() : '';
  return {none: 'No stored preset yet — Store saves this position/path for Recall.',
    stored: `✓ Matches stored preset (${stored}).`,
    changed: `● Changed since stored preset (${stored}). Recall restores it.`}[StageMap.presetState(cue)];
}

function renderPerformTarget(force = false) {
  const host = $('performTarget'), cue = perfTarget();
  const sig = JSON.stringify([cue?.id, cue && StageMap.spatialSnapshot(cue), cue?.spatial_preset, cue?.title,
    cue?.duration_s, perfCueIndex(cue?.id), perf.selected, perf.tool, perf.locked, perf.follow, perf.previewT]);
  const editing = host.contains(document.activeElement) && document.activeElement.tagName === 'INPUT';
  if (!force && (sig === perf.targetSig || editing)) return;
  perf.targetSig = sig;
  if (!cue) { host.innerHTML = '<p class="small-muted">No cue selected. Import audio or select a cue.</p>'; return; }
  const lock = perf.locked ? 'disabled' : '', isPath = cue.direction_mode === 'path';
  const rows = isPath ? cue.path.map((p, i) => `<tr class="${i === perf.selected ? 'selected' : ''}" data-row="${i}">
      <td>${i === 0 ? 'START' : i + 1}</td>
      <td><input type="number" data-pt="${i}" data-k="time_s" min="0" step="0.1" value="${fmt(p.time_s)}" ${lock} aria-label="Point ${i + 1} time (s)"></td>
      <td><input type="number" data-pt="${i}" data-k="x_m" step="0.05" value="${fmt(p.x_m)}" ${lock} aria-label="Point ${i + 1} X (m)"></td>
      <td><input type="number" data-pt="${i}" data-k="y_m" step="0.05" value="${fmt(p.y_m)}" ${lock} aria-label="Point ${i + 1} Y (m)"></td>
      <td><button data-perf="delete" data-pt="${i}" title="Delete point" ${lock || cue.path.length <= 1 ? 'disabled' : ''}>×</button></td></tr>`).join('') : '';
  const duration = Math.max(cue.duration_s || 0, isPath ? cue.path.at(-1).time_s : 0);
  host.innerHTML = `
    <div class="perf-target-head"><span class="eyebrow">${perf.follow ? 'TARGET · FOLLOWING NEXT' : 'TARGET · MANUAL SELECTION'}</span>
      ${perf.follow ? '' : '<button data-perf="follow" class="secondary">↺ Follow NEXT</button>'}</div>
    <h2>${perfCueNumber(cue.id)} · ${h(cue.title)}</h2>
    <div class="small-muted">${cue.duration_s ? fmt(cue.duration_s, 1) + ' s' : 'duration unknown'} · ${h(cue.start_mode.toUpperCase())} · ${isPath ? `stage-map ${cue.path.length > 1 ? `path, ${cue.path.length} points` : 'position'}` : `angle mode ${fmt(cue.position_deg, 1)}°`}</div>
    <div class="perf-tools" role="group" aria-label="Map tool">
      <button data-perf="tool" data-tool="position" class="${perf.tool === 'position' ? 'active' : ''}" ${lock}>◎ Move point</button>
      <button data-perf="tool" data-tool="add" class="${perf.tool === 'add' ? 'active' : ''}" ${lock}>＋ Add path point</button>
    </div>
    <p class="micro">${perf.locked ? 'Map locked for the show. Unlock to edit.' : perf.tool === 'add'
      ? 'Click the map to append a path point after the last one (Shift+click works in either tool). Drag points to move them.'
      : 'Click the map to move the selected point there, or drag any point. Shift+click appends a path point.'}</p>
    ${isPath ? `<table class="path-table"><thead><tr><th>#</th><th>Time s</th><th>X m</th><th>Y m</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
      : '<p class="direction-mode-help">This cue still uses angle mode. Click or drag on the map to convert it to a stage-map position (the current bearing becomes the starting point).</p>'}
    ${isPath && duration > 0 ? `<label class="small-label" for="perfPreview">Preview path time · ${perf.previewT == null ? 'off' : fmt(perf.previewT, 1) + ' s'}</label>
      <input id="perfPreview" type="range" min="0" max="${duration}" step="0.05" value="${perf.previewT ?? 0}">` : ''}
    <div class="perf-presets">
      <button data-perf="store" class="primary" ${lock}>Store</button>
      <button data-perf="recall" class="secondary" ${cue.spatial_preset ? '' : 'disabled'}>Recall</button>
      <button data-perf="reset" class="danger" ${lock}>Reset</button>
    </div>
    <p class="micro perf-preset-state">${perfPresetText(cue)} Reset = one static point at front (0°).</p>
    <label class="check"><input id="perfLock" type="checkbox" ${perf.locked ? 'checked' : ''}> Lock map and presets for the show (GO / STOP / PANIC still work)</label>`;
}

function renderPerformOutputs() {
  const cue = perfTarget(), p = perfFocusPoint(cue), host = $('performOutputs');
  if (!cue || !p) { host.innerHTML = ''; return; }
  const gains = StageMap.pointGains(p.x, p.y, state.project.speakers);
  const mix = state.status?.mixer;
  host.innerHTML = `<div class="section-heading">SPEAKER OUTPUT AT ${perf.previewT != null ? 'PREVIEW TIME' : 'SELECTED POINT'}</div>` +
    [...state.project.speakers].sort((a, b) => a.output_channel - b.output_channel).map(s => {
      const v = gains[s.output_channel - 1], db = v > 1e-4 ? 20 * Math.log10(v) : -Infinity;
      const level = mix?.meters?.[s.output_channel - 1] || 0;
      return `<div class="perf-gain"><b>CH${s.output_channel}</b><span>${h(s.name)}</span>
        <div class="bar"><i style="width:${(v * 100).toFixed(1)}%"></i><em style="width:${Math.min(100, level * 115).toFixed(1)}%"></em></div>
        <small>${Number.isFinite(db) ? fmt(db, 1) + ' dB' : '−∞'}</small></div>`;
    }).join('') +
    `<p class="micro">Pan gain before trims/AutoCal/master (bar); thin line = live output meter. Centre = all four equal; on the dashed speaker edge = that pair only.${state.project.global_rotation_deg ? ` Global rotation ${fmt(state.project.global_rotation_deg, 1)}° is added during playback.` : ''}</p>`;
}

function renderPerformCues() {
  const host = $('performCues'), next = state.status?.next_cue_id, voices = state.status?.mixer?.voices || [];
  const stored = state.project.cues.filter(c => c.spatial_preset).length;
  host.innerHTML = `<div class="section-heading perf-cues-head">CUES <span>${stored}/${state.project.cues.length} stored</span>
      <span><button data-perf="store-all" class="quiet" ${perf.locked ? 'disabled' : ''}>Store all</button>
      <button data-perf="recall-all" class="quiet" ${stored && !perf.locked ? '' : 'disabled'}>Recall all</button></span></div>` +
    `<div class="perf-cue-list">${state.project.cues.map((c, i) => {
      const playing = voices.some(v => v.cue_id === c.id && v.state === 'playing');
      const preset = StageMap.presetState(c);
      const cls = [c.id === next ? 'next' : '', c.id === state.selectedCueId ? 'selected' : '', playing ? 'playing' : ''].join(' ');
      return `<button class="perf-cue ${cls}" data-cue-id="${h(c.id)}"><span class="num">${String(i + 1).padStart(3, '0')}</span>
        <span class="title">${h(c.title)}</span><span class="tag">${c.id === next ? 'NEXT' : playing ? 'LIVE' : ''}</span>
        <span class="kind">${c.direction_mode === 'path' ? (c.path.length > 1 ? `PATH ${c.path.length}` : 'XY') : fmt(c.position_deg, 0) + '°'}</span>
        <span class="preset ${preset}" title="${{none: 'No stored preset', stored: 'Matches stored preset', changed: 'Changed since stored'}[preset]}">${{none: '—', stored: '✓', changed: '●'}[preset]}</span></button>`;
    }).join('')}</div>`;
}

function renderPerform() {
  if (!performing() || !state.project) return;
  followNext();
  perf.statusAt = performance.now();
  if (perf.dragging < 0) renderPerformMap();
  renderPerformTarget();
  renderPerformOutputs();
  renderPerformCues();
}

/* ---------- actions ---------- */
function perfStore(cue) {
  cue.spatial_preset = {...StageMap.spatialSnapshot(cue), stored_at: new Date().toISOString()};
}
function perfRecall(cue) {
  if (!cue.spatial_preset) return false;
  Object.assign(cue, structuredClone(StageMap.spatialSnapshot(cue.spatial_preset)));
  return true;
}

$('performTarget').addEventListener('click', e => {
  const b = e.target.closest('[data-perf]'), cue = perfTarget();
  if (!b || !cue) return;
  const what = b.dataset.perf;
  if (what === 'follow') { perf.follow = true; perf.lastNext = undefined; perf.targetSig = ''; renderPerform(); return; }
  if (what === 'recall') {
    if (perfRecall(cue)) { perf.selected = 0; perf.previewT = null; perfChanged(`Recalled stored position/path for cue ${perfCueNumber(cue.id)}.`); }
    return;
  }
  if (perf.locked) return;
  if (what === 'tool') { perf.tool = b.dataset.tool; perf.targetSig = ''; renderPerformTarget(); }
  else if (what === 'delete' && cue.path.length > 1) {
    cue.path.splice(Number(b.dataset.pt), 1);
    perf.selected = Math.min(perf.selected, cue.path.length - 1);
    perfChanged();
  } else if (what === 'store') { perfStore(cue); perfChanged(`Stored position/path for cue ${perfCueNumber(cue.id)}.`); }
  else if (what === 'reset') {
    Object.assign(cue, {direction_mode: 'path', position_deg: 0, modulation: [{time_s: 0, offset_deg: 0}],
      path: [StageMap.bearingPoint(0, state.project.speakers)]});
    perf.selected = 0; perf.previewT = null;
    perfChanged(`Cue ${perfCueNumber(cue.id)} reset to a static front position. Recall restores the stored preset.`);
  }
});
$('performTarget').addEventListener('click', e => {
  const row = e.target.closest('tr[data-row]');
  if (row && !e.target.closest('input,button')) { perf.selected = Number(row.dataset.row); perf.previewT = null; perf.targetSig = ''; renderPerform(); }
});
$('performTarget').addEventListener('change', e => {
  const cue = perfTarget();
  if (!cue) return;
  if (e.target.id === 'perfLock') {
    perf.locked = e.target.checked;
    perfStorage(PERF_LOCK_KEY, perf.locked ? '1' : '0');
    perf.targetSig = ''; renderPerform();
    notify(perf.locked ? 'Map locked for the show.' : 'Map unlocked — edits change the cue.');
    return;
  }
  const i = Number(e.target.dataset.pt), key = e.target.dataset.k;
  if (perf.locked || !key || !cue.path?.[i]) return;
  const point = cue.path[i];
  point[key] = key === 'time_s' ? Math.min(14400, Math.max(0, num(e.target.value))) : Math.min(100, Math.max(-100, num(e.target.value)));
  perfSortPath(cue, point);
  perfChanged();
});
$('performTarget').addEventListener('input', e => {
  if (e.target.id !== 'perfPreview') return;
  perf.previewT = num(e.target.value);
  const label = $('performTarget').querySelector('label[for="perfPreview"]');
  if (label) label.textContent = `Preview path time · ${fmt(perf.previewT, 1)} s`;
  renderPerformMap(); renderPerformOutputs();
});

$('performCues').addEventListener('click', e => {
  const b = e.target.closest('[data-perf]');
  if (b?.dataset.perf === 'store-all' && !perf.locked) {
    if (!confirm('Store the current position/path of EVERY cue as its preset?')) return;
    state.project.cues.forEach(perfStore);
    perfChanged(`Stored presets for ${state.project.cues.length} cues.`);
    return;
  }
  if (b?.dataset.perf === 'recall-all' && !perf.locked) {
    const count = state.project.cues.filter(c => c.spatial_preset).length;
    if (!confirm(`Recall stored presets for ${count} cues? Unsaved map changes on those cues are replaced.`)) return;
    state.project.cues.forEach(perfRecall);
    perf.selected = 0;
    perfChanged(`Recalled ${count} stored presets.`);
    return;
  }
  const row = e.target.closest('[data-cue-id]');
  if (!row) return;
  state.selectedCueId = row.dataset.cueId;
  perf.follow = row.dataset.cueId === state.status?.next_cue_id;
  perf.selected = 0; perf.previewT = null; perf.targetSig = '';
  renderPerform();
});

$('performMap').addEventListener('pointerdown', e => {
  const cue = perfTarget();
  if (!cue || !e.target.closest('svg')) return;
  if (perf.locked) { notify('Map is locked for the show. Untick Lock to edit.'); return; }
  const hit = e.target.closest('[data-ppoint]'), p = perfMapPoint(e);
  perf.previewT = null;
  if (hit && cue.direction_mode === 'path') {
    perf.selected = Number(hit.dataset.ppoint);
  } else if (cue.direction_mode !== 'path') {
    perfEnsurePath(cue);
    Object.assign(cue.path[0], {x_m: p.x, y_m: p.y});
  } else if (perf.tool === 'add' || e.shiftKey) {
    const last = cue.path.at(-1), step = cue.duration_s > 0 ? Math.max(0.5, cue.duration_s / 8) : 2;
    cue.path.push({time_s: Math.round((last.time_s + step) * 100) / 100, x_m: p.x, y_m: p.y});
    perf.selected = cue.path.length - 1;
  } else {
    Object.assign(cue.path[perf.selected] || cue.path[0], {x_m: p.x, y_m: p.y});
  }
  perf.dragging = perf.selected;
  $('performMap').setPointerCapture(e.pointerId);
  renderPerformMap(); renderPerformOutputs();
});
$('performMap').addEventListener('pointermove', e => {
  const cue = perfTarget();
  if (perf.dragging < 0 || !cue?.path?.[perf.dragging]) return;
  const p = perfMapPoint(e);
  Object.assign(cue.path[perf.dragging], {x_m: p.x, y_m: p.y});
  renderPerformMap(); renderPerformOutputs();
});
function perfEndDrag() {
  if (perf.dragging < 0) return;
  perf.dragging = -1;
  perfChanged();
}
$('performMap').addEventListener('pointerup', perfEndDrag);
$('performMap').addEventListener('pointercancel', perfEndDrag);
$('modeToggle').addEventListener('click', () => setPerformMode(!performing()));

perf.locked = perfStorage(PERF_LOCK_KEY) === '1';
setPerformMode((new URLSearchParams(location.search).get('mode') || perfStorage(PERF_MODE_KEY)) === 'perform');
perf.frame = requestAnimationFrame(perfAnimate);
globalThis.SpatialPerform = {render: renderPerform, open: () => setPerformMode(true)};
