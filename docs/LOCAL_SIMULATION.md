# Local functional console (Shawn-PC)

Implemented on local branch `local/simulation-platform` from verified remote main
`b61f81537dbfbcc61e5465c0eac3d694afba0f06`. This records the initial local-only build; see [audit fixes](AUDIT_FIXES.md) for the subsequent authorized publication and validation scope.

## Start

Double-click **`Start Simulation (Windows).cmd`** (or run `./run_simulation.ps1`). On first run it
creates `.venv` with Python 3.11–3.13 and installs dependencies; it then opens
http://127.0.0.1:8765 in Performance mode. Data lives in `SpatialStage-test-data`,
separate from shows under the user profile, and the repository show (`show/audio`) is
imported there as *Show audio (repository)*. If an older SpatialStage engine already holds
port 8765, the launcher shows its PID/command and asks before stopping it.
`run_simulation.ps1 -InstallOnly` only prepares the environment.

### Virtual four-speaker headphone monitor

Expand **LOCAL SIMULATION**, choose *Virtual 4 speakers (headphones)*, click **Connect
headphone monitor** once to list devices, pick your headphones and click it again. Output
stays muted until you unmute. The real CH1–4 engine output is rendered as four virtual
speakers at their Stage setup positions, heard from **Listener X/Y** facing **Head bearing**:
1/r level and r/c arrival differences relative to the nearest speaker, a spherical-head
time difference, broadband level difference, far-ear head shadow and slight darkening
behind. At the centre it matches the console-levelled venue; walk the listener towards a
corner to hear how close performers perceive cues (the panning reference stays at the centre).
The listener is drawn on the Performance map. This is approximate (no HRTF, no room
reflections); front/back cues are weak on headphones. *Mono sum* remains for content checks.

Offline headphone render of one GO: `scripts/render_simulation.py --project ID --headphones 2,2,0`
also writes `<output>-headphones.wav` heard at x=2 m, y=2 m facing front.

1. Choose **Connect silent simulation**. MAIN MUTE stays on. Preflight decodes the
   numbered files; unmute explicitly and GO to see the real engine's CH1–4 meters.
2. To hear it, click **Connect stereo monitor** once to populate devices, select
   your headphones/PC output, then click it again. Reconnection cancels playback
   and mutes. ARM a cue, unmute and GO. No automatic replay occurs.
3. The four monitor controls provide gain 0–1, mute and solo. Solo is additive;
   mute wins. They apply only to the stereo listening path. Both L/R receive the
   same sum, with 0.025 gain per stem (-32 dB), capped by the production engine's
   clipped four-channel outputs. This is content audition, not surround rendering.
4. Use existing Cue direction, gain, fade, envelope, transition, global rotation,
   numbered import, save and Stage setup controls. Geometry/routing changes require
   settled MAIN MUTE. Speaker trims are real show settings; monitor gains are not.
5. **Start new capture**, operate the show, **Stop capture**, download WAV. Capture
   is the actual post-routing/post-compensation/post-master CH1–4 float PCM at 48 kHz.
   It stops at 60 seconds (~46 MiB). Starting another capture clears the old one;
   reconnecting discards it. Download first. Monitor mute/solo does not alter it.
6. **Disconnect output** or PANIC before leaving. Hardware four-output mode remains
   in the original left sidebar and retains its own muted connection workflow.

Offline render, no device and no wall-clock waiting:

```powershell
.\.venv\Scripts\python.exe scripts/render_simulation.py --project 2b71ed8221a0 --seconds 6
```

This schedules one real controller GO and its automatic chain, not later manual
GOs. `--index` selects a zero-based cue; `--output` chooses the WAV. Output JSON
records frames and clipping count. The UI capture instead records actual live edits.

## Scope and known limits

Known site facts: indoor venue, approximately 6 × 6 m stage, four **IBO PS 15**,
onsite console handles leveling. Exact specifications, speaker coordinates/heights,
room boundaries and interface remain unknown. The dashed stage footprint is not
a room boundary. Existing default speaker polar positions (3 m radius) are editable
placeholders, not measured corner coordinates. No brand/specification substitution.

