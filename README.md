# StageSpatialCue

**Local-first 4-channel theatre spatial sound cue controller for macOS**

**Status: v0.1 rehearsal / research prototype. Not certified for a public performance, hearing-safety use, or clinical research.** Real four-channel CoreAudio output must be tested on the target Mac, mixer and sound interface. The Python callback is not hard-real-time; it can underrun under load. A native audio engine is the recommended next step before production.

StageSpatialCue combines a cue-stack operator console with 2D vector-base amplitude panning (VBAP), a draggable clockwise 360° direction dial, a per-cue modulation envelope and independent cue execution modes. The interface is a local browser page; audio is mixed by a separate Python engine and sent directly to four hardware output channels through PortAudio/CoreAudio.

## Features in this MVP

| Feature | Status | Notes |
|---|---|---|
| 4 discrete audio outputs | Implemented, hardware-unverified | Select a CoreAudio/PortAudio device with at least 4 output channels; 48 kHz, float32, 512 frames |
| Independent spatial bearing | Implemented | 0° = 12 o'clock, 90° = right, 180° = behind/bottom, 270° = left, 0.01° control precision |
| Irregular 4-speaker layout | Implemented | 4 bearing angles, 4 distances, 4 output channel maps, speaker trim; geometry validation |
| Distance compensation | Optional experimental | Simple linear-distance amplitude adjustment relative to median speaker distance; defaults off |
| Draggable spatial dial | Implemented | Click/drag and two-decimal numeric input |
| Modulation envelope | Implemented | Per-cue piecewise-linear **unwrapped angle offsets** in seconds, including multiple full turns |
| GO / STOP / SKIP / PANIC | Implemented | Keyboard controls and UI; startup/reconnect defaults to main mute |
| Replace / layer / wait start modes | Implemented | Replace crossfades existing voices; layer overlaps; wait queues after active voices finish |
| Fade in / fade out / transitions | Implemented | Independent per cue, plus de-click stop; smooth sine-based intrinsic fades |
| Manual / auto-continue / auto-follow | Implemented | Post-wait relative to cue start or end, respectively |
| Global direction steering | Implemented, elementary | Live rotation offset added to all current spatial voices; scene/global modulation is future work |
| Audio folder auto-import | Implemented | Browser folder upload; sequence sorted by numerical filename prefix |
| Local multi-project save/export | Implemented | Independent show JSON/media folders; ZIP export including logs |
| Device selection | Partial | Select real 4-output device; input device preference displayed/saved but **not routed** |
| Per-channel meter/test | Implemented, hardware-unverified | Quiet 440 Hz tone to one specified channel; software output meters |
| Experiment event logging | Basic | Operator and audio-frame events in `events.jsonl`; not latency-calibrated or participant-linked |
| Looping, audio trim, live mic routing, timecode, OSC/MIDI | Not implemented | Future milestones |
| Long-file streaming, hard real-time guarantees, peak limiter | Not implemented | Predecoded mono prototype with basic output clipping |

## Quick start on Mac

A Mac with **macOS, Python 3.11–3.13, Homebrew, and a USB/Thunderbolt interface that offers at least four independently addressable outputs** is required for physical four-channel playback. You may still run the editor without an audio interface.

```bash
# Install dependencies (if you already have suitable Python, skip python@3.12)
brew install python@3.12 portaudio libsndfile ffmpeg

# From the repository directory
cd StageSpatialCue
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

# Optional: populate a synthetic 3-cue demo show
python scripts/seed_demo.py

# Run the local controller
stagespatialcue
```

Open **http://127.0.0.1:8765** in Chrome. Use the **Import folder** control for directory selection. A double-clickable `run_mac.command` is also provided; it attempts to use your system `python3` and installs dependencies into `.venv`.

To quit, return to Terminal and press `Ctrl+C`. The local service listens only on `127.0.0.1`, not on the LAN. Projects are stored by default under `~/.stagespatialcue/projects/` (outside the source directory).

On a development or demo machine without 4-output hardware, the editor and project management still work; playback remains unavailable until an appropriate interface is connected.

### Audio hardware wiring (IMPORTANT)

```text
Mac USB-C / Thunderbolt
       │
       ▼
4-or-more-output USB audio interface (CoreAudio)
       ├── OUT 1 ──► mixing console input 1 ──► dedicated out / aux / matrix 1 ──► SPK 1
       ├── OUT 2 ──► mixing console input 2 ──► dedicated out / aux / matrix 2 ──► SPK 2
       ├── OUT 3 ──► mixing console input 3 ──► dedicated out / aux / matrix 3 ──► SPK 3
       └── OUT 4 ──► mixing console input 4 ──► dedicated out / aux / matrix 4 ──► SPK 4
```

