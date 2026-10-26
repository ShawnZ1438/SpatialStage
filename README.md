# SpatialStage

**Local Windows simulation console:** see [setup, scope and verified tests](docs/LOCAL_SIMULATION.md).
It uses the production cue/mixing engine with silent output, optional low-level stereo monitoring,
four-channel capture and editable stage visualization. Real four-output mode remains available.

**Local-first four-output spatial cue control for actor-centered experimental theatre.**

[中文说明](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md) · [Calibration](docs/CALIBRATION.md) · [AutoCal](docs/AUTOCAL.md) · [Reliability / audit fixes](docs/RELIABILITY.md) · [Open decisions](docs/OPEN_QUESTIONS.md)

> **v0.3.1 is a rehearsal prototype, not a production or hearing-safety guarantee.** The Python callback still takes locks and allocates arrays. Software tests do not validate a particular Apple Silicon Mac, console, microphone or speaker system. There is no claim of benefit for ADHD participants, no listener tracking, and no participant research logging. An independent physical mute must remain available.

## 1. What the system does

The performers are the listeners; there is no audience-facing coordinate system. Four speakers surround the acting area and face its center. A local browser edits cues and controls a Python audio engine. **Audio comes from a real four-channel CoreAudio device, not the browser's stereo output.**

| Capability | Current behavior |
|---|---|
| Direction | Clockwise 0.00–359.99° dial (360° input normalizes to 0°); 0=12 o'clock, 90=right, 180=bottom, 270=left |
| Spatialization | 2D adjacent-speaker constant-power VBAP at one fixed reference center |
| Movement | Per-cue relative angular keyframes or angular ADSR, or a stage-map XY position/path; plus global rotation and show envelope |
| Performance mode | Stage map that follows NEXT: drag position, draw a timed path, Store / Recall / Reset per cue, lock for the show |
| Cue playback | Replace, layer or queue; per-cue gain, fades, transition, pre/post waits |
| Operator controls | FADE GO, CUT GO, STOP, SKIP, ARM SELECTED, MAIN MUTE, PANIC |
| Media / projects | Local numbered-file/folder upload, stable manual ordering, file replacement, autosave, multiple projects, ZIP export |
| Live edits | Bearing, gain, angular envelopes and natural fade settings; no PCM reload or rescheduling of already queued voices |
| AutoCal | One center point, balanced, XLR input, EQ disabled; sequential sweeps, diagnostic plots, persisted reports, explicit human APPLY |
| Reliability | Persistent mute ramps, non-increasing stop envelopes, identity-based NEXT, predecoded GO, device-loss mute latch, queued browser saves |
| Not implemented | True pause/resume, loop/trim editor, stereo-width preservation, ZIP restore/import, MIDI/OSC, multi-window conflict resolution, automatic room EQ |

## 2. Mac setup and launch

Use native Apple Silicon Python **3.11–3.13**; Python 3.12 is the recommended setup target. A device must expose at least **four independent outputs** at 48 kHz. An optional XLR input is used only for AutoCal, not live microphone playback.

```bash
# First setup, with Homebrew already installed:
brew install python@3.12 portaudio libsndfile ffmpeg
git clone https://github.com/ShawnZ1438/SpatialStage.git
cd SpatialStage
./run_mac.command
```

**Double-click launch:** in Finder, double-click **`Start SpatialStage.command`** in the project folder. It installs on first run, keeps the Mac awake while the engine runs (`caffeinate`), and opens the browser in Performance mode. Double-clicking again while it runs just reopens the browser. Keep the Terminal window open during the show; closing it stops the engine. If the folder came from a ZIP download and macOS blocks the file, right-click → Open once.

Open `http://127.0.0.1:8765`. The launcher creates `.venv` and installs dependencies on first use or when `pyproject.toml` changes. That installation may need Internet access. Subsequent launches with installed dependencies are local/offline. `SPATIALSTAGE_PYTHON=/path/to/python3.12 ./run_mac.command` selects an interpreter for a new environment. An incompatible existing `.venv` must be recreated deliberately, not silently deleted.