The simulation calls the same StageController, Mixer.render, scheduling, file
decode, VBAP, fades, compensation and master limiter as the four-output path.
Meters are actual per-block post-clip peaks (polling can miss brief peaks); the
engine's PEAK OVER counter detects pre-clip overload blocks. Live bearing display
now includes cue and global envelopes. Actor/head markers are visual only; there
is no tracking and the mixer reference remains center. The silent thread is
approximately wall-clock paced, not a hardware latency benchmark.

No HRTF, acoustic propagation, room response or SPL simulation. No participant
logging. No AutoCal redesign: one point / balanced / XLR / experimental EQ off /
human APPLY gate remain intact. Stereo monitor requires a device supporting two
outputs at 48 kHz. Choose a different device if PortAudio rejects the selected one.
The first population click is intentional: it does not open an arbitrary device.
Monitor preferences are session-only and reset on reconnect. Use one browser.

Existing unsupported features remain unsupported: ZIP restore/import (audio import
is supported), true pause/resume, loop/trim editor, stereo-width preservation,
MIDI/OSC, multi-window conflict resolution and automatic room EQ.

## Initial simulator verification, 2026-10-23

The subsequent audit repair validation is recorded in [AUDIT_FIXES.md](AUDIT_FIXES.md).

- Python: **65 passed**, including new capture byte equality, cap/empty/stop rules,
  API GO/end-of-list/repeated STOP/live save, monitor gain/solo stem isolation,
  effective bearing, independent CH1–4 routing and clipping assertions.
- Existing regression coverage: replace/queue/layer timing, zero-wait simultaneous
  chains, sample-frame waits, repeated stop ramps, cold GO rejection, mute/panic,
  live fade/direction edits, channel permutation, 0° front/270° left, imports/order,
  export, save persistence and mocked AutoCal measurement/approval/cancellation.
- Node: **6 save regression tests passed**; app.js, save-queue.js and simulation.js
  syntax checks passed. Ruff correctness checks and `git diff --check` passed.
- Headless Edge against real localhost: import/order/row identity, in-flight save,
  failed speaker-save retry, reload/NEXT, AutoCal dialog, silent connection, capture
  download and actor inputs passed; zero uncaught browser errors. Screenshot:
  `test-output/browser.png`; transcript: `test-output/browser.txt`.
- Offline 6 s demo render: 288000 × 4 at 48000 Hz; zero clipping blocks. This first
  demo cue sweeps front-to-right/rear: CH4 is correctly silent for that cue.
  `test-output/offline-4ch.wav` plus JSON report. Full pytest output:
  `test-output/pytest-final.txt`.
- Actual local PortAudio stereo connection to Headphones (Elgato Wave:XLR): stayed
  master-muted, rendered 6144 zero-valued frames, connected=true, error=null,
  xruns=0. Closed afterward. This verifies muted opening/callback only, not audible
  playback, human listening or four-output hardware.
- Fixed verified Windows defects: open upload files now close before deletion;
  persisted UTF-8 project/calibration JSON is read explicitly as UTF-8. Without the
  latter, speaker names were corrupted and hot-edit geometry guards misfired.

Initial sandbox runs could not create pytest temporary directories or start the
test server reliably. Tests were rerun with isolated workspace temporary data and
approved execution outside that sandbox. No approval denial remains. One installed
Starlette/httpx deprecation warning remains; the passing suite is not warning-free.

Not validated: audible listening by a human, all OS audio drivers, long-duration
stress/maximum polyphony, real device disconnect during playback, real four-channel
interface, console routing, microphone or acoustic measurement, macOS on hardware.
Mocked output tests do not establish those results.

## Remaining hardware acceptance

1. Confirm actual interface/driver and four discrete outputs at 48 kHz.
2. At low console level, check CH1–4 individually against physical speaker labels;
   ensure no unwanted stereo summing or duplicated console buses.
3. Enter measured positions and confirm clockwise front/left conventions on site.
4. Verify console level matching, physical mute, polarity and acceptable levels.
5. Test STOP/PANIC, reconnect behavior, representative polyphony, long playback and
   operator edits on the real system. Keep independent hardware mute available.
6. If AutoCal is used later, test the actual one-point XLR chain and review results
   before human APPLY; no sweeps were sent to hardware during this task.
