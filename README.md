# SpatialStage

**Local-first four-channel spatial sound cue controller for actor-centered experimental theatre.**

[简体中文安装与操作说明](README.zh-CN.md) · [Stage calibration](docs/CALIBRATION.md) · [Architecture](docs/ARCHITECTURE.md) · [Remaining decisions](docs/OPEN_QUESTIONS.md)

> **v0.2 — functional rehearsal prototype, NOT production-certified.** The software has automated tests but has **not** been validated with the actual Apple Silicon Mac, unknown mixing console, physical four-output interface or loudspeakers. Its Python/NumPy audio callback is not hard real-time. No clinical or acoustic benefit for ADHD participants is claimed. No participant data or research measurements are collected.

## Why it exists

SpatialStage is designed for sound designers and technical operators supporting theatre in which the **performers themselves** (not an audience) are the listeners. Four loudspeakers surround a circular acting area. Audio cues follow a script, and the operator can direct a prepared sound to any virtual clockwise angle, sweep it through the room, layer effects or move to a new cue. The performer can move **inside** the four-speaker perimeter; the panning geometry assumes one **fixed central reference**. This is a creative and acoustic-exploration tool, not an EEG/diagnostic system or spatial tracking solution.

The web UI is a controller on `127.0.0.1:8765`; audio does not play through the browser's stereo output. Python sends four discrete PCM channels to an actual CoreAudio/PortAudio four-output device, normally through an audio interface or a USB multi-output console.

### v0.2 capability matrix

| Feature | Available | Behavior |
|---|---|---|
| Spatial angle dial | ✅ | Clockwise 0.00–359.99°; 12 o'clock=0°, 3=90°, 6=180°, 9=270° |
| Four physical outputs | ✅, **hardware validation pending** | Explicit channel mapping CH1/CH2/CH3/CH4; requires interface exposing ≥4 independent outputs |
| Stage geometry | ✅ | Speaker X/Y (metres) relative to center automatically converted to angle/range |
| Calibration preview | ✅, **not real acoustic calibration** | Calculates theoretical propagation delay and relative distance gain suggestions; does **not** apply delay or measure SPL |
| VBAP directional panning | ✅ | Adjacent-speaker constant-power amplitude weighting for actor reference center |
| Local folder / numbered cues | ✅ | `001_...wav`, `002_...wav` sorted by numeric filename; uploaded media copied per project |
| Cue movement | ✅ | Free angular keyframes, plus a separate direction ADSR mode (attack/decay/sustain/release) |
| Global direction control | ✅ | Live rotation + optional show-wide keyframe envelope, measured from first GO audio start |
| FADE GO / CUT GO | ✅ | FADE GO follows cue start and transition config; CUT GO overrides queued/layer behavior to replace immediately with 5ms de-click |
| Replace / layer / queue | ✅ | Replace existing sound, play concurrently or wait for existing sounds to finish |
| Fades / pre/post intervals | ✅ | Gain envelope independent from angular modulation; pre- and post-wait do not subtract fade durations |
| Active-Cue editing | ✅, prototype | Direction/gain/ADSR/keyframe edits propagate to an active/queued voice on next autosave (~300ms); prior PCM buffer stays fixed |
| Change a Cue's file | ✅ | Replaces the selected cue's *future* media; playback already queued retains decoded samples |
| Multi-project, local persistence | ✅ | JSON + per-project media + ZIP export, automatic saves |
| Master mute / meters / STOP / PANIC / SKIP | ✅ | Mute starts ON; audio test runs a quiet 440Hz tone through only one channel |
| Scientific participant event logging | **No, intentionally** | Disabled; optional local operator-only diagnostics (`SPATIALSTAGE_DIAGNOSTICS=1`) |
| Mic input, listener tracking, HRTF, measured acoustic delays | ❌ | Not planned for the initial rehearsal build |
| Native real-time engine / hearing-safety certification | ❌ | Required before a mission-critical production |

## 1. Stage geometry, speaker map and VBAP

