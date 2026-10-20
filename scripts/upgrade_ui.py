from pathlib import Path
root = Path(__file__).resolve().parents[1]
p=root/'stagespatialcue/static/index.html'
s=p.read_text()
s=s.replace('<title>StageSpatialCue — 4-channel theatre cue lab</title>', '<title>SpatialStage — Four-channel stage sound control</title>')
s=s.replace('Stage<span>Spatial</span>Cue','Spatial<span>Stage</span>')
s=s.replace('''        <label for="inputSelect" class="small-label spaced">INPUT / metadata only in v0.1</label>
        <select id="inputSelect" aria-label="Preferred input device (not routed)"></select>
        <p class="micro">Live microphone routing is not active in this prototype.</p>''', '''        <p class="micro">Input is a numbered folder of local audio files. No live microphone capture is used.</p>''')
s=s.replace('''        <p class="micro">Rotation affects all active sources. Distance ≠ full room acoustics.</p>''','''        <label class="check"><input type="checkbox" id="globalEnvelopeEnabled" /> Enable show-wide direction envelope</label>
        <div id="globalEnvelopeFields" class="global-keys"></div>
        <button id="globalAddPoint" class="quiet" style="margin-top:8px;width:100%">＋ Global keyframe</button>
        <p class="micro">Global keyframe time starts at the first GO. Values are angular offsets in degrees. Both global controls affect live sounds.</p>''')
s=s.replace('''<div class="side-bottom"><b>LOCAL-FIRST</b><p>Show data stays in ~/.stagespatialcue/projects. No cloud or telemetry.</p></div>''','''<div class="side-bottom"><b>LOCAL-FIRST</b><p>Show data: ~/.spatialstage/projects · no telemetry or participant logging.</p></div>''')
s=s.replace('Space = GO · S = STOP · Alt+↓ = SKIP · Shift+Esc = PANIC','Space = FADE GO · C = CUT GO · S = STOP · Alt+↓ = SKIP · Shift+Esc = PANIC')
s=s.replace('''<button id="goButton" class="go" title="Space">▶ <b>GO</b></button>''', '''<button id="goButton" class="go" title="Space / normal transition">▶ <b>FADE GO</b></button><button id="cutGoButton" class="cut" title="C / bypass waits and transition">↯ CUT GO</button>''')
s=s.replace('''<span>Edits auto-save · Next playback uses new cue settings</span>''','''<span>Live direction/gain edits update active voices · Media swap is next playback</span>''')
s=s.replace('''<dialog id="stageDialog"><div class="modal-head"><div><span class="eyebrow">CALIBRATION</span><h2>Speaker geometry & routing</h2></div><button class="square" id="closeSettings">✕</button></div><p>Enter angles clockwise from the top (0°) and distances from one fixed audience/actor reference point. Channel numbers map to physical outputs.</p><div id="speakerFields"></div><p class="micro">Speaker angles must enclose the center without a gap of 180° or more. Do not infer precise actor-level acoustics from distances alone.</p><div class="modal-footer"><button id="cancelSettings" class="secondary">Cancel</button><button id="saveSettings" class="primary">Save geometry</button></div></dialog>''', '''<dialog id="stageDialog"><div class="modal-head"><div><span class="eyebrow">STAGE-CENTER CALIBRATION</span><h2>Four loudspeakers · geometry and routing</h2></div><button class="square" id="closeSettings">✕</button></div>
  <p>The <b>actor reference point is (0,0)</b>. +X points to 3 o'clock; +Y points to 12 o'clock. Enter measured speaker positions in metres. Angles and distances recalculate automatically. Each speaker should physically face the center. MAIN MUTE must be ON when changing routing.</p>
  <div id="speakerFields"></div>
  <div id="calibrationHints" class="calibration-hints"></div>
  <p class="micro">Software computes geometry and theoretical air-path delay / relative gain suggestions ONLY. It does not apply the delay or measure SPL. Use a calibrated microphone/SPL meter and the four channel test tones for actual verification.</p>
  <div class="modal-footer"><button id="cancelSettings" class="secondary">Cancel</button><button id="previewSettings" class="secondary">Preview calibration</button><button id="saveSettings" class="primary">Save geometry</button></div></dialog>''')
p.write_text(s)
p=root/'stagespatialcue/static/style.css'
s=p.read_text()
s+='''\n/* v0.2 theater controls / calibration */
.transport-buttons .cut{background:#71502b;border-color:#b38751;color:#ffe3b1;min-width:90px}
.global-keys{margin-top:9px;display:grid;gap:7px}
.global-key-row{display:grid;grid-template-columns:1fr 1fr 27px;gap:5px;align-items:center}
.global-key-row input{min-width:0;font-size:11px}
.global-key-row button{padding:3px 5px;background:#2d1d28;color:#ffb6bd}
.speaker-grid{grid-template-columns:1.3fr 1fr 1fr .7fr 1fr;gap:8px}
.calibration-hints{margin-top:10px;white-space:pre-wrap;background:#0b1421;border:1px solid #324558;border-radius:8px;padding:11px 13px;font-size:11px;color:#acc4d3;line-height:1.75}
.direction-mode-help{background:#17293c;border-left:2px solid #52dccd;padding:8px 10px;margin:10px 0;color:#abc4d5;font-size:11px;line-height:1.5}
.adsr-meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.adsr-meta>label{font-size:10px;color:#98aac0}
.adsr-meta>label input{margin-top:5px}
.swap-button{margin-top:10px;display:block;text-align:center;padding:9px;border:1px dashed #597487;color:#afd9e6;cursor:pointer;font-size:11px;border-radius:7px}
.swap-button input{display:none}
@media(max-width:1330px){.transport-buttons{flex-wrap:wrap;justify-content:flex-end}.transport-buttons button{height:42px}.transport-buttons .go{min-width:108px}}
'''
p.write_text(s)
