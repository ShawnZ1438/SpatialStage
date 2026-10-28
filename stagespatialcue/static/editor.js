/* SpatialStage editor: audio library + sound design, cue list, stage map with every
   layer of the selected cue, cue/layer inspector, drag & drop, Store/Recall/Reset,
   and the locked Run view. Uses app.js globals ($, h, fmt, num, t, state, ...). */
'use strict';
const ed = {tool:'position', selectedPoint:0, dragging:-1, previewT:null, follow:true, lastNext:undefined,
  sig:{}, statusAt:0, search:''};
const SIM_KEY = 'spatialstage.simPanel';
const LAYER_COLORS = ['#52dccd', '#f0bd6c', '#b9a3fa', '#71baf6', '#f28fad', '#9be37a', '#e6d36a', '#7fd6f5'];
const DEFAULT_ADSR = {attack_s:.3, peak_offset_deg:90, decay_s:.5, sustain_offset_deg:90, release_s:.3, release_offset_deg:0};
const MEDIA_TYPE = 'application/x-spatialstage-media', CUE_TYPE = 'application/x-spatialstage-cue';

function edStorage(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { /* private window / blocked storage: per-session only */ }
  return null;
}
const runMode = () => document.body.classList.contains('performing');
const newId = () => (globalThis.crypto?.randomUUID?.() || Math.random().toString(16).slice(2) + Date.now().toString(16)).replace(/-/g, '').slice(0, 12);
const cueIndex = id => state.project?.cues.findIndex(c => c.id === id) ?? -1;
const mediaUse = id => state.project.cues.filter(c => c.layers.some(l => l.media_id === id));
const layerIndex = (cue, layer) => cue.layers.indexOf(layer);
const layerColor = (cue, layer) => LAYER_COLORS[Math.max(0, layerIndex(cue, layer)) % LAYER_COLORS.length];
const layerName = layer => mediaById(layer.media_id)?.name || t('missingAudio');
function currentLayer() {
  const cue = currentCue();
  if (!cue?.layers.length) return null;
  let layer = cue.layers.find(l => l.id === state.selectedLayerId);
  if (!layer) { layer = cue.layers[0]; state.selectedLayerId = layer.id; ed.selectedPoint = 0; }
  return layer;
}
function selectCue(id, {follow} = {}) {
  if (state.selectedCueId !== id) { state.selectedLayerId = null; ed.selectedPoint = 0; ed.previewT = null; }
  state.selectedCueId = id;
  ed.follow = follow ?? (id === state.status?.next_cue_id);
}
// A focused field is not re-rendered, so show the clamped/normalised number right away.
function reflect(el, value, digits = 2) { if (el.type === 'number') el.value = fmt(value, digits); }
function selectLayer(id) { state.selectedLayerId = id; ed.selectedPoint = 0; ed.previewT = null; }
function changed(message) {
  scheduleSave();
  // Lists rebuild from their own signatures; the panels below may hold stale focus guards.
  ed.sig.inspector = ed.sig.designer = ed.sig.map = undefined;
  render();
  if (message) notify(message);
}
// A list rebuilt between mousedown and mouseup swallows the click (e.g. a field's
// change event fires on blur when you click a row). Hold rebuilds until release.
let pointerHeld = false;
document.addEventListener('pointerdown', () => { pointerHeld = true; }, true);
for (const type of ['pointerup', 'pointercancel']) {
  document.addEventListener(type, () => { pointerHeld = false; setTimeout(() => render(), 0); }, true);
}

/* ---------- creating cues and layers ---------- */
function newLayer(mediaId, point) {
  return {id:newId(), media_id:mediaId, gain_db:0, delay_s:0, muted:false,
    position_deg:0, direction_mode:point ? 'path' : 'keyframes', modulation:[{time_s:0, offset_deg:0}],
    direction_adsr:{...DEFAULT_ADSR}, path:point ? [{time_s:0, x_m:point.x, y_m:point.y}] : []};
}
function newCue(mediaId, point) {
  const media = mediaById(mediaId);
  const cue = {id:newId(), title:media?.name || t('newCueTitle'), color:'cyan', notes:'',
    layers:media ? [newLayer(mediaId, point)] : [], spatial_preset:null, gain_db:0, transition_s:2.5,
    replace_style:'crossfade', pre_wait_s:0, post_wait_s:0, start_mode:'replace', continue_mode:'manual'};
  const at = cueIndex(state.selectedCueId);
  state.project.cues.splice(at < 0 ? state.project.cues.length : at + 1, 0, cue);
  selectCue(cue.id, {follow:false});
  if (cue.layers[0]) selectLayer(cue.layers[0].id);
  return cue;
}
function addLayer(cue, mediaId, point) {
  if (cue.layers.length >= 32) { notify(t('tooManyLayers'), true); return null; }
  const layer = newLayer(mediaId, point);
  cue.layers.push(layer);
  selectCue(cue.id, {follow:ed.follow && cue.id === state.selectedCueId});
  selectLayer(layer.id);
  return layer;
}
function guardEdit() {
  if (runMode()) { notify(t('runLocked'), true); return false; }
  return true;
}

/* ---------- audio library ---------- */
function renderLibrary(force) {
  const host = $('libraryList'), media = state.project.media, voices = state.status?.mixer?.voices || [];
  const playing = new Set(voices.filter(v => v.state === 'playing').map(v => v.media_id));
  const q = ed.search.trim().toLowerCase();
  const sig = JSON.stringify([I18N.lang, q, state.selectedMediaId, [...playing],
    media.map(m => [m.id, m.name, m.duration_s, m.trim_start_s, m.trim_end_s, m.loop, m.source_channels, m.stereo_mode]),
    state.project.cues.map(c => c.layers.map(l => l.media_id))]);
  if (!force && (ed.sig.library === sig || pointerHeld)) return;
  ed.sig.library = sig;
  $('libraryCount').textContent = t('libraryCount', {n:media.length});
  const shown = media.filter(m => !q || m.name.toLowerCase().includes(q) || m.filename.toLowerCase().includes(q));
  host.innerHTML = shown.map(m => {
    const used = mediaUse(m.id).length;
    return `<div class="lib-item${m.id === state.selectedMediaId ? ' selected' : ''}${playing.has(m.id) ? ' playing' : ''}" draggable="true" data-media-id="${h(m.id)}" title="${h(m.filename)}">
      <span class="lib-name">${h(m.name)}</span>
      <span class="lib-meta">${fmtDuration(playDuration(m))}${m.source_channels === 2 ? ' · ST' : ''}${m.loop ? ' · ⟲' : ''} · ${used ? h(t('usedIn', {n:used})) : h(t('unused'))}</span>
      <button class="lib-play" data-lib="audition" title="${h(t('auditionAudio'))}" aria-label="${h(t('auditionAudio'))}">▷</button></div>`;
  }).join('') || `<p class="micro empty-note">${h(media.length ? t('noSearchMatch') : t('libraryEmpty'))}</p>`;
}