The console **must retain four independent signal paths**. If its four mono input channels are mixed into a standard stereo L/R main bus, directional output will collapse to two channels. Most laptop headphone connectors are two-channel only; a 4×4 sound card, or a mixer that actually enumerates as a 4-channel USB audio output device, is required. Some digital desks expose stereo USB returns only; check the console's USB driver/routing matrix before rehearsal.

1. Connect the hardware and power it on; keep PA amps/console masters down.
2. Open **Applications → Utilities → Audio MIDI Setup**. Select the interface, set **48,000 Hz** when supported, and check that four output channels exist. You can inspect/configure the speaker/channel mapping here; the StageSpatialCue application also maps each speaker to output 1–4.
3. On the physical console, create a discrete one-to-one signal path for each channel. Do **not** simply pan the four inputs across a stereo bus.
4. Start StageSpatialCue; select the output device (minimum `4 out`), click **Connect audio**. This resets **MAIN MUTE to ON** by design.
5. At safe console levels, cautiously unmute; use **Test CH** for channels 1, 2, 3 and 4. The one-second calibration tone is deliberately low level but is **not** a calibrated SPL signal.
6. Enter/verify each speaker bearing, distance and physical output assignment under **Stage setup**.
7. Import audio, click **Preflight**, rehearse all cue overlaps with the full speaker system, verify no unexpectedly hot peak and check xrun counter.
8. Set the correct next cue with **ARM SELECTED** before the show begins. Keep a separate emergency stop accessible at the console.

Apple's official multichannel configuration guide: <https://support.apple.com/guide/audio-midi-setup/set-external-speakers-stereo-surround-sound-ams1005/mac>

## Cue audio folders and filenames

Use a numbered prefix. The folder's name is not part of the current cue identity; imported filenames are stored alongside the copied project media.

```text
Show_A_Act_1/
  001_Opening_Ambience.wav
  002_Left_Whisper.wav
  003_Back_Rumble.wav
  004_Orbit_Cue.flac
  005_Transition_to_Scene_2.mp3
```

Accepted extensions: `.wav`, `.aif`, `.aiff`, `.flac`, `.ogg`, `.mp3`, `.m4a`, `.aac`. WAV/AIFF/FLAC generally decode with `libsndfile`; installing `ffmpeg` adds fallback support for compressed formats. **48 kHz PCM WAV is the strongly recommended show-prep format**, especially for repeatable boundaries and lower decoder unpredictability. Stereo/multichannel source audio is intentionally downmixed to mono before VBAP. If you need stereo beds to stay stereo or already-spatial multichannel masters, this requires a separate mode not present in v0.1.

`001_Title.wav` / `001-Title.wav` / `001 Title.wav` all work. Unnumbered files are imported after numbered ones and can be reordered using the ↑ / ↓ controls in the Cue Stack. The uploader copies media **into the project directory**, rather than relying on an external folder remaining mounted. Maximum 250 files per batch, 150 MiB per uploaded file; decoding has a 30-minute per-clip limit and a 700 MiB decoded cache. Large shows currently need a streaming engine.

## Operating the cue stack

**Operator keys (when not editing an input field)**

| Key | Action |
|---|---|
| `Space` or click GO | Trigger the next armed cue (or a chain) |
| `S` or STOP | Begin a short 40 ms de-click fade on all currently playing voices; cancels future voices |
| `Alt+↓` or SKIP | Move the next-cue pointer forward **without playing audio** |
| `Shift+Esc` or PANIC | Immediately kill all voices and set master mute ON |
| ARM SELECTED | Set the next GO cue to the selected row (does not stop active playback) |

**Each cue has these settings:**

- `position_deg`: static bearing, 0–359.99°, clockwise from 12 o'clock.
- `gain_db`: cue volume level (-90 to +12 dB; use conservative gain staging).
- `fade_in_s`: sine attack from silence starting at the cue's first sample.
- `fade_out_s`: sine release to silence over the last portion of the **natural clip duration**.
- `transition_s`: when this cue is `replace`, release previous active cues over this duration to prevent abrupt discontinuities; the new cue starts immediately (after its pre-wait) and overlaps the outgoing tail. This is **not** the new cue's fade-in.
- `start_mode`: `replace` (fade out all earlier playing cues), `layer` (mix together), or `queue` (start only after **all current/scheduled voices** end).
- `pre_wait_s`: extra wait after GO, or after the queue condition, before the cue begins. **It is not an absolute gap measured from the prior cue's end** if manually triggered while another cue is still playing.
- `continue_mode`: `manual` (next cue needs another GO); `auto_continue` (auto-start next cue after `post_wait_s` measured from this cue's start); `auto_follow` (auto-start next cue after `post_wait_s` measured from this cue's natural/planned end).
- `post_wait_s`: only used for auto modes. It is ignored for `manual`.
- `modulation`: elapsed time in seconds plus a **relative unwrapped bearing offset**. Values beyond ±360 can represent complete revolutions.