SpatialStage is **actor-centered**. There is no audience or audience-facing definition of front. Place the origin at the geometric midpoint of the four loudspeakers (or your taped center of the intended acting area). The flat floor has two coordinates: **+X to 3 o'clock/right**, **+Y to 12 o'clock/top**. Bearing is measured clockwise from the +Y axis, so **0° top**, **90° right**, **180° bottom**, **270° left**. Audio software does not know where the physical 12-o'clock arrow is: mark it on the actual stage.

```text
                              +Y / 0° / 12 o'clock
                                      ↑
      L / FRONT LEFT (CH1)             |              R / FRONT RIGHT (CH2)
           ~315°  ◉                   |                  ◉ ~45°
                    \                  |                /
                     \                 |               /
         270°  <------+---------- CENTER (0,0) --------+----> 90° / +X
                     /            ACTOR AREA           \
                    /                |                   \
        RL / REAR LEFT (CH4)          |              RR / REAR RIGHT (CH3)
           ~225°  ◉                   |                  ◉ ~135°
                                      ↓
                                   180°
```

Default positions are the four diagonal bearings **315°, 45°, 135°, 225°**, each 3 m from center, with editable distances and angular positions. This reflects loudspeakers near the middle of the 10–11, 1–2, 4–5 and 7–8 o'clock clock-face sectors. Speakers can move slightly behind the nominal circle as long as the actual X/Y readings are entered. They should **face the center** (the software previews an inward pointing direction equal to the speaker bearing + 180°).

**Enter X/Y in metres** (recommended) or plan the equivalent polar bearing/range:

```
x = distance * sin(angle)
y = distance * cos(angle)
angle = atan2(x, y)  (degrees, wrapped to [0,360))
distance = sqrt(x² + y²)
```

`Stage setup` has four speaker rows with name, X, Y, physical output channel (1–4, all unique), and per-output manual trim (dB). The app derives angle and distance automatically and rejects layouts with an angular gap ≥180° (which do not surround the center).

**2D VBAP (Vector-Based Amplitude Panning)**: for each requested source angle, choose the two neighboring speakers containing the direction, solve the positive two-vector amplitude weights, and normalize to equal power (`gL²+gR²=1` before optional manual trim). The result maps to four physical outputs, usually only the neighboring pair carrying the source at a time. Distances may optionally be used for a *rough* center-point distance gain multiplier, but this is **not equal-loudness room calibration**. Width, timing, off-center perception, room modes, speaker frequency response and reflections are not corrected. At different actor positions, the perceived virtual source can shift or lose focus; there is no head tracking.

### Geometry is not acoustic calibration

`Preview calibration` calculates, for each speaker:

- `angle_deg`, `distance_m`, `x_m`, `y_m`, inward orientation (angle + 180°).
- Theoretical propagation time `1000 × distance / 343` milliseconds (20°C approximation).
- Suggested additional delay `1000 × (maximum_distance − speaker_distance) / 343` milliseconds, **displayed only; not applied**.
- Suggested relative amplitude trim `20 log10(speaker_distance / median_distance)` dB, **displayed only**, based on an idealized distance law. Independently entered manual trims are applied to the VBAP mix.

Real calibration requires the actual console/output routing, channel isolation tests, speaker aiming, calibrated SPL measurements at the center and (ideally) multiple actor positions. Do not apply suggested delays or gain changes blindly. See [CALIBRATION.md](docs/CALIBRATION.md) for the measurement checklist, soundcheck procedure and pending data.

## 2. Connect an Apple Silicon Mac to the four speakers

```text
                           USB-C / Thunderbolt or class-compliant USB
  Mac (local SpatialStage) ────────> 4+ output audio interface
                                     OUT 1 ───► Console line input 1 ─► isolated bus 1 ─► L (315°)
                                     OUT 2 ───► Console line input 2 ─► isolated bus 2 ─► R ( 45°)
                                     OUT 3 ───► Console line input 3 ─► isolated bus 3 ─► RR(135°)
                                     OUT 4 ───► Console line input 4 ─► isolated bus 4 ─► RL(225°)
```

An alternative is direct Mac USB audio into a mixing console **if its USB driver advertises ≥4 independent CoreAudio output channels**, and if they can be routed to four isolated analog/AUX/matrix outputs. A generic **two-channel** USB mixer, Mac headphone port, AirPlay speaker pair or HDMI stereo endpoint is not enough. Do **not** combine all four software channels into the console's stereo main L/R bus; this destroys directional separation. Do not assume an aggregate of unrelated Bluetooth or AirPlay devices is a synchronized show solution.