Manual launch:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
spatialstage
# Equivalent factory entry point, without import-time project creation:
python -m uvicorn stagespatialcue.server:create_app --factory --host 127.0.0.1 --port 8765
```

Update an existing clone using `git pull --ff-only` and run `./run_mac.command` again. Do not replace unrelated local edits or force-push your branch. Keep a backup of show data before updating. Projects live in `~/.spatialstage/projects`, or under `STAGE_SPATIAL_DATA` when set.

## 3. Four-speaker geometry and physical routing

Mark the actual center and the 12-o'clock reference arrow on the floor. +X is right; +Y is up. Enter each speaker's **X/Y position in meters relative to that center**, not just four distances. Angles/distances are computed as `theta=atan2(x,y)` clockwise, `r=sqrt(x²+y²)`. The software does not infer where the actor actually stands or move the origin automatically.

| Physical role | Suggested bearing | Default output |
|---|---:|---:|
| L / front-left | 315° | CH1 |
| R / front-right | 45° | CH2 |
| RR / rear-right | 135° | CH3 |
| RL / rear-left | 225° | CH4 |

These angles are a starting layout, not required exact positions. Move the speakers back from the acting circle as needed, point them toward its center, and enter measured coordinates. Exactly four unique output channels are required; adjacent speaker bearings must be at least 0.01° apart (including across 0/360) and have gaps below 180°. 0.01° is **control resolution**, not promised perceptual accuracy.

```text
                       0° / +Y
           L / CH1                 R / CH2
                 \                 /
270° / −X         fixed center (0,0)          90° / +X
                 /                 \
           RL / CH4                RR / CH3
                         180°

Mac → USB/Thunderbolt multichannel interface or USB console
    → four discrete line outputs / console return channels
    → four isolated buses or direct outputs → four speakers
```

A stereo headphone socket, Bluetooth stereo or a console exposing only two USB returns is not four-channel surround. The console/interface model, drivers, routing and clock compatibility remain site-specific. A separate four-output sound interface is supported; an aggregate device is not automatically verified. In the console, avoid summing all four returns into the same stereo master. Verify CH1–CH4 one at a time at low physical gain, with actors absent.

The geometry preview computes theoretical relative gain/delay suggestions only; it **does not apply acoustic delay correction**. Measured AutoCal is a separate approval-controlled path. Room reflections are not modeled by VBAP; ignoring them in the model does not remove them from the venue. See [calibration](docs/CALIBRATION.md).

## 4. Cue design and show operation

### Import and editing

Name sources `001_Footsteps.wav`, `002_Car.wav`, `003_Wind.wav`. Import a folder or multiple files. **Only the newly imported batch is numerically sorted**, then appended; existing hand-arranged rows never get sorted again. Up/down buttons reorder rows. Click a row to edit it; selecting a row does not change NEXT. ARM SELECTED explicitly sets NEXT by immutable cue ID. Deleting NEXT clears it and requires re-arming.

WAV/AIFF/FLAC/OGG use libsndfile; formats not accepted there use FFmpeg when installed. Every source is currently downmixed to **mono**, resampled to 48 kHz and predecoded. Stereo width is not retained. Clip decoding is capped at 30 minutes (the FFmpeg fallback truncates at that limit); split longer sources. Maximum decoded cache is 700 MiB, not a total application memory guarantee. Upload limit is 150 MiB per file, 256 MiB per whole request and 250 files per request; split large batches.

Changing a cue's media affects its **next fresh playback**. Already playing or scheduled voices retain their existing PCM. Editing direction/gain/envelope updates matching voices; changing trigger timing does not retroactively reschedule them. Use STOP then ARM/GO to audition a new schedule. Live fade-in/out changes are blended over 15 ms rather than stepping their natural gain envelope.

### Transport and timing

| Action | Meaning |
|---|---|
| Space / FADE GO | Trigger NEXT and its automatic chain, respecting pre-wait/start mode/transition |
| C / CUT GO | Trigger one NEXT cue immediately, override queue/layer/pre-wait, replace with 5 ms de-click |
| S / STOP | Soft-stop existing voices (40 ms), cancel pending playback; repeating STOP cannot increase stop gain or extend its deadline |
| Alt+Down / SKIP | Advance NEXT without starting a sound; currently playing audio continues |
| MAIN MUTE | Ramp final output to/from zero over 15 ms; **cue and show clocks continue**, not a pause |
| Shift+Escape / PANIC | Clear scheduled voices and delay buffers, reset mute immediately; also request cancellation of AutoCal |

Typing in an input does not trigger ordinary transport shortcuts. PANIC remains available while a dialog/input has focus. It is immediate in the software mixer, not a guarantee to retract samples already buffered by CoreAudio, the console or speakers. Hardware mute is independent and necessary.

FADE GO's start modes: **replace** fades previous voices; **layer** preserves them; **queue** waits for already active/pending voices. Crossfade normally uses the configured 2–3 s transition; new very short clips cap the transition-in ramp at half their length. Natural fade-in/out still apply within clip duration.

`auto_continue`: next anchor = current cue start + current `post_wait_s`. `auto_follow`: next anchor = current cue scheduled end + current `post_wait_s`. The next cue then adds its own `pre_wait_s`. Thus both waits add if both are set. Fade durations are not subtracted from these waits. **Zero-wait auto-continue cues sharing an exact start frame are a simultaneous group**, even when their default mode is replace: they do not cancel one another. Nonzero-start replacement still replaces; CUT GO always triggers only one cue. This is a documented implementation choice, open to revising as a dedicated group-cue feature.

Automatic chains are planned at GO as one atomic scheduling operation. ARM and chain completion initiate background preload. **A cold-cache GO is rejected, not queued for late playback and not decoded on the transport thread.** Wait for ready or run Preflight and press GO again. The complete chain must fit the available cache. Preflight reports missing/invalid files and cache size issues.

### Angular movement

```text
effective angle = wrap360(base cue angle
                       + cue envelope offset(t)
                       + global rotation
                       + global show envelope(T))