function renderMediaDesigner(force) {
  const host = $('mediaDesigner'), m = mediaById(state.selectedMediaId);
  const sig = JSON.stringify([I18N.lang, m, m && mediaUse(m.id).map(c => [c.id, c.title]), runMode()]);
  const editing = host.contains(document.activeElement) && ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
  if (!force && (ed.sig.designer === sig || editing)) return;
  ed.sig.designer = sig;
  if (!m) { host.innerHTML = ''; host.hidden = true; return; }
  host.hidden = false;
  const users = mediaUse(m.id), lock = runMode() ? 'disabled' : '';
  host.innerHTML = `
    <div class="designer-head"><span class="eyebrow">${h(t('soundDesign'))}</span><button data-md="close" class="square" title="${h(t('close'))}">✕</button></div>
    <label class="full-label">${h(t('audioName'))}<input data-media="name" type="text" value="${h(m.name)}" ${lock}></label>
    <p class="micro">${h(m.filename)} · ${m.source_channels} ch · ${h(t('fileLength'))} ${fmtDuration(m.duration_s)}</p>
    <div class="field-row three">
      <label>${h(t('audioGain'))}<input data-media="gain_db" type="number" min="-90" max="12" step="0.5" value="${fmt(m.gain_db,1)}" ${lock}></label>
      <label>${h(t('trimStart'))}<input data-media="trim_start_s" type="number" min="0" step="0.01" value="${fmt(m.trim_start_s)}" ${lock}></label>
      <label>${h(t('trimEnd'))}<input data-media="trim_end_s" type="number" min="0" step="0.01" value="${fmt(m.trim_end_s)}" ${lock}></label>
    </div>
    <div class="field-row three">
      <label>${h(t('fadeIn'))}<input data-media="fade_in_s" type="number" min="0" step="0.05" value="${fmt(m.fade_in_s)}" ${lock}></label>
      <label>${h(t('fadeOut'))}<input data-media="fade_out_s" type="number" min="0" step="0.05" value="${fmt(m.fade_out_s)}" ${lock}></label>
      <label class="check inline-check"><input data-media="loop" type="checkbox" ${m.loop ? 'checked' : ''} ${lock}> ${h(t('loop'))}</label>
    </div>
    <p class="micro">${h(t('trimHelp', {len:fmtDuration(playDuration(m))}))}</p>
    ${m.source_channels === 2 ? `<div class="field-row">
      <label>${h(t('stereoFile'))}<select data-media="stereo_mode" ${lock}><option value="width" ${m.stereo_mode === 'width' ? 'selected' : ''}>${h(t('keepStereo'))}</option><option value="mono" ${m.stereo_mode !== 'width' ? 'selected' : ''}>${h(t('monoDownmix'))}</option></select></label>
      <label>${h(t('stereoWidth'))}<input data-media="stereo_width_deg" type="number" min="0" max="180" step="5" value="${fmt(m.stereo_width_deg,0)}" ${lock || m.stereo_mode !== 'width' ? 'disabled' : ''}></label></div>
      <p class="micro">${h(t('stereoHelp'))}</p>` : ''}
    <label class="full-label">${h(t('notes'))}<textarea data-media="notes" rows="2" ${lock}>${h(m.notes)}</textarea></label>
    <div class="used-by"><span class="small-label">${h(t('usedByCues', {n:users.length}))}</span>${users.map(c => `<button class="chip" data-md="cue" data-cue-id="${h(c.id)}">#${cueIndex(c.id) + 1} ${h(c.title)}</button>`).join('') || `<span class="micro">${h(t('notInAnyCue'))}</span>`}</div>
    <div class="designer-actions">
      <button data-md="audition" class="secondary">▷ ${h(t('audition'))}</button>
      <button data-md="new-cue" class="secondary" ${lock}>＋ ${h(t('newCueWithAudio'))}</button>
      <label class="secondary file-button ${lock ? 'disabled' : ''}">⇆ ${h(t('replaceFile'))}<input id="replaceMediaFile" type="file" accept=".wav,.aif,.aiff,.flac,.ogg,.mp3,.aac,.m4a" ${lock}></label>
      <button data-md="delete" class="danger" ${users.length || lock ? 'disabled' : ''} title="${h(users.length ? t('deleteAudioInUse') : t('deleteAudio'))}">${h(t('delete'))}</button>
    </div>`;
}

/* ---------- cue list ---------- */
function cueTags(c, voices, next) {
  const mine = voices.filter(v => v.cue_id === c.id);
  const playing = mine.some(v => v.state === 'playing' && !v.stopping);
  const fading = !playing && mine.some(v => v.stopping);
  const queued = !playing && mine.some(v => v.state === 'queued' && !v.stopping);
  return [playing ? 'LIVE' : fading ? 'FADE' : queued ? 'WAIT' : '', c.id === next ? 'NEXT' : '', c.id === state.selectedCueId ? 'SEL' : ''].filter(Boolean);
}
// Elapsed / length and the row's progress bar while the cue is sounding.
function cueProgress(row, c, voices) {
  const live = voices.filter(v => v.cue_id === c.id && v.state === 'playing');
  const total = cueDuration(c), dur = row.querySelector('.dur');
  if (!live.length) { row.style.setProperty('--progress', '0%'); if (dur) dur.textContent = fmtDuration(total); return; }
  const elapsed = Math.max(...live.map(v => v.elapsed_s));
  row.style.setProperty('--progress', total === Infinity ? '100%' : `${Math.min(100, elapsed / Math.max(total, .01) * 100).toFixed(1)}%`);
  if (dur) dur.textContent = total === Infinity ? `${fmt(elapsed, 1)} s ⟲` : `${fmt(elapsed, 1)} / ${fmt(total, 1)} s`;
}
function renderCueList(force) {
  const host = $('performCues'), next = state.status?.next_cue_id, voices = state.status?.mixer?.voices || [];
  host.querySelectorAll('.perf-cue').forEach(row => {
    const c = state.project.cues.find(x => x.id === row.dataset.cueId);
    if (!c) return;
    const tags = cueTags(c, voices, next);
    row.classList.toggle('selected', c.id === state.selectedCueId);
    row.classList.toggle('next', c.id === next);
    row.classList.toggle('playing', tags.includes('LIVE'));
    row.classList.toggle('fading', tags.includes('FADE'));
    const tag = row.querySelector('.tag');
    if (tag) tag.textContent = tags.join(' · ');
    cueProgress(row, c, voices);
  });
  const stored = state.project.cues.filter(c => c.spatial_preset).length;
  // NEXT / LIVE / SEL are patched in place above; rebuilding on them would swallow
  // a click in progress whenever GO moves NEXT.
  const sig = JSON.stringify([I18N.lang, runMode(), state.project.cues.map(c => [c.id, c.title, c.spatial_preset, c.stop_fade_s,
    c.layers.map(l => [l.id, l.media_id, l.muted, l.delay_s, l.direction_mode, l.path, l.position_deg]), StageMap.presetState(c)]),
    state.project.media.map(m => [m.id, m.duration_s, m.trim_start_s, m.trim_end_s, m.loop])]);
  if (!force && (host.dataset.signature === sig || pointerHeld)) return;
  host.dataset.signature = sig;
  const focusedId = host.contains(document.activeElement) ? document.activeElement.dataset.cueId : null;
  const scroll = $('cueListBody')?.scrollTop ?? 0;  // a rebuild must not jump the list back to the top
  const lock = runMode() ? 'disabled' : '';
  host.innerHTML = `<div class="section-heading perf-cues-head"><span>${h(t('cueList'))} <span class="count">${h(t('cueCount', {n:state.project.cues.length}))}</span></span>
      <span><button data-cl="new" class="quiet" ${lock}>＋ ${h(t('newCue'))}</button>
      <button data-cl="store-all" class="quiet" ${lock} title="${h(t('storeAllTip'))}">${h(t('storeAll'))}</button>
      <button data-cl="recall-all" class="quiet" ${stored ? '' : 'disabled'} title="${h(t('recallAllTip'))}">${h(t('recallAll'))}</button></span></div>` +
    `<div class="perf-cue-list" id="cueListBody">${state.project.cues.map((c, i) => {
      const tags = cueTags(c, voices, next), preset = StageMap.presetState(c);
      const cls = [c.id === next ? 'next' : '', c.id === state.selectedCueId ? 'selected' : '', tags.includes('LIVE') ? 'playing' : ''].join(' ');
      const dots = c.layers.map((l, j) => `<i style="background:${LAYER_COLORS[j % LAYER_COLORS.length]}"${l.muted ? ' class="muted"' : ''}></i>`).join('');
      return `<div class="perf-cue ${cls}" role="button" tabindex="0" data-cue-id="${h(c.id)}" draggable="${runMode() ? 'false' : 'true'}"><span class="num" title="${h(t('playOrder'))}">#${i + 1}</span>
        <span class="title">${h(c.title)}</span><span class="tag">${tags.join(' · ')}</span>
        <span class="kind"><span class="layer-dots">${dots}</span>${h(c.layers.length ? t('layersShort', {n:c.layers.length}) : t('emptyCue'))}</span>
        <span class="dur">${fmtDuration(cueDuration(c))}</span>
        <span class="preset ${preset}" title="${h(t({none:'presetNone', stored:'presetStored', changed:'presetChanged'}[preset]))}">${{none:'—', stored:'✓', changed:'●'}[preset]}</span>
        <span class="ctrl"><button class="cue-play" data-play title="${h(t('playTip'))}" aria-label="${h(t('playCue'))}">▶</button><button class="cue-stop" data-stop title="${h(t('stopTip', {s:fmt(c.stop_fade_s ?? 2, 1)}))}" aria-label="${h(t('stopCue'))}">■</button></span></div>`;
    }).join('')}${runMode() ? '' : `<div class="cue-dropzone" data-cl="drop-new">${h(t('dropNewCue'))}</div>`}</div>`;
  host.querySelectorAll('.perf-cue').forEach(row => cueProgress(row, state.project.cues.find(x => x.id === row.dataset.cueId), voices));
  $('cueListBody').scrollTop = scroll;
  if (focusedId) host.querySelector(`[data-cue-id="${focusedId}"]`)?.focus({preventScroll:true});
}

/* ---------- inspector: cue settings, layers, selected layer ---------- */
function field(label, attrs, value) {
  return `<label>${h(label)}<input ${attrs} value="${h(value)}"></label>`;
}
function choice(label, attrs, value, options) {
  return `<label>${h(label)}<select ${attrs}>${options.map(([v, text]) => `<option value="${v}" ${v === value ? 'selected' : ''}>${h(text)}</option>`).join('')}</select></label>`;
}
function presetText(cue) {
  const at = cue.spatial_preset?.stored_at ? new Date(cue.spatial_preset.stored_at).toLocaleString(I18N.lang === 'zh' ? 'zh-CN' : 'en') : '';
  return t({none:'presetNoneLong', stored:'presetStoredLong', changed:'presetChangedLong'}[StageMap.presetState(cue)], {at});
}
function renderLayerEditor(cue, layer, lock) {
  if (!layer) return `<p class="direction-mode-help">${h(t('noLayersHelp'))}</p>`;
  const m = mediaById(layer.media_id), isPath = layer.direction_mode === 'path';
  const duration = Math.max(playDuration(m), isPath ? layer.path.at(-1)?.time_s || 0 : 0);
  let body;
  if (isPath) {
    const rows = layer.path.map((p, i) => `<tr class="${i === ed.selectedPoint ? 'selected' : ''}" data-row="${i}">
      <td>${i === 0 ? '▶' : i + 1}</td>
      <td><input type="number" data-pt="${i}" data-k="time_s" min="0" step="0.1" value="${fmt(p.time_s)}" ${lock} aria-label="${h(t('pointTime', {n:i + 1}))}"></td>
      <td><input type="number" data-pt="${i}" data-k="x_m" step="0.05" value="${fmt(p.x_m)}" ${lock} aria-label="X ${i + 1}"></td>
      <td><input type="number" data-pt="${i}" data-k="y_m" step="0.05" value="${fmt(p.y_m)}" ${lock} aria-label="Y ${i + 1}"></td>
      <td><button data-ly="delete-point" data-pt="${i}" title="${h(t('deletePoint'))}" ${lock || layer.path.length <= 1 ? 'disabled' : ''}>×</button></td></tr>`).join('');
    body = `<div class="perf-tools" role="group" aria-label="${h(t('mapTool'))}">
        <button data-ly="tool" data-tool="position" class="${ed.tool === 'position' ? 'active' : ''}" ${lock}>◎ ${h(t('toolMove'))}</button>
        <button data-ly="tool" data-tool="add" class="${ed.tool === 'add' ? 'active' : ''}" ${lock}>＋ ${h(t('toolAdd'))}</button></div>
      <p class="micro">${h(lock ? t('runLockedShort') : ed.tool === 'add' ? t('toolAddHelp') : t('toolMoveHelp'))}</p>
      <table class="path-table"><thead><tr><th>#</th><th>${h(t('timeS'))}</th><th>X m</th><th>Y m</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      ${duration > 0 ? `<label class="small-label" for="layerPreview">${h(t('previewTime', {t:ed.previewT == null ? t('off') : fmt(ed.previewT, 1) + ' s'}))}</label>
        <input id="layerPreview" type="range" min="0" max="${duration}" step="0.05" value="${ed.previewT ?? 0}">` : ''}`;
  } else {
    const adsr = layer.direction_adsr || DEFAULT_ADSR;
    body = `<div class="field-row">${field(t('bearing'), `data-layer-field="position_deg" type="number" min="0" max="360" step="0.5" ${lock}`, fmt(layer.position_deg))}<span class="micro">${h(t('angleModeHelp'))}</span></div>` +
      (layer.direction_mode === 'adsr'
        ? `<div class="adsr-meta">${[['attack_s', 'adsrAttack'], ['peak_offset_deg', 'adsrPeak'], ['decay_s', 'adsrDecay'], ['sustain_offset_deg', 'adsrSustain'], ['release_s', 'adsrRelease'], ['release_offset_deg', 'adsrReleaseOffset']]
            .map(([k, key]) => field(t(key), `data-adsr="${k}" type="number" step="0.1" ${lock}`, fmt(adsr[k]))).join('')}</div>`
        : `<table class="path-table"><thead><tr><th>#</th><th>${h(t('timeS'))}</th><th>${h(t('offsetDeg'))}</th><th></th></tr></thead><tbody>${layer.modulation.map((p, i) => `<tr>
            <td>${i + 1}</td><td><input type="number" data-kf="${i}" data-k="time_s" min="0" step="0.1" value="${fmt(p.time_s)}" ${lock}></td>
            <td><input type="number" data-kf="${i}" data-k="offset_deg" step="1" value="${fmt(p.offset_deg)}" ${lock}></td>
            <td><button data-ly="delete-key" data-kf="${i}" ${lock || layer.modulation.length <= 1 ? 'disabled' : ''}>×</button></td></tr>`).join('')}</tbody></table>
          <button data-ly="add-key" class="quiet wide" ${lock}>＋ ${h(t('addKeyframe'))}</button>`);
  }
  return `<div class="section-label layer-head"><i style="background:${layerColor(cue, layer)}"></i>${h(t('selectedLayer', {n:layerIndex(cue, layer) + 1, name:layerName(layer)}))}</div>
    ${choice(t('motion'), `data-layer-field="direction_mode" ${lock}`, layer.direction_mode, [['path', t('motionPath')], ['keyframes', t('motionKeyframes')], ['adsr', t('motionAdsr')]])}
    ${body}`;
}
function renderInspector(force) {
  const host = $('performTarget'), cue = currentCue(), layer = currentLayer();
  const sig = JSON.stringify([I18N.lang, runMode(), state.project.auto_replace, cue, state.selectedLayerId, ed.selectedPoint, ed.tool, ed.follow, ed.previewT,
    cueIndex(cue?.id), cue && cue.layers.map(l => mediaById(l.media_id)?.name)]);
  const editing = host.contains(document.activeElement) && ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
  if (!force && (ed.sig.inspector === sig || editing)) return;
  ed.sig.inspector = sig;
  if (!cue) { host.innerHTML = `<p class="small-muted">${h(t('noCueSelected'))}</p>`; return; }
  const lock = runMode() ? 'disabled' : '';
  const layers = cue.layers.map((l, i) => `<tr class="layer-row${l.id === layer?.id ? ' selected' : ''}${l.muted ? ' muted' : ''}" data-layer-id="${h(l.id)}">
      <td><i class="layer-dot" style="background:${LAYER_COLORS[i % LAYER_COLORS.length]}"></i>${i + 1}</td>
      <td class="layer-name" title="${h(mediaById(l.media_id)?.filename || '')}">${h(layerName(l))}<small>${l.direction_mode === 'path' ? (l.path.length > 1 ? t('pathPoints', {n:l.path.length}) : 'XY') : fmt(l.position_deg, 0) + '°'}</small></td>
      <td><input type="number" data-lf="gain_db" min="-90" max="12" step="0.5" value="${fmt(l.gain_db, 1)}" ${lock} aria-label="${h(t('layerGain'))}"></td>
      <td><input type="number" data-lf="delay_s" min="0" step="0.1" value="${fmt(l.delay_s, 1)}" ${lock} aria-label="${h(t('layerDelay'))}"></td>
      <td><input type="checkbox" data-lf="muted" ${l.muted ? 'checked' : ''} ${lock} aria-label="${h(t('layerMute'))}"></td>
      <td><button data-ly="remove-layer" title="${h(t('removeLayer'))}" ${lock}>×</button></td></tr>`).join('');
  host.innerHTML = `
    <div class="perf-target-head"><span class="eyebrow">${h(ed.follow ? t('targetFollowing') : t('targetManual'))}</span>
      <span>${ed.follow ? '' : `<button data-cue-action="follow" class="secondary">↺ ${h(t('followNext'))}</button>`}</span></div>
    ${lock ? `<h2>#${cueIndex(cue.id) + 1} · ${h(cue.title)}</h2>` : `<label class="full-label">${h(t('cueTitle'))}<input data-cue-field="title" type="text" value="${h(cue.title)}"></label>`}
    <div class="cue-actions">
      <button data-cue-action="play" class="primary" title="${h(t('playTip'))}">${h(t('playCue'))}</button>
      <button data-cue-action="stop" class="secondary" title="${h(t('stopTip', {s:fmt(cue.stop_fade_s ?? 2, 1)}))}">${h(t('stopCue'))}</button>
      <button data-cue-action="arm" class="secondary">${h(t('setAsNext'))}</button>
      ${lock ? '' : `<button data-cue-action="duplicate" class="quiet">${h(t('duplicateCue'))}</button>
      <button data-cue-action="delete" class="danger">${h(t('deleteCue'))}</button>`}
    </div>
    <div class="section-label">${h(t('layersTitle', {n:cue.layers.length}))}</div>
    ${cue.layers.length ? `<table class="layer-table"><thead><tr><th></th><th>${h(t('audio'))}</th><th>${h(t('layerGainShort'))}</th><th>${h(t('layerDelayShort'))}</th><th>${h(t('layerMuteShort'))}</th><th></th></tr></thead><tbody>${layers}</tbody></table>` : ''}
    <p class="micro">${h(t('layersHelp'))}</p>
    ${renderLayerEditor(cue, layer, lock)}
    <div class="section-label">${h(t('playback'))}</div>
    <div class="field-row three">
      ${field(t('cueGain'), `data-cue-field="gain_db" type="number" min="-90" max="12" step="0.5" ${lock}`, fmt(cue.gain_db, 1))}
      ${field(t('preWait'), `data-cue-field="pre_wait_s" type="number" min="0" step="0.1" ${lock}`, fmt(cue.pre_wait_s))}
      ${field(t('postWait'), `data-cue-field="post_wait_s" type="number" min="0" step="0.1" ${lock}`, fmt(cue.post_wait_s))}
    </div>
    <div class="field-row">
      ${choice(t('startAction'), `data-cue-field="start_mode" ${lock}`, cue.start_mode, [['replace', t(state.project.auto_replace ? 'startReplace' : 'startReplaceOff')], ['layer', t('startLayer')], ['queue', t('startQueue')]])}
      ${choice(t('autoNext'), `data-cue-field="continue_mode" ${lock}`, cue.continue_mode, [['manual', t('autoManual')], ['auto_continue', t('autoContinue')], ['auto_follow', t('autoFollow')]])}
    </div>
    <div class="field-row three">
      ${field(t('stopFade'), `data-cue-field="stop_fade_s" type="number" min="0" max="60" step="0.1" ${lock}`, fmt(cue.stop_fade_s ?? 2))}
      ${choice(t('replaceStyle'), `data-cue-field="replace_style" ${lock}`, cue.replace_style, [['crossfade', t('crossfade')], ['cut', t('declickCut')]])}
      ${field(t('transitionS'), `data-cue-field="transition_s" type="number" min="0" max="60" step="0.1" ${lock}`, fmt(cue.transition_s))}
    </div>
    <p class="micro">${h(t('playbackHelp'))}</p>
    <div class="section-label">${h(t('presets'))}</div>
    <div class="perf-presets">
      <button data-cue-action="store" class="primary" ${lock}>${h(t('store'))}</button>
      <button data-cue-action="recall" class="secondary" ${cue.spatial_preset ? '' : 'disabled'}>${h(t('recall'))}</button>
      <button data-cue-action="reset" class="danger" ${lock}>${h(t('reset'))}</button>
    </div>
    <p class="micro perf-preset-state">${h(presetText(cue))} ${h(t('resetHelp'))}</p>`;
}

/* ---------- stage map ---------- */
function mapPoint(event) {
  const svg = $('performMap').querySelector('svg');
  const pt = svg.createSVGPoint(); pt.x = event.clientX; pt.y = event.clientY;
  const local = pt.matrixTransform(svg.getScreenCTM().inverse());
  const g = StageMap.geometry(state.project.speakers);
  const m = g.toMetres(local.x, local.y), lim = g.extent;
  return {x:Math.round(Math.max(-lim, Math.min(lim, m.x)) * 100) / 100, y:Math.round(Math.max(-lim, Math.min(lim, m.y)) * 100) / 100};
}
function layerStereo(layer) {
  const m = layer && mediaById(layer.media_id);
  return m && m.source_channels === 2 && m.stereo_mode === 'width' ? Number(m.stereo_width_deg) : 0;
}
function layerPoint(layer, time = null) {
  if (!layer) return null;
  if (layer.direction_mode !== 'path') {
    const p = StageMap.bearingPoint(layer.position_deg, state.project.speakers);
    return {x:p.x_m, y:p.y_m};
  }
  if (time != null) return StageMap.pathAt(layer.path, time);
  const p = layer.path[ed.selectedPoint] || layer.path[0];
  return {x:p.x_m, y:p.y_m};
}
function speakerNotes() {
  const mix = state.status?.mixer;
  return state.project.speakers.map(s => {
    const ch = s.output_channel - 1, notes = [];
    if (s.trim_db) notes.push(`trim ${s.trim_db > 0 ? '+' : ''}${fmt(s.trim_db, 1)} dB`);
    if (mix?.autocal_enabled) notes.push(`AutoCal ${fmt(mix.autocal_gain_db?.[ch], 1)} dB / ${fmt(mix.autocal_delay_ms?.[ch], 2)} ms`);
    return notes.join(' · ');
  });
}
function renderMap(force) {
  const cue = currentCue(), layer = currentLayer(), host = $('performMap');
  const sig = JSON.stringify([I18N.lang, runMode(), state.project.speakers, cue?.layers, layer?.id, ed.selectedPoint, ed.previewT,
    state.project.media.map(m => [m.id, m.stereo_mode, m.stereo_width_deg, m.name]), speakerNotes()]);
  if (!force && ed.sig.map === sig && host.querySelector('svg')) return;
  ed.sig.map = sig;
  const others = (cue?.layers || []).filter(l => l !== layer).map(l => {
    const p = layerPoint(l, l.direction_mode === 'path' ? 0 : null);
    return {id:l.id, x:p.x, y:p.y, color:layerColor(cue, l), label:`${layerIndex(cue, l) + 1} ${layerName(l)}`, path:l.direction_mode === 'path' ? l.path : null};
  });
  host.innerHTML = StageMap.svg({
    speakers:state.project.speakers, notes:speakerNotes(), interactive:!runMode() && !!layer, labels:stageLabels(),
    path:layer?.direction_mode === 'path' ? layer.path : null, selected:ed.selectedPoint, others,
    color:layer ? layerColor(cue, layer) : null, label:layer ? `${layerIndex(cue, layer) + 1} ${layerName(layer)}` : '',
    anglePoint:layer && layer.direction_mode !== 'path' ? layerPoint(layer) : null,
    gainPoint:layerPoint(layer, layer?.direction_mode === 'path' ? ed.previewT : null), stereo:layerStereo(layer),
  });
  host.classList.toggle('locked', runMode());
  renderLive();
}
// Playing layers and speaker meters, extrapolated between status polls.
function renderLive() {
  const live = $('performMap').querySelector('.live-layer');
  if (!live || !state.project) return;
  const g = StageMap.geometry(state.project.speakers), mix = state.status?.mixer;
  const since = (performance.now() - ed.statusAt) / 1000;
  const rotation = state.project.global_rotation_deg + currentShowOffset();
  const parts = [];
  for (const s of state.project.speakers) {
    const level = mix?.meters?.[s.output_channel - 1] || 0, p = StageMap.speakerXY(s);
    if (level > 0.002) parts.push(`<circle cx="${g.px(p.x)}" cy="${g.py(p.y)}" r="${18 + Math.min(1, level * 3) * 16}" class="sm-meter" style="opacity:${0.25 + Math.min(1, level * 3) * 0.6}"/>`);
  }
  for (const v of mix?.voices || []) {
    if (v.state !== 'playing') continue;
    const cue = state.project.cues.find(c => c.id === v.cue_id), layer = cue?.layers.find(l => l.id === v.layer_id);
    let p;
    if (layer?.direction_mode === 'path' && layer.path?.length) {
      p = StageMap.rotate(StageMap.pathAt(layer.path, v.elapsed_s + since), rotation);
    } else if (v.position_xy) {
      p = {x:v.position_xy[0], y:v.position_xy[1]};
    } else {
      const b = StageMap.bearingPoint(v.position_deg, state.project.speakers);
      p = {x:b.x_m, y:b.y_m};
    }
    const label = cue ? `#${cueIndex(cue.id) + 1} ${layer ? layerName(layer) : cue.title}` : v.title;
    parts.push(`<circle cx="${g.px(p.x)}" cy="${g.py(p.y)}" r="9" class="sm-live"/><text x="${g.px(p.x) + 12}" y="${g.py(p.y) + 4}" class="sm-live-label">${h(label)}</text>`);
  }
  const pose = state.status?.simulation?.pose;
  if (pose) {  // virtual headphone listener: where the monitor stands and faces
    const head = pose.head_deg * Math.PI / 180, x = g.px(pose.x_m), y = g.py(pose.y_m);
    parts.push(`<circle cx="${x}" cy="${y}" r="8" class="sm-listener"/><line x1="${x}" y1="${y}" x2="${x + 22 * Math.sin(head)}" y2="${y - 22 * Math.cos(head)}" class="sm-listener-head"/><text x="${x + 11}" y="${y + 18}" class="sm-small">${h(t('listener'))}</text>`);
  }
  live.innerHTML = parts.join('');
}
function animate() {
  if (state.project && ed.dragging < 0) renderLive();
  requestAnimationFrame(animate);
}
function renderOutputs() {
  const cue = currentCue(), layer = currentLayer(), host = $('performOutputs');
  const p = layerPoint(layer, layer?.direction_mode === 'path' ? ed.previewT : null);
  if (!cue || !layer || !p) { host.innerHTML = ''; return; }
  const gains = StageMap.sourceGains(p, state.project.speakers, layerStereo(layer), layer.direction_mode !== 'path');
  const mix = state.status?.mixer;
  host.innerHTML = `<div class="section-heading">${h(t('outputsFor', {name:layerName(layer)}))}</div><div class="outputs-grid">` +
    [...state.project.speakers].sort((a, b) => a.output_channel - b.output_channel).map(s => {
      const v = gains[s.output_channel - 1], db = v > 1e-4 ? 20 * Math.log10(v) : -Infinity;
      const level = mix?.meters?.[s.output_channel - 1] || 0;
      return `<div class="perf-gain"><b>CH${s.output_channel}</b><span>${h(s.name)}</span>
        <div class="bar"><i style="width:${(v * 100).toFixed(1)}%"></i><em style="width:${Math.min(100, level * 115).toFixed(1)}%"></em></div>
        <small>${Number.isFinite(db) ? fmt(db, 1) + ' dB' : '−∞'}</small></div>`;
    }).join('') + `</div><p class="micro">${h(t('outputsHelp'))}</p>`;
}