1. Confirm the mixer/audio-interface brand/model, available USB channels, routing matrix and physical OUT 1–4. Connect cables with amps/console muted.
2. On macOS open **Applications → Utilities → Audio MIDI Setup**, inspect the device's independent channels, set **48,000 Hz** if supported. Apple references: [Audio device setup](https://support.apple.com/guide/audio-midi-setup/set-up-audio-devices-ams59f301fda/mac) and [Configure external multichannel speakers](https://support.apple.com/guide/audio-midi-setup/set-up-external-speakers-for-stereo-or-surround-sound-ams1005/mac).
3. In SpatialStage select the 4+ output device and click **Connect audio**. On connection, **MAIN MUTE is automatically ON** and the master starts at **−18 dB**.
4. Lower amplifier/console master gain, manually release mute, click **Test CH** and test channels 1→4 at a conservative level. Each test generates a brief approximately −22 dBFS 440 Hz sine in **one software channel**; this is a wiring test, **not** standardized SPL/pink-noise calibration.
5. Inspect independent console input meters, output bus meters and speaker, then set manual trim using a calibrated meter as needed. Mute again for geometry/routing edits.
6. Run **Preflight**, then rehearse FADE GO, CUT GO, STOP, SKIP, MAIN MUTE and PANIC before actors enter the stage.

The output system uses a `sounddevice.OutputStream` with 4 float32 channels, fixed 48 kHz, 512-frame callback (about 10.7 ms at nominal sample rate). This is a **prototype**, and the Mac hardware/driver adds latency. If no ≥4-channel device appears, show design still works but actual playback is blocked.

## 3. Install and run on Apple Silicon macOS

Requires: macOS, Apple Silicon, **Python 3.11–3.13 (3.12 recommended)**, Homebrew, 4-channel audio device for actual playback, an up-to-date browser (Chrome is recommended for folder import). Recommended: WAV 48 kHz. FFmpeg provides MP3/AAC/M4A fallback.

```bash
# Install third-party dependencies (Apple Silicon Homebrew typically /opt/homebrew)
brew install python@3.12 portaudio libsndfile ffmpeg

# Clone YOUR repo
git clone https://github.com/ShawnZ1438/SpatialStage.git
cd SpatialStage

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

# Optional: demo project and short synthetic FX (no copyrighted audio)
python scripts/seed_demo.py

# Launch loopback-only web controller
spatialstage
```

Open **http://127.0.0.1:8765** in the Mac's browser. Run `python -m pytest -q` to check the DSP and API reference tests. The optional `run_mac.command` helps on macOS with Python installed. To stop the local service, `Ctrl+C` in Terminal. A file dialog cannot directly grant the browser arbitrary ongoing access to a folder; imported files are copied to the application's local project store so future runs do not depend on browser permissions.

The local project root is `~/.spatialstage/projects/`. Files remain local by default and the server is bound to `127.0.0.1`, not to the LAN.

## 4. Add audio files, plan the Cue Stack

Name local audio files with leading cue numbers:

```text
Act-1-Audio/
  001_Door_Opens.wav
  002_Distant_Whisper.wav
  003_Car_Pass_Left_to_Right.wav
  004_Clock_Ring.wav
```

Click **Import folder** (or Files) and select files. The app stores copies under the active show's `media/` directory and sorts the **new Cue rows** by the leading number before the first underscore/dash/space. You can subsequently reorder cues with ↑/↓. Existing media is not removed when a Cue row is deleted. File sizes are limited to 150 MiB per upload; an individual predecoded sound is limited to 30 minutes, and the decoded cache is bounded at 700 MiB. MP3 etc. must decode successfully on the Mac. Multichannel/stereo source files are downmixed to mono before positioning; do not use prerendered four-channel master files as though the app preserved their channels.

Each cue has an editable name, source media, bearing, source gain, fade-in, fade-out, replace transition length/style, pre-wait, post-wait and direction modulation curve. You can select any future row without arming/playing it; **ARM SELECTED** changes the next Cue pointer. To replace the file attached to a row, choose **Replace this Cue's audio file**. Playback already scheduled or active retains previously decoded audio, which is safer than swapping the buffer during playback.