```

Keyframe offsets are unwrapped: `0 → 360` is one clockwise revolution, not zero motion. For a car going from left through the top to right, base=270°, offsets=0→180°. Through the bottom use 0→−180°. Cue ADSR uses angular peak/sustain/final offsets, not loudness; its release is tied to file duration, **not a STOP key-off event**. The global envelope starts with the first scheduled cue, continues during mute and silent gaps, and is reset when re-arming an idle show. End-relative release and clock controls remain design decisions, not full synthesizer ADSR semantics.

### Performance mode and the stage map

**▶ Performance mode** (top bar, or `?mode=perform`) replaces the cue table with a stage map in metres around the actor centre. The map targets the NEXT cue and follows it after each GO; click another cue in the list to prepare it ahead (**↺ Follow NEXT** returns).

- **Position:** click or drag on the map. An angle-mode cue converts to a stage-map position the first time; its current bearing becomes the starting point on the speaker edge, so it sounds the same until moved.
- **Path:** choose **＋ Add path point** (or Shift+click) to append timed points; drag points to move them and edit time/X/Y in the table. Time is seconds from the start of the file; the source holds the first/last point before/after them. **Preview path time** scrubs a ghost position.
- **How a point sounds:** bearing comes from the centre as before. Distance only sets spread: on or beyond the dashed speaker edge = that speaker pair only (identical to plain VBAP); toward the centre the sound blends into all four speakers equally, so a path crossing the centre does not jump between opposite pairs. Power stays constant; there is no distance attenuation. Global rotation and the show envelope still rotate the result. The panel shows the four channel gains at the selected point; speaker labels show trims and active AutoCal values.
- **Store / Recall / Reset:** Store saves the cue's current position/path (and its angle settings) in the project. Recall restores it. Reset sets one static point at the front (0°). The list marks each cue ✓ stored, ● changed since stored, — none. **Store all / Recall all** act on every cue.
- **Lock:** tick *Lock map and presets* once the show is set; the map and editing are disabled (remembered in this browser). GO / STOP / PANIC and Recall still work.

Edits autosave like any other cue edit and apply to a cue that is already playing after ~300 ms. Edit mode's inspector shows a mini map for stage-map cues; *Modulation curve → Stage-map position / XY path* converts a cue there too. Stage setup draws the speaker layout with theoretical delay/level hints as you type.

### Saves and recovery

Edits autosave through a single-flight revision queue. A pending PUT never discards later edits; explicit Save waits for the newest revision. Failure keeps a dirty state and offers **Retry save**. The stage dialog closes only after acknowledgement. Project switching/export/transport preparation wait for pending saves. STOP/PANIC do not wait for saves and cancel a GO still waiting on save completion.

Polling updates row state without replacing the whole cue table. NEXT is tracked by cue ID, not row number. A stopped/disconnected output stream latches mute and rejects GO. Reconnect and unmute deliberately; no automatic replay or catch-up occurs. Use **one browser editor at a time**: cross-tab/version conflict protection is not implemented. Within one editor, media import merges newly added cue IDs and media replacement updates only media fields, preserving concurrent edits and deletions. Project switching waits for the active media operation.

## 5. AutoCal: center / balanced / XLR / EQ off

Place the XLR measurement microphone at the reference center near actor ear height. Use one compatible duplex interface/clock where possible. Confirm the actual input, four discrete outputs and physical low-level gain. Stop and disconnect show output, leave MAIN MUTE on, and clear actors from the test area. AutoCal uses a **separate measurement stream**; show MAIN MUTE does not suppress its intentional test sweeps.

Save the one-point balanced/XLR/no-EQ configuration, acknowledge the measurement checklist, then start CH1–CH4 sweeps. Inspect level in dBFS, SNR, relative timing and normalized response plots. Reports persist under the project; no raw microphone PCM or participant measurements are kept. Results initially require review. Only a passing, unchanged geometry/device profile plus typed **APPLY** can enable bounded attenuation and relative delay; ordinary project saves cannot enable compensation. EQ remains disabled. Cancel measurement or PANIC requests best-effort capture stop and discards incomplete runs. See [AutoCal details and limitations](docs/AUTOCAL.md).

One measurement point is center-only, **not multi-position optimization**, and dBFS is not calibrated sound pressure. Direct sound may be obscured by reflections; output-device names do not fingerprint external console gain/DSP changes. Recheck after any physical routing, gain or speaker change. No Audyssey code or licensed MultEQ implementation is included.

## 6. Data, backup and development

JSON saves are atomic. Media paths are isolated to their project. ZIP **export only** contains project JSON, currently referenced media and AutoCal JSON; unused assets, operator logs and temporary save files are excluded. Output spools to disk after 8 MiB and streams in chunks. ZIP restoration is manual for now; do not mistake an export button for a tested restore workflow.

Server binds only to 127.0.0.1:8765. Exact localhost/127.0.0.1 browser origins on port8765 are allowed; other browser origins/ports are rejected. This is not protection from another malicious local process or a compromised OS account. Do not expose the server to a LAN or tunnel. Optional operator diagnostics (`SPATIALSTAGE_DIAGNOSTICS=1`) remain off by default and are not participant logs.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
node --check stagespatialcue/static/app.js
node --check stagespatialcue/static/save-queue.js
node --check stagespatialcue/static/simulation.js
node --check stagespatialcue/static/stage-map.js
node --check stagespatialcue/static/perform.js
node --test tests/js/*.test.cjs
python -m ruff check stagespatialcue tests
python -m playwright install chromium
python scripts/browser_smoke.py --spawn
python scripts/browser_audit_regressions.py
```

The browser script creates isolated temporary projects, refuses an occupied operator port, imports silence and does not play audio. `--browser-path` selects an installed Chromium without hard-coded paths. `--inline-transport` is an explicit offline-DOM/local-API test mode for environments whose browser policy blocks HTTP navigation; CI uses normal HTTP. CI is configured for Python 3.11/3.12/3.13, Node syntax/regressions, correctness lint and browser interactions. CI results must be checked per commit, not inferred from its configuration.

The package remains `stagespatialcue` for compatibility. See [audit evidence and hardware acceptance](docs/RELIABILITY.md). Before using this as a sole live controller, validate the actual four-output Mac chain, hard mute, maximum acoustic levels, representative polyphony, disconnect recovery and off-center perception. Moving actors cannot all receive the same center-calibrated virtual direction.