function followNext() {
  const next = state.status?.next_cue_id ?? null;
  if ((ed.follow || runMode()) && next !== ed.lastNext && next && cueIndex(next) >= 0) selectCue(next, {follow:true});
  ed.lastNext = next;
}
function render(force = false) {
  if (!state.project) return;
  followNext();
  ed.statusAt = performance.now();
  renderLibrary(force);
  renderMediaDesigner(force);
  if (ed.dragging < 0) renderMap(force);
  renderOutputs();
  renderCueList(force);
  renderInspector(force);
}

/* ---------- presets ---------- */
function storePreset(cue) {
  cue.spatial_preset = {layers:StageMap.cueSnapshot(structuredClone(cue.layers)), stored_at:new Date().toISOString()};
}
function recallPreset(cue) {
  if (!cue.spatial_preset) return false;
  for (const stored of cue.spatial_preset.layers) {
    const layer = cue.layers.find(l => l.id === stored.layer_id) || (cue.spatial_preset.layers.length === 1 && cue.layers.length === 1 ? cue.layers[0] : null);
    if (layer) Object.assign(layer, structuredClone(StageMap.spatialSnapshot(stored)));
  }
  return true;
}

/* ---------- events: library ---------- */
$('librarySearch').addEventListener('input', e => { ed.search = e.target.value; renderLibrary(true); });
$('libraryList').addEventListener('click', e => {
  const item = e.target.closest('[data-media-id]');
  if (!item) return;
  if (e.target.closest('[data-lib="audition"]')) { auditionMedia(item.dataset.mediaId); return; }
  state.selectedMediaId = item.dataset.mediaId;
  render(true);
});
$('libraryList').addEventListener('dblclick', e => {
  const item = e.target.closest('[data-media-id]');
  if (item && !e.target.closest('button')) auditionMedia(item.dataset.mediaId);
});
$('libraryList').addEventListener('dragstart', e => {
  const item = e.target.closest('[data-media-id]');
  if (!item) return;
  e.dataTransfer.setData(MEDIA_TYPE, item.dataset.mediaId);
  e.dataTransfer.setData('text/plain', mediaById(item.dataset.mediaId)?.name || '');
  e.dataTransfer.effectAllowed = 'copy';
  document.body.classList.add('dragging-media');
});
document.addEventListener('drop', () => document.body.classList.remove('dragging-media'), true);
document.addEventListener('dragend', () => { document.body.classList.remove('dragging-media'); document.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target')); });
// Audio files from the computer: drop anywhere on the library column.
const hasFiles = e => [...(e.dataTransfer?.types || [])].includes('Files');
$('libraryPanel').addEventListener('dragover', e => { if (hasFiles(e)) { e.preventDefault(); $('libraryPanel').classList.add('drop-target'); } });
$('libraryPanel').addEventListener('dragleave', e => { if (!$('libraryPanel').contains(e.relatedTarget)) $('libraryPanel').classList.remove('drop-target'); });
$('libraryPanel').addEventListener('drop', e => {
  if (!hasFiles(e)) return;
  e.preventDefault(); $('libraryPanel').classList.remove('drop-target');
  if (guardEdit()) uploadFiles([...e.dataTransfer.files]);
});

$('mediaDesigner').addEventListener('change', async e => {
  const m = mediaById(state.selectedMediaId);
  if (!m || runMode()) return;
  if (e.target.id === 'replaceMediaFile') {
    const file = e.target.files?.[0]; if (!file) return;
    await mediaMutation(async () => {
      try {
        await saveNow();
        const form = new FormData(); form.append('file', file, file.name);
        const r = await api(`/projects/${state.project.id}/media/${m.id}/replace`, {method:'POST', body:form});
        Object.assign(m, r.media);
        await saveNow(); changed(t('fileReplaced'));
      } catch (err) { report(err); }
    });
    return;
  }
  const key = e.target.dataset.media; if (!key) return;
  if (key === 'loop') m.loop = e.target.checked;
  else if (key === 'name') m.name = e.target.value.trim() || t('untitledAudio');
  else if (key === 'notes') m.notes = e.target.value.slice(0, 2000);
  else if (key === 'stereo_mode') m.stereo_mode = e.target.value;
  else {
    const v = num(e.target.value);
    m[key] = key === 'gain_db' ? Math.max(-90, Math.min(12, v)) : key === 'stereo_width_deg' ? Math.max(0, Math.min(180, v)) : Math.max(0, v);
    reflect(e.target, m[key], key === 'gain_db' ? 1 : key === 'stereo_width_deg' ? 0 : 2);
    if (key === 'trim_end_s' && m.trim_end_s && m.trim_end_s <= m.trim_start_s) { reflect(e.target, m.trim_end_s = 0); notify(t('trimInvalid'), true); }
    if (key === 'trim_start_s' && m.trim_end_s && m.trim_start_s >= m.trim_end_s) { reflect(e.target, m.trim_start_s = 0); notify(t('trimInvalid'), true); }
  }
  changed();
});
$('mediaDesigner').addEventListener('click', e => {
  const b = e.target.closest('[data-md]'), m = mediaById(state.selectedMediaId);
  if (!b || !m) return;
  const what = b.dataset.md;
  if (what === 'close') { state.selectedMediaId = null; render(true); }
  else if (what === 'audition') auditionMedia(m.id);
  else if (what === 'cue') { selectCue(b.dataset.cueId, {follow:false}); const cue = currentCue(); const l = cue?.layers.find(x => x.media_id === m.id); if (l) selectLayer(l.id); render(true); }
  else if (!guardEdit()) return;
  else if (what === 'new-cue') { newCue(m.id); changed(t('cueCreated')); }
  else if (what === 'delete' && !mediaUse(m.id).length && confirm(t('confirmDeleteAudio', {name:m.name}))) {
    state.project.media = state.project.media.filter(x => x.id !== m.id);
    state.selectedMediaId = null;
    changed(t('audioDeleted'));
  }
});

/* ---------- events: cue list ---------- */
$('performCues').addEventListener('click', e => {
  const b = e.target.closest('[data-cl]');
  if (b?.dataset.cl === 'new') { if (guardEdit()) { newCue(null); changed(t('cueCreated')); } return; }
  if (b?.dataset.cl === 'store-all') {
    if (!guardEdit() || !confirm(t('confirmStoreAll'))) return;
    state.project.cues.forEach(storePreset);
    changed(t('storedAll', {n:state.project.cues.length}));
    return;
  }
  if (b?.dataset.cl === 'recall-all') {
    const count = state.project.cues.filter(c => c.spatial_preset).length;
    if (!confirm(t('confirmRecallAll', {n:count}))) return;
    state.project.cues.forEach(recallPreset);
    ed.selectedPoint = 0;
    changed(t('recalledAll', {n:count}));
    return;
  }
  const row = e.target.closest('[data-cue-id]');
  if (!row) return;
  if (e.target.closest('[data-play]')) { playCue(row.dataset.cueId); return; }
  if (e.target.closest('[data-stop]')) { stopCue(row.dataset.cueId); return; }
  selectCue(row.dataset.cueId);
  render(true);
  renderTransport();  // the GO hint names the selected cue at once
});
$('performCues').addEventListener('keydown', e => {
  const row = e.target.closest('.perf-cue');
  if (row && e.target === row && e.key === 'Enter') { e.preventDefault(); selectCue(row.dataset.cueId); render(true); }
});
$('performCues').addEventListener('dblclick', e => {
  const row = e.target.closest('[data-cue-id]');
  if (row && !runMode() && !e.target.closest('.ctrl')) { e.preventDefault(); playCue(row.dataset.cueId); }
});
$('performCues').addEventListener('dragstart', e => {
  const row = e.target.closest('.perf-cue');
  if (!row || runMode()) return;
  e.dataTransfer.setData(CUE_TYPE, row.dataset.cueId);
  e.dataTransfer.effectAllowed = 'move';
});
function dropKind(e) {
  const types = [...(e.dataTransfer?.types || [])];
  return types.includes(MEDIA_TYPE) ? 'media' : types.includes(CUE_TYPE) ? 'cue' : null;
}
$('performCues').addEventListener('dragover', e => {
  if (!dropKind(e) || runMode()) return;
  e.preventDefault();
  document.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target'));
  (e.target.closest('.perf-cue, .cue-dropzone') || $('performCues')).classList.add('drop-target');
});
$('performCues').addEventListener('drop', e => {
  const kind = dropKind(e);
  if (!kind || !guardEdit()) return;
  e.preventDefault();
  document.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target'));
  const row = e.target.closest('.perf-cue');
  if (kind === 'cue') {
    if (row) moveCue(e.dataTransfer.getData(CUE_TYPE), cueIndex(row.dataset.cueId));
    return;
  }
  const mediaId = e.dataTransfer.getData(MEDIA_TYPE);
  if (row) {
    const cue = state.project.cues.find(c => c.id === row.dataset.cueId);
    if (addLayer(cue, mediaId, null)) changed(t('layerAdded', {name:mediaById(mediaId)?.name, cue:cue.title}));
  } else { newCue(mediaId); changed(t('cueCreated')); }
});

/* ---------- events: inspector ---------- */
$('performTarget').addEventListener('click', e => {
  const cue = currentCue();
  if (!cue) return;
  const row = e.target.closest('tr.layer-row');
  if (row && !e.target.closest('input,button')) { selectLayer(row.dataset.layerId); render(true); return; }
  const pathRow = e.target.closest('tr[data-row]');
  if (pathRow && !e.target.closest('input,button')) { ed.selectedPoint = Number(pathRow.dataset.row); ed.previewT = null; render(true); return; }
  const a = e.target.closest('[data-cue-action]');
  if (a) {
    const what = a.dataset.cueAction;
    if (what === 'follow') { ed.follow = true; ed.lastNext = undefined; render(true); }
    else if (what === 'arm') prepareCue(cue.id);
    else if (what === 'play') playCue(cue.id);
    else if (what === 'stop') stopCue(cue.id);
    else if (what === 'recall') { if (recallPreset(cue)) { ed.selectedPoint = 0; ed.previewT = null; changed(t('recalled', {cue:cue.title})); } }
    else if (!guardEdit()) return;
    else if (what === 'store') { storePreset(cue); changed(t('stored', {cue:cue.title})); }
    else if (what === 'reset') {
      for (const l of cue.layers) Object.assign(l, {direction_mode:'path', position_deg:0, modulation:[{time_s:0, offset_deg:0}], path:[StageMap.bearingPoint(0, state.project.speakers)]});
      ed.selectedPoint = 0; ed.previewT = null;
      changed(t('resetDone', {cue:cue.title}));
    } else if (what === 'duplicate') {
      const copy = structuredClone(cue);
      copy.id = newId(); copy.title = t('copyOf', {title:cue.title}); copy.spatial_preset = null;
      for (const l of copy.layers) l.id = newId();
      state.project.cues.splice(cueIndex(cue.id) + 1, 0, copy);
      selectCue(copy.id, {follow:false});
      changed(t('cueDuplicated'));
    } else if (what === 'delete' && confirm(t('confirmDeleteCue', {title:cue.title}))) {
      const idx = cueIndex(cue.id);
      state.project.cues.splice(idx, 1);
      selectCue(state.project.cues[Math.min(idx, state.project.cues.length - 1)]?.id ?? null, {follow:false});
      changed(t('cueDeleted'));
    }
    return;
  }
  const b = e.target.closest('[data-ly]'), layer = currentLayer();
  if (!b || !guardEdit()) return;
  const what = b.dataset.ly;
  if (what === 'remove-layer') {
    const target = cue.layers.find(l => l.id === b.closest('tr')?.dataset.layerId);
    if (target && confirm(t('confirmRemoveLayer', {name:layerName(target)}))) {
      cue.layers.splice(cue.layers.indexOf(target), 1);
      state.selectedLayerId = null;
      changed(t('layerRemoved'));
    }
  } else if (!layer) return;
  else if (what === 'tool') { ed.tool = b.dataset.tool; render(true); }
  else if (what === 'delete-point' && layer.path.length > 1) {
    layer.path.splice(Number(b.dataset.pt), 1);
    ed.selectedPoint = Math.min(ed.selectedPoint, layer.path.length - 1);
    changed();
  } else if (what === 'add-key') {
    const lastT = layer.modulation.at(-1)?.time_s || 0;
    layer.modulation.push({time_s:Math.round((lastT + Math.max(1, playDuration(mediaById(layer.media_id)) / 4)) * 10) / 10, offset_deg:layer.modulation.at(-1)?.offset_deg ?? 0});
    changed();
  } else if (what === 'delete-key' && layer.modulation.length > 1) {
    layer.modulation.splice(Number(b.dataset.kf), 1);
    changed();
  }
});
$('performTarget').addEventListener('change', e => {
  const cue = currentCue(), layer = currentLayer();
  if (!cue || runMode()) return;
  const el = e.target, v = num(el.value);
  if (el.dataset.cueField) {
    const key = el.dataset.cueField;
    if (key === 'title') cue.title = el.value.trim() || t('newCueTitle');
    else if (el.tagName === 'SELECT') cue[key] = el.value;
    else { cue[key] = key === 'gain_db' ? Math.max(-90, Math.min(12, v)) : ['transition_s', 'stop_fade_s'].includes(key) ? Math.max(0, Math.min(60, v)) : Math.max(0, v); reflect(el, cue[key], key === 'gain_db' ? 1 : 2); }
    changed(); return;
  }
  if (el.dataset.lf) {
    const target = cue.layers.find(l => l.id === el.closest('tr')?.dataset.layerId);
    if (!target) return;
    if (el.dataset.lf === 'muted') target.muted = el.checked;
    else if (el.dataset.lf === 'gain_db') reflect(el, target.gain_db = Math.max(-90, Math.min(12, v)), 1);
    else reflect(el, target.delay_s = Math.max(0, Math.min(3600, v)), 1);
    changed(); return;
  }
  if (!layer) return;
  if (el.dataset.layerField === 'direction_mode') {
    layer.direction_mode = el.value;
    // Converting keeps the sound: the current bearing becomes a point on the speaker edge.
    if (el.value === 'path' && !layer.path?.length) layer.path = [StageMap.bearingPoint(layer.position_deg, state.project.speakers)];
    if (el.value === 'adsr' && !layer.direction_adsr) layer.direction_adsr = {...DEFAULT_ADSR};
    ed.selectedPoint = 0; changed(); return;
  }
  if (el.dataset.layerField === 'position_deg') { reflect(el, layer.position_deg = ((v % 360) + 360) % 360); changed(); return; }
  if (el.dataset.adsr) {
    const k = el.dataset.adsr;
    reflect(el, layer.direction_adsr[k] = k.endsWith('_s') ? Math.max(0, v) : Math.max(-2160, Math.min(2160, v)));
    changed(); return;
  }
  if (el.dataset.kf != null) {
    const p = layer.modulation[Number(el.dataset.kf)];
    if (!p) return;
    p[el.dataset.k] = el.dataset.k === 'time_s' ? Math.max(0, Math.min(14400, v)) : Math.max(-2160, Math.min(2160, v));
    layer.modulation.sort((a, b) => a.time_s - b.time_s);
    changed(); return;
  }
  const i = Number(el.dataset.pt), key = el.dataset.k;
  if (!key || !layer.path?.[i]) return;
  const point = layer.path[i];
  point[key] = key === 'time_s' ? Math.min(14400, Math.max(0, v)) : Math.min(100, Math.max(-100, v));
  layer.path.sort((a, b) => a.time_s - b.time_s);
  ed.selectedPoint = Math.max(0, layer.path.indexOf(point));
  changed();
});
$('performTarget').addEventListener('input', e => {
  if (e.target.id !== 'layerPreview') return;
  ed.previewT = num(e.target.value);
  const label = $('performTarget').querySelector('label[for="layerPreview"]');
  if (label) label.textContent = t('previewTime', {t:fmt(ed.previewT, 1) + ' s'});
  renderMap(true); renderOutputs();
});

/* ---------- events: stage map ---------- */
$('performMap').addEventListener('pointerdown', e => {
  const cue = currentCue();
  if (!cue || !e.target.closest('svg')) return;
  const other = e.target.closest('[data-layer]');
  if (other) { selectLayer(other.dataset.layer); render(true); return; }
  if (runMode()) { notify(t('runLocked')); return; }
  const layer = currentLayer();
  if (!layer) { notify(t('dragAudioHere')); return; }
  const hit = e.target.closest('[data-ppoint]'), p = mapPoint(e);
  ed.previewT = null;
  if (hit && layer.direction_mode === 'path') {
    ed.selectedPoint = Number(hit.dataset.ppoint);
  } else if (layer.direction_mode !== 'path') {
    layer.direction_mode = 'path';
    layer.path = [{time_s:0, x_m:p.x, y_m:p.y}];
    ed.selectedPoint = 0;
  } else if (ed.tool === 'add' || e.shiftKey) {
    const last = layer.path.at(-1), d = playDuration(mediaById(layer.media_id));
    const step = d > 0 ? Math.max(0.5, d / 8) : 2;
    layer.path.push({time_s:Math.round((last.time_s + step) * 100) / 100, x_m:p.x, y_m:p.y});
    ed.selectedPoint = layer.path.length - 1;
  } else {
    Object.assign(layer.path[ed.selectedPoint] || layer.path[0], {x_m:p.x, y_m:p.y});
  }
  ed.dragging = ed.selectedPoint;
  $('performMap').setPointerCapture(e.pointerId);
  renderMap(true); renderOutputs();
});
$('performMap').addEventListener('pointermove', e => {
  const layer = currentLayer();
  if (ed.dragging < 0 || !layer?.path?.[ed.dragging]) return;
  const p = mapPoint(e);
  Object.assign(layer.path[ed.dragging], {x_m:p.x, y_m:p.y});
  renderMap(true); renderOutputs();
});
function endDrag() {
  if (ed.dragging < 0) return;
  ed.dragging = -1;
  changed();
}
$('performMap').addEventListener('pointerup', endDrag);
$('performMap').addEventListener('pointercancel', endDrag);
$('performMap').addEventListener('dragover', e => {
  if (dropKind(e) !== 'media' || runMode()) return;
  e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
  $('performMap').classList.add('drop-target');
});
$('performMap').addEventListener('dragleave', () => $('performMap').classList.remove('drop-target'));
$('performMap').addEventListener('drop', e => {
  if (dropKind(e) !== 'media' || !guardEdit()) return;
  e.preventDefault();
  $('performMap').classList.remove('drop-target');
  const mediaId = e.dataTransfer.getData(MEDIA_TYPE), p = mapPoint(e);
  const cue = currentCue();
  if (cue) { if (addLayer(cue, mediaId, p)) changed(t('layerAddedAt', {name:mediaById(mediaId)?.name, x:fmt(p.x, 1), y:fmt(p.y, 1)})); }
  else { newCue(mediaId, p); changed(t('cueCreated')); }
});

/* ---------- modes ---------- */
// Design = full editing; Show = everything locked except GO/STOP/PANIC, ▶/■, NEXT and Recall.
function setMode(run) {
  document.body.classList.toggle('performing', run);
  $('modeEdit').setAttribute('aria-pressed', String(!run));
  $('modePerform').setAttribute('aria-pressed', String(run));
  if (run) { ed.follow = true; ed.lastNext = undefined; state.selectedMediaId = null; }
  render(true);
}
$('modeEdit').addEventListener('click', () => setMode(false));
$('modePerform').addEventListener('click', () => setMode(true));
const simPanel = document.querySelector('.simulation-panel');
if (simPanel) {
  const saved = edStorage(SIM_KEY);
  if (saved) simPanel.open = saved === 'open';
  simPanel.addEventListener('toggle', () => edStorage(SIM_KEY, simPanel.open ? 'open' : 'closed'));
}
I18N.onChange(() => render(true));
// Every launch opens in Show mode; ?mode=edit opens Design instead.
const urlMode = new URLSearchParams(location.search).get('mode');
document.body.classList.toggle('performing', urlMode !== 'edit');
$('modeEdit').setAttribute('aria-pressed', String(!runMode()));
$('modePerform').setAttribute('aria-pressed', String(runMode()));
if (urlMode) history.replaceState(null, '', location.pathname);
requestAnimationFrame(animate);
// Show mode: a cue picked in the list (not NEXT) is where FADE GO / CUT GO starts;
// the sequence then continues after it. ▶ / ■ never change this.
function goTarget() {
  const id = state.selectedCueId, next = state.status?.next_cue_id;
  return runMode() && !ed.follow && id && id !== next && cueIndex(id) >= 0 ? id : null;
}
function afterGo() { ed.follow = true; ed.lastNext = undefined; }
globalThis.SpatialEditor = {render, setMode, goTarget, afterGo};