### Live operator control — two GO buttons

| Operator control | Exact meaning |
|---|---|
| **FADE GO** / `Space` | Trigger next cue according to its stored `start_mode` (`replace`, `layer`, `queue`), pre-wait and transition style. Crossfade replaces active audio with the configured transition. |
| **CUT GO** / `C` | Override next cue's start mode, **start now**, cancel pending cues and de-click active audio over **5 ms**. Trigger *only this* cue (automatic chain intentionally not followed for the cut operation). This is an immediate operational transition, not a sample-discontinuous zero-ms cut. |
| **STOP** / `S` | Apply a brief 40 ms ramp to all active voices and cancel scheduled voices. It does **not** turn on main mute or reset the armed Cue pointer. |
| **SKIP** / `Alt+↓` | Move the next-Cue pointer forward without firing the skipped Cue. |
| **PANIC** / `Shift+Esc` | Immediately discard all voices and force MAIN MUTE ON. |
| **MAIN MUTE** | Silence all outgoing PCM immediately; must be explicitly unmuted after connect/PANIC. |
| **Master output** | Set global output level; gain changes are smoothed over short ramps. |

Start modes: `replace` fades out active voices according to `transition_s` (default **2.5 s**) or 5 ms for the Cue's `replace_style=cut`. Incoming sound uses its own fade-in at least as long as the chosen replacement fade, **capped at half the new clip duration** (short effects remain audible). `layer` mixes with the currently playing sounds. `queue` schedules after all currently/pending sounds end and then waits its own pre-wait. CUT GO always forces immediate replacement.

`fade_in_s` and `fade_out_s` are **volume gain envelopes** of each source. They are separate from the **direction** envelope and separate from the `transition_s` replacement fade. The `pre_wait_s` is applied **before** a newly triggered clip starts; it is *not* made shorter by the fade-in. `post_wait_s` is interpreted by the outgoing cue's auto-next rule:

- `manual`: only the operator triggers the next cue; post-wait is ignored.
- `auto_continue`: next cue is scheduled at **this cue's actual audio start** + `post_wait_s` + **next cue's** `pre_wait_s`, so clips may overlap.
- `auto_follow`: next cue is scheduled at **this cue's natural or previously determined end** + `post_wait_s` + **next cue's** `pre_wait_s`. A natural fade-out fits inside that clip and does **not** subtract time from the intentional gap. Replacing voices can overlap; cue fades are not a separate additional interval.

There is no automatic synchronization with a human script page, only the manually selected cue order and explicit auto rules. A sound designer should set those parameters for each script cue.

## 5. Design spatial direction and motion

### Cue base angle + free keyframes

Choose **Free keyframes** and drag points on the envelope: X is **clip elapsed seconds**, Y is **relative angular offset**, in signed degrees. For an effect that starts at 270° (left) and moves clockwise to 90° (right) over 4 seconds, set a `position_deg = 270.00` and keyframes `(0s, 0°) → (4s, +180°)`; the final bearing is `(270+180) % 360 = 90°`. If you want the opposite direction, use `−180°`. Keyframe offsets are **not forced to take the shortest angular path**; an offset of `+360°` makes an entire clockwise revolution. The inspector's cyan pointer marks the stored base angle and amber pointer the composed preview including the global controls.

### Direction ADSR (not volume ADSR)

Choose **ADSR direction offset** per Cue. Its attack ramps from **0° offset → peak offset**, decay ramps **peak → sustain offset**, sustain holds until the last release interval, and release ramps **sustain → final offset**. Durations for attack/decay/release are seconds and sustain is automatically the remaining portion of the audio clip. If attack+decay+release exceeds clip length, the stages are proportionally compressed. Offset values can be negative and can exceed ±360° up to the editor's configured limits for multi-revolution motions.

### Global show-wide direction envelope

Enable the **Global show-wide envelope** in the left sidebar. Add points `(show time seconds, angular offset degrees)`; this track starts at the **first scheduled audio start after ARM / new show** and is linearly interpolated. The **Global rotation** number is a separate live-adjustable scalar applied to every playing source. The final software direction, measured clockwise, is:

