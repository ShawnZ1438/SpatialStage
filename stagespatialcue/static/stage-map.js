/* Stage-map geometry and SVG drawing shared by Performance mode, the inspector and
   Stage setup. Gain maths mirrors spatial.py (point_gains) for display only. */
'use strict';
const StageMap = (() => {
  const rad = d => d * Math.PI / 180;
  const wrap = d => ((d % 360) + 360) % 360;
  const round2 = v => Math.round(v * 100) / 100 || 0;  // never -0

  function speakerXY(s) {
    return {x: s.distance_m * Math.sin(rad(s.angle_deg)), y: s.distance_m * Math.cos(rad(s.angle_deg))};
  }
  // Active pair (speaker-list indices), unit-power pair gains and the distance from
  // the centre to the straight edge joining that pair along this bearing.
  function pairPan(bearing, speakers) {
    const order = speakers.map((_, i) => i).sort((a, b) => speakers[a].angle_deg - speakers[b].angle_deg);
    const target = wrap(bearing);
    let r = order.findIndex(i => speakers[i].angle_deg > target);
    if (r < 0) r = 0;
    const L = order[(r + order.length - 1) % order.length], R = order[r];
    const span = wrap(speakers[R].angle_deg - speakers[L].angle_deg), rel = wrap(target - speakers[L].angle_deg);
    const gl = Math.sin(rad(span - rel)) / Math.sin(rad(span)), gr = Math.sin(rad(rel)) / Math.sin(rad(span));
    const n = Math.hypot(gl, gr), gains = speakers.map(() => 0);
    gains[L] = gl / n; gains[R] = gr / n;
    const a = speakerXY(speakers[L]), b = speakerXY(speakers[R]), ex = b.x - a.x, ey = b.y - a.y;
    const ux = Math.sin(rad(target)), uy = Math.cos(rad(target));
    return {gains, ring: (a.x * ey - a.y * ex) / (ux * ey - uy * ex)};
  }
  // Physical-channel order (index = output_channel - 1), before trims/AutoCal.
  function pointGains(x, y, speakers, rotation = 0) {
    const {gains, ring} = pairPan(Math.atan2(x, y) * 180 / Math.PI + rotation, speakers);
    const ratio = Math.min(1, Math.max(0, Math.hypot(x, y) / ring));
    const blended = gains.map(g => ratio * g + (1 - ratio) * 0.5), n = Math.hypot(...blended);
    const physical = [0, 0, 0, 0];
    speakers.forEach((s, i) => { physical[s.output_channel - 1] = blended[i] / n; });
    return physical;
  }
  // Stereo width w: L/R at -w/2 and +w/2. Stage-map cues rotate the point (same
  // radius, as the mixer does); angle cues stay on the speaker edge (pure VBAP).
  function stereoPoints(p, speakers, stereo, edge = false) {
    const bearing = Math.atan2(p.x, p.y) * 180 / Math.PI;
    return [-stereo / 2, stereo / 2].map(w => {
      if (!edge) return rotate(p, w);
      const q = bearingPoint(bearing + w, speakers);
      return {x: q.x_m, y: q.y_m};
    });
  }
  // Per channel: one source, or the RMS of the equal-power L/R pair.
  function sourceGains(p, speakers, stereo = 0, edge = false) {
    if (!stereo) return pointGains(p.x, p.y, speakers);
    const [l, r] = stereoPoints(p, speakers, stereo, edge).map(q => pointGains(q.x, q.y, speakers));
    return l.map((v, i) => Math.sqrt((v * v + r[i] * r[i]) / 2));
  }
  // A stage-map point on the speaker edge sounds identical to a plain bearing.
  function bearingPoint(bearing, speakers, time_s = 0) {
    const {ring} = pairPan(bearing, speakers);
    return {time_s, x_m: round2(ring * Math.sin(rad(bearing))), y_m: round2(ring * Math.cos(rad(bearing)))};
  }
  function pathAt(path, t) {
    if (!path?.length) return null;
    if (t <= path[0].time_s) return {x: path[0].x_m, y: path[0].y_m};
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1], b = path[i];
      if (t <= b.time_s) {
        const f = (t - a.time_s) / Math.max(1e-9, b.time_s - a.time_s);
        return {x: a.x_m + (b.x_m - a.x_m) * f, y: a.y_m + (b.y_m - a.y_m) * f};
      }
    }
    const last = path.at(-1);
    return {x: last.x_m, y: last.y_m};
  }
  // Clockwise rotation, matching how global rotation is added to the bearing.
  function rotate(p, deg) {
    const c = Math.cos(rad(deg)), s = Math.sin(rad(deg));
    return {x: p.x * c + p.y * s, y: -p.x * s + p.y * c};
  }
  // Canonical copy of the fields Store/Recall/Reset own; key order is fixed so
  // JSON comparison can tell whether a cue still matches its stored preset.
  function spatialSnapshot(src) {
    const a = src.direction_adsr || {};
    return {
      direction_mode: src.direction_mode || 'keyframes',
      position_deg: Number(src.position_deg || 0),
      modulation: (src.modulation || []).map(p => ({time_s: Number(p.time_s), offset_deg: Number(p.offset_deg)})),
      direction_adsr: {attack_s: a.attack_s, peak_offset_deg: a.peak_offset_deg, decay_s: a.decay_s,
        sustain_offset_deg: a.sustain_offset_deg, release_s: a.release_s, release_offset_deg: a.release_offset_deg},
      path: (src.path || []).map(p => ({time_s: Number(p.time_s), x_m: Number(p.x_m), y_m: Number(p.y_m)})),
    };
  }
  // A cue preset stores every layer's spatial fields, keyed by layer id.
  function cueSnapshot(layers) {
    return (layers || []).map(l => ({layer_id: l.layer_id ?? l.id, ...spatialSnapshot(l)}));
  }
  function presetState(cue) {
    if (!cue?.spatial_preset) return 'none';
    return JSON.stringify(cueSnapshot(cue.layers)) === JSON.stringify(cueSnapshot(cue.spatial_preset.layers)) ? 'stored' : 'changed';
  }

  function geometry(speakers, size = 640) {
    const pts = speakers.map(speakerXY);
    const extent = Math.max(3.5, ...pts.map(p => Math.max(Math.abs(p.x), Math.abs(p.y)))) + 1.3;
    const k = size / (2 * extent);
    return {size, extent, k, px: x => size / 2 + x * k, py: y => size / 2 - y * k,
      toMetres: (X, Y) => ({x: (X - size / 2) / k, y: (size / 2 - Y) / k})};
  }
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  /* opts: speakers, notes[] (per speaker), path[], selected, anglePoint {x,y},
     gainPoint {x,y}, stereo (width ° or 0), interactive, size, labels {front, actor},
     color (selected layer), others [{id, x, y, color, label, path}] = the cue's other
     layers (clickable via data-layer). Returns SVG markup with an empty .live-layer group. */
  function svg(opts) {
    const {speakers, size = 640} = opts;
    const g = geometry(speakers, size), {px, py, extent} = g, parts = [];
    const whole = Math.floor(extent);
    for (let m = -whole; m <= whole; m++) {
      const strong = m === 0;
      parts.push(`<line x1="${px(m)}" y1="${py(-extent)}" x2="${px(m)}" y2="${py(extent)}" class="sm-grid${strong ? ' axis' : ''}"/>`,
        `<line x1="${px(-extent)}" y1="${py(m)}" x2="${px(extent)}" y2="${py(m)}" class="sm-grid${strong ? ' axis' : ''}"/>`);
    }
    for (let r = 1; r < extent; r++) {
      parts.push(`<circle cx="${px(0)}" cy="${py(0)}" r="${r * g.k}" class="sm-ring"/><text x="${px(r) + 3}" y="${py(0) + 12}" class="sm-small">${r} m</text>`);
    }
    const order = speakers.map((s, i) => [s, speakerXY(s), i]).sort((a, b) => a[0].angle_deg - b[0].angle_deg);
    parts.push(`<polygon points="${order.map(([, p]) => `${px(p.x)},${py(p.y)}`).join(' ')}" class="sm-edge"/>`);
    const labels = {front: '0° · FRONT / +Y', actor: 'ACTOR', ...(opts.labels || {})};
    parts.push(`<text x="${px(0)}" y="16" class="sm-label" text-anchor="middle">${esc(labels.front)}</text>`,
      `<circle cx="${px(0)}" cy="${py(0)}" r="13" class="sm-actor"/><text x="${px(0)}" y="${py(0) + 3}" class="sm-small" text-anchor="middle">${esc(labels.actor)}</text>`);
    for (const o of opts.others || []) {
      if (o.path?.length > 1) parts.push(`<polyline points="${o.path.map(q => `${px(q.x_m)},${py(q.y_m)}`).join(' ')}" class="sm-other-path" style="stroke:${o.color}"/>`);
      parts.push(`<g class="sm-other" data-layer="${esc(o.id)}"><circle cx="${px(o.x)}" cy="${py(o.y)}" r="9" style="fill:${o.color}"/><text x="${px(o.x) + 12}" y="${py(o.y) + 4}" class="sm-other-label">${esc(o.label)}</text></g>`);
    }
    if (opts.gainPoint) {
      const gains = sourceGains(opts.gainPoint, speakers, opts.stereo, !!opts.anglePoint);
      speakers.forEach(s => {
        const p = speakerXY(s), v = gains[s.output_channel - 1];
        if (v > 0.01) parts.push(`<line x1="${px(opts.gainPoint.x)}" y1="${py(opts.gainPoint.y)}" x2="${px(p.x)}" y2="${py(p.y)}" class="sm-gain" style="stroke-width:${1 + 5 * v};opacity:${0.15 + 0.75 * v}"/>`);
      });
    }
    order.forEach(([s, p, i]) => {
      // Name (and note) sit above upstage speakers and below downstage ones.
      const lx = px(p.x), ly = p.y >= 0 ? py(p.y) - (opts.notes?.[i] ? 37 : 24) : py(p.y) + 32, anchor = 'middle';
      parts.push(`<g class="sm-speaker" data-channel="${s.output_channel}"><circle cx="${px(p.x)}" cy="${py(p.y)}" r="16"/><text x="${px(p.x)}" y="${py(p.y) + 4}" text-anchor="middle">${s.output_channel}</text></g>`,
        `<text x="${lx}" y="${ly}" text-anchor="${anchor}" class="sm-label">${esc(s.name)}</text>`);
      if (opts.notes?.[i]) parts.push(`<text x="${lx}" y="${ly + 14}" text-anchor="${anchor}" class="sm-small">${esc(opts.notes[i])}</text>`);
    });
    if (opts.stereo && opts.gainPoint) {
      stereoPoints(opts.gainPoint, speakers, opts.stereo, !!opts.anglePoint).forEach((q, i) => {
        const label = i ? 'R' : 'L';
        parts.push(`<circle cx="${px(q.x)}" cy="${py(q.y)}" r="7" class="sm-stereo"/><text x="${px(q.x)}" y="${py(q.y) + 3.5}" text-anchor="middle" class="sm-stereo-label">${label}</text>`);
      });
    }
    const tint = opts.color ? ` style="--layer:${opts.color}"` : '';
    const first = opts.anglePoint || (opts.path?.[0] && {x: opts.path[0].x_m, y: opts.path[0].y_m});
    if (opts.label && first) parts.push(`<text x="${px(first.x) - 12}" y="${py(first.y) + 24}" text-anchor="end" class="sm-selected-label">${esc(opts.label)}</text>`);
    if (opts.anglePoint) {
      parts.push(`<line x1="${px(0)}" y1="${py(0)}" x2="${px(opts.anglePoint.x)}" y2="${py(opts.anglePoint.y)}" class="sm-anglemode"${tint}/>`,
        `<circle cx="${px(opts.anglePoint.x)}" cy="${py(opts.anglePoint.y)}" r="9" class="sm-point angle"${tint}/>`);
    }
    const path = opts.path || [];
    if (path.length > 1) {
      parts.push(`<polyline points="${path.map(p => `${px(p.x_m)},${py(p.y_m)}`).join(' ')}" class="sm-path" marker-mid="url(#smArrow)" marker-end="url(#smArrow)"${tint}/>`);
    }
    path.forEach((p, i) => {
      const sel = i === opts.selected;
      parts.push(`<circle data-ppoint="${i}" cx="${px(p.x_m)}" cy="${py(p.y_m)}" r="${sel ? 11 : 8}" class="sm-point${sel ? ' selected' : ''}${i === 0 ? ' start' : ''}"${tint}/>`,
        `<text x="${px(p.x_m) + 13}" y="${py(p.y_m) - 9}" class="sm-small">${i === 0 ? '▶ ' : ''}${Number(p.time_s).toFixed(1)} s</text>`);
    });
    return `<svg viewBox="0 0 ${size} ${size}" class="stage-map${opts.interactive ? ' interactive' : ''}" role="img" aria-label="Stage map: loudspeakers, actor centre and cue position">
      <defs><marker id="smArrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="sm-arrow"/></marker></defs>
      ${parts.join('')}<g class="live-layer"></g></svg>`;
  }

  return {speakerXY, pairPan, pointGains, stereoPoints, sourceGains, bearingPoint, pathAt, rotate, spatialSnapshot, cueSnapshot, presetState, geometry, svg};
})();
if (typeof module !== 'undefined') module.exports = StageMap;