**Examples**

- A normal scene transition: Cue A currently playing. Cue B `replace`, transition 1.5 s, fade-in 1.5 s → both overlap while A fades down and B fades up.
- Whisper added during music: Cue B `layer`, fade-in 0.2 s → Whisper plays together with music; music remains active.
- Door cue after rain ends: Cue B `queue`, pre-wait 0.5 s → Door waits for the last playing cue to finish and starts 0.5 s later.
- Auto sequence: Cue A `auto_follow`, post-wait 1 s → Cue B triggers 1 s after A's end; Cue B's pre-wait is added.
- Automated overlap: Cue A `auto_continue`, post-wait 2 s → Cue B triggers 2 s after A's start, whether A has ended or not (B's own start mode can still replace/wait).

**Limits:** Auto chains are pre-scheduled when GO is pressed; editing an already scheduled voice does not change its original playback settings. Master rotation does affect active voices. The voice starts are quantized to actual buffer rendering; real analog output timing needs loopback measurement.

## 360° spatial model

Speaker labels and four channel numbers are **independent**. Speakers are described by bearing angles relative to a defined center point and distances in meters from that same point. The default is:

| Speaker | Bearing | Distance | Physical output |
|---|---:|---:|---:|
| Front left | 315° | 3 m | 1 |
| Front right | 45° | 3 m | 2 |
| Rear right | 135° | 3 m | 3 |
| Rear left | 225° | 3 m | 4 |

Angles **must enclose the reference point** (no consecutive empty gap of 180° or more). For arbitrary stages, enter each measured bearing directly. **Four distances alone cannot reconstruct the layout.** Alternatively, if you have XY coordinates, convert with `bearing = (atan2(x,y) × 180/π + 360) % 360`, defining positive X toward the stage's right and positive Y toward 12 o'clock.

Given a requested bearing θ, VBAP finds the two enclosing loudspeakers and calculates nonnegative gains, then normalizes their squared sum to one. It is an **amplitude panning approximation** and does not synthesize a real point source at a chosen location. It is not a binaural HRTF headphone renderer, wave-field synthesis, nor a model of wall reflections or a moving human subject. Four-channel equal-power VBAP does not guarantee identical loudness at every angle, particularly at low frequencies.

The optional distance multiplier is `distance_i / median(distance)`, applied to each active speaker's gain. This crudely compensates for 1/r loss at **one reference point**, but can create extra peaks. It defaults OFF; prefer physical SPL measurement, channel trims and a speaker-system technician for actual calibration. No per-channel delay compensation is currently applied.

For cue modulation, points are `[(elapsed_s, offset_deg), ...]`, linearly interpolated *without angle wrapping*. For example:

- Base bearing **350°** with offsets `0° at 0 s` and `20° at 4 s` sweeps across 0° to finish at **10°**.
- Base bearing **90°** with offsets `0° at 0 s` and `360° at 8 s` makes one full clockwise circle.
- Multiple revolutions can be typed numerically as offsets such as `+720°`. The graph drag area is currently limited to `-360° … +360°`, while numeric editing supports `-2160° … +2160°`.

The **Global rotation** control sums a signed angle to every current cue's `base position + cue modulation`. It is a deliberately simple global steering layer, not a competing timeline or automatic actor tracking solution.

## Save, export, and event logging

Each show lives under:

```text
~/.stagespatialcue/projects/<project-id>/
  project.json       # human-readable cue definitions, geometry, angles
  media/
    001_Opening_Ambience.wav
    002_Left_Whisper.wav
  events.jsonl       # non-identifying operator and engine frame events
```

Cue edits are automatically persisted to `project.json` via atomic replace. `Export show ZIP` creates a ZIP including JSON, audio and logged events. Restoring a show currently requires copying an exported project folder back under the data root; an in-app import is planned. To change the data location:

```bash
STAGE_SPATIAL_DATA="$HOME/Documents/StageSpatialProjects" stagespatialcue
```

`events.jsonl` contains approximate UTC receipt timestamps and frame numbers from the 48 kHz engine clock. Logged events include arm, GO, skip, STOP, panic, mute changes, cue audio starts/ends and import. **Frame timestamps indicate software rendering relative to the current stream, not measured acoustic arrival time**; they are unsuitable as millisecond-accurate participant-exposure ground truth until device latency has been calibrated. This MVP does not store names, ADHD diagnoses, study scores or microphone recordings.

## Validation & development

```bash
python -m pytest -q
python -m compileall -q stagespatialcue
```

Hardware smoke-test checklist:

1. CoreAudio lists the chosen interface with `max_output_channels >= 4`; startup/reconnect is muted.
2. Each test channel goes to **only** its intended speaker, not to a console stereo bus or duplicated PA send.
3. 0/90/180/270° virtual bearings sweep clockwise in the expected stage orientation.
4. 350→10° is a short clockwise sweep with correct unwrap; `0→360°` is one revolution.
5. `replace`, `layer`, `queue`, auto-follow, auto-continue and post-wait behave correctly under a full 20–30 minute trial.
6. Stop/replace near a zero crossing and a full-scale transient are auditioned for audible clicks.
7. No xrun, clipped block, memory exhaustion or late GO under the maximum expected number of simultaneously playing cues.
8. Stop/reconnect device, unplug/replug interface, switch sample rate, sleep/wake the Mac, refresh UI and restart server; test safe failure modes.
9. Measure sound level at all relevant participant locations using suitable instrumentation; do not expose participants until the study protocol is approved.
10. Keep a conventional mixer emergency mute; never rely solely on the browser's PANIC control.

## Known constraints / technical debt

- **Python + PortAudio callback is not hard-real-time.** Mixer math and Python locks can cause underruns; this version is for prototyping and rehearsal only. Upgrade to native JUCE C++ or Swift/CoreAudio (and lock-free command queues) for performance-grade reliability.
- The program decodes entire files to mono in RAM; no streaming for hour-long tracks, time stretching, loop regions, fades between arbitrary sections or output bus presets yet.
- A USB interface that *only* advertises two stereo channels may require driver/routing changes to expose four independent outputs. A four-speaker console alone does not mean the Mac can address four channels.
- 48 kHz is fixed for now. Some interfaces may reject it; matching hardware clock/source and sample rate is required.
- No automatic feedback prevention, calibrated peak limiter, hardware mute relay, redundancy computer, actor tracking or scientific participant scheduler.
- One local operator browser tab is assumed. Simultaneous multiple tabs can issue competing GO/ARM commands.
- HTTP on loopback is not a general remote-operator server. Do not expose port 8765 to a network or use port forwarding.
- `preflight` checks clips/cache/device selection but is not a complete live-show risk test.
- Audio output testing is **not performed** in this source-only build environment; the supplied editor has browser-level visual checks and unit/API tests, not a Mac PA certification.

## Suggested roadmap

1. **M1 — Hardware validation:** test on intended Mac/interface/mixer; four output channels, routing matrix, SPL calibration, drift/xruns, robust setup wizard.
2. **M2 — Cue design:** individual stop targets and groups, native waveform previews and trim, draggable keyframe editor with smoothing/easing, independent per-channel level meter and channel mute.
3. **M3 — Research mode:** scene-based global steering lanes, deterministic condition presets, counterbalanced trials, task IDs (pseudonymous), time-aligned response/event ingestion with explicit consent workflows.
4. **M4 — Production engine:** native low-latency CoreAudio/JUCE audio thread, file streaming, precache limits, sample-accurate scheduler, output limiter, channel delays, verified dropout handling, redundancy.
5. **M5 — Integrations:** OSC/MIDI/QLab interoperability, hardware GO button, rehearsal/live/locked modes and a signed macOS `.app` distribution.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md) for decisions, experiment-design safeguards and questions for the stage research team.

## Publish to GitHub

This archive is a **local git-ready repository**. The ChatGPT environment used to prepare it has no destination repository specified and no create-repository action, so a remote push has **not** been claimed.

```bash
cd StageSpatialCue
git status
git log -1 --oneline

# Install GitHub CLI if needed
brew install gh
gh auth login

# For this type of exploratory human-subjects work, consider private until reviewed
gh repo create StageSpatialCue --private --source . --remote origin --push

# Or, if you create a remote in the GitHub website first:
# git remote add origin git@github.com:YOUR_USERNAME/StageSpatialCue.git
# git push -u origin main
```

Do not commit participant identifiers, consent records, private sound files you lack redistribution rights for, or confidential study documents. The `.gitignore` intentionally ignores most standalone audio file extensions. Project data is kept outside the source repository.

## References

- [Zotter and Frank: Amplitude Panning Using Vector Bases](https://link.springer.com/chapter/10.1007/978-3-030-17207-7_3)
- [Apple: Set up external speakers for surround sound in Audio MIDI Setup](https://support.apple.com/guide/audio-midi-setup/set-external-speakers-stereo-surround-sound-ams1005/mac)
- [QLab 5: Cue sequences](https://reference.qlab.app/docs/v5/fundamentals/cue-sequences/), inspiration for but not an implementation of QLab's cue semantics

MIT license. No QLab affiliation. No patient information is required by StageSpatialCue.