```text
θ_output(t, T_show) = wrap360(
    θ_cue_base + cue_direction_offset(t) + global_rotation
    + global_show_offset(T_show)  # 0 when disabled
)
```

Edits to position/gain/direction ADSR/free keyframes or global motion propagate to currently playing audio after autosave, normally around 300 ms plus UI/device scheduling. The reference mixer smooths gain/direction at block boundaries to avoid sudden jumps, but **it does not guarantee glitch-free live edits**. Editing the stage speaker routing is blocked while connected and unmuted. If a show is armed and an auto chain has already queued several voices, changes to their direction/gain apply, but their already-scheduled start frames, sound buffer and cutoff times remain fixed.

## 6. Local projects and file persistence

```text
~/.spatialstage/projects/<12-character-show-ID>/
  project.json            # cue ordering / audio references / speakers / global & per-cue envelopes
  media/                  # copied and renamed audio source assets
  events.jsonl            # ONLY if explicit SPATIALSTAGE_DIAGNOSTICS=1
```

**Export show ZIP** packages that show's data and media; the app doesn't upload your project to GitHub, iCloud or another server. Cue list changes are automatically saved with an atomic project.json replacement. Existing v0.1 JSON generally loads with new defaults; the next save writes `schema_version = 2`. Old `~/.stagespatialcue/projects` are **not automatically migrated** into the new default directory; copy them manually while SpatialStage is shut down if you want to reuse old projects. Preserve project IDs and media subfolders.

`.gitignore` excludes local audio, ZIP exports, `.venv`, secrets and runtime project stores. Do **not** commit participant names, recordings or copyrighted audio to the public repository.

## 7. Reliability and current limitations

- **Requires hardware tests before an actual rehearsal**. CI tests validate Python logic and API schemas, not physical Mac+console routing, speaker pressure, sample clock drift or actor perception.
- The current PortAudio callback takes Python locks and allocates NumPy buffers; this is not compliant with hard real-time audio callback design. Dropouts may occur. For performance deployment, port the mixer and command queue to **JUCE/CoreAudio C++**, with preallocated signal paths and lock-free control messages.
- Measured latency calibration (including buffer/console/amplifier/air propagation) is **not implemented**. Theoretical center-point extra delay is *preview only*. Speaker trim is a manually applied parameter; an SPL meter is needed to determine safe actual gains.
- One virtual source is rendered from the reference center, not independently for every moving actor. Off-center listener localization is neither uniform nor guaranteed.
- Speaker frequency response, directivity, reflections, bass management, speed-of-sound changes, playback-device clock domains and hearing safety are not modeled. Do not infer ADHD effects from the software's direction degrees.
- No experiment participant logs are collected. Optional operator diagnostics are disabled by default.
- No OSC/MIDI, DAW timeline, looping, waveform cuts, external timecode, real-time mic input, HRTF or 3D height yet.

## 8. Project layout, testing and contribution

```text
stagespatialcue/                 # internal Python module retained for v0.1 project compatibility
  models.py                     # Pydantic project/cue/speaker schemas
  spatial.py                    # stage XY/polar conversion + VBAP + direction ADSR
  mixer.py                      # frame mixer; GO transitions, global motion, live updates
  audio.py                      # decode/cache, device selection, preflight, stage controller
  server.py                     # FastAPI localhost endpoints
  storage.py                    # atomic project JSON, import/export
  static/index.html, app.js, style.css
scripts/seed_demo.py            # synthetic demo audio
scripts/browser_smoke.py        # developer-only browser mock/testing example
scripts/                         # historical UI migration scripts (not needed at runtime)
tests/                           # automated DSP/API checks
.github/workflows/ci.yml
run_mac.command
```

```bash
python -m pytest -q
node --check stagespatialcue/static/app.js  # optional Node syntax check
```

**Development path:** v0.2 geometry, envelopes and live edits → in-situ speaker/output soundcheck → UX improvements, stage-safe sound level controls and playback snapshots → native audio engine → reproducible show release and hardware acceptance testing.

**License:** MIT. Independent tool; not affiliated with QLab.