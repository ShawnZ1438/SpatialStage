'use strict';
// Display maths must agree with spatial.point_gains (the engine is the source of truth).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const StageMap = require('../../stagespatialcue/static/stage-map.js');

const corners = [
  {name: 'L', angle_deg: 315, distance_m: Math.SQRT2 * 3, output_channel: 1},
  {name: 'R', angle_deg: 45, distance_m: Math.SQRT2 * 3, output_channel: 2},
  {name: 'RR', angle_deg: 135, distance_m: Math.SQRT2 * 3, output_channel: 3},
  {name: 'RL', angle_deg: 225, distance_m: Math.SQRT2 * 3, output_channel: 4},
];
const close = (actual, expected) => actual.forEach((v, i) => assert.ok(Math.abs(v - expected[i]) < 1e-6, `${actual} vs ${expected}`));

test('centre is all four, a speaker is itself, the edge is pairwise', () => {
  close(StageMap.pointGains(0, 0, corners), [.5, .5, .5, .5]);
  close(StageMap.pointGains(3, 3, corners), [0, 1, 0, 0]);
  close(StageMap.pointGains(-3, 0, corners), [Math.SQRT1_2, 0, 0, Math.SQRT1_2]);
  const g = StageMap.pointGains(1.2, -0.7, corners);
  assert.ok(Math.abs(g.reduce((s, v) => s + v * v, 0) - 1) < 1e-9);
});

test('bearing conversion lands on the speaker edge and rotation is clockwise', () => {
  assert.deepEqual(StageMap.bearingPoint(270, corners), {time_s: 0, x_m: -3, y_m: 0});
  const p = StageMap.rotate({x: 0, y: 2}, 90);
  assert.ok(Math.abs(p.x - 2) < 1e-9 && Math.abs(p.y) < 1e-9);
});

test('path interpolation holds the ends; presets compare canonically', () => {
  const path = [{time_s: 1, x_m: -2, y_m: 0}, {time_s: 3, x_m: 2, y_m: 2}];
  assert.deepEqual(StageMap.pathAt(path, 0), {x: -2, y: 0});
  assert.deepEqual(StageMap.pathAt(path, 2), {x: 0, y: 1});
  assert.deepEqual(StageMap.pathAt(path, 9), {x: 2, y: 2});
  const layer = {id: 'L1', media_id: 'm', direction_mode: 'path', position_deg: 0, modulation: [{time_s: 0, offset_deg: 0}], direction_adsr: {}, path};
  const cue = {layers: [layer]};
  assert.equal(StageMap.presetState(cue), 'none');
  cue.spatial_preset = {layers: StageMap.cueSnapshot(structuredClone(cue.layers)), stored_at: 'x'};
  assert.equal(StageMap.presetState(cue), 'stored');
  layer.path[0].x_m = -1;
  assert.equal(StageMap.presetState(cue), 'changed');
  layer.path[0].x_m = -2;
  cue.layers.push({...structuredClone(layer), id: 'L2'});  // a new layer also counts as a change
  assert.equal(StageMap.presetState(cue), 'changed');
});

test('stereo width: angle cues stay on the speaker edge, map cues rotate the point', () => {
  close(StageMap.sourceGains({x: 0, y: 3}, corners, 90, true), [Math.SQRT1_2, Math.SQRT1_2, 0, 0]);
  const [l, r] = StageMap.stereoPoints({x: 0, y: 3}, corners, 90, true);
  assert.ok(Math.abs(l.x + 3) < 1e-9 && Math.abs(l.y - 3) < 1e-9 && Math.abs(r.x - 3) < 1e-9);
  const [ml] = StageMap.stereoPoints({x: 0, y: 2}, corners, 90);
  assert.ok(Math.abs(Math.hypot(ml.x, ml.y) - 2) < 1e-9 && ml.x < 0);
});
