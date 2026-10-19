# Architecture and decision log

## Design intent

The tool is intentionally split into (A) a **web interaction surface**, (B) a persistent **show model and operator scheduler**, and (C) the **4-channel audio renderer**. A browser audio-only prototype was avoided because four independent CoreAudio routes and repeatable device configuration are essential to this project. The API server remains local, the media is copied to the project data directory, and the output engine does not depend on browser tab audio output.

```
Browser /static/app.js
    ├── cue stack & keyboard controls
    ├── polar source dial / cue envelope editing
    ├── speaker calibration / output and input preferences
    └── REST calls + status polling
             │ localhost 127.0.0.1:8765
             ▼
FastAPI /server.py
    ├── ProjectStore /storage.py ── project.json + media/ + events.jsonl
    └── StageController /audio.py
             ├── decode cache (48 kHz mono float32, 700 MiB)
             ├── frame-anchored auto chains / manual GO
             └── Mixer /mixer.py
                    ├── spatial.vbap_gains(...)
                    ├── per-voice attack/release/crossfade
                    ├── master gain/mute/output peak counter
                    └── sounddevice / PortAudio / CoreAudio
                               └── OUT 1–4 ── physical console ── speakers
```

## Timing ownership

The mixer's sample clock (`frame`) is incremented in the 48 kHz PortAudio callback. Cue voices carry `start_frame`, `end_frame` and optional stop-fade information. The control thread schedules voices; the callback renders frames. The current callback uses a Python re-entrant mutex protecting `voices` and `project`, which makes it **not** a hard-real-time architecture. File decoding happens before the new voices are queued. A native successor should use a lock-free single-producer/single-consumer command queue and a preallocated audio graph, with no allocation, file I/O, locks or logging from the render thread.

There are two kinds of events: `operator_go` (message received via HTTP) and `cue_audio_start` (scheduled voice enters a rendered output buffer). Their timestamps are not the same as actual measured sound at the performer. The difference incorporates UI/network event latency, audio device output buffering, mixer and speaker/air travel delays. Hardware loopback and SPL testing are required for research-grade timings.

## Spatialization

The reference plane uses bearing `atan2(x,y)`, clockwise positive. `position` is source direction, not a listener head azimuth or Cartesian object location. Speaker pairs are sorted by actual bearing; the two that surround the desired direction are mixed with positive constant-power VBAP gains. Optional speaker-specific distance and gain trim multiply those coefficients. We deliberately do not include reverberation, early reflections, HRTF, Doppler, listener-specific head tracking or time-delay steering in v0.1.

**Important limitation:** the system assumes a reference point at the actor/listener center for sound-field planning. If multiple ADHD participants move independently around the stage, a single VBAP output cannot guarantee the same perceived direction for every person. Future acoustic calibration needs listener position and potentially multi-position measurements, not simply speaker distances.

### Modulation semantics

Effective angle at time `t`:

```
θ_effective(t) = wrap360(θ_cue + offset_cue(t) + rotation_global)
```

`offset_cue(t)` uses linear interpolation over unwrapped offset keys. A 360° signed offset means a full revolution, not a return to the same source bearing by the shortest path. Cue updates affect new voices; project-level rotation currently influences existing voices.

## Reliability constraints

- Data model validation rejects overlapping 1–4 hardware channel assignments and speaker gaps >=180°.
- Device connection requires >=4 discrete output channels, 48 kHz float32 support and forced mute.
- Default master volume is -18 dB and startup/reconnection is muted.
- PANIC discards voices and sets mute; STOP fades current voices with a short ramp.
- Project JSON writes use a temporary file and atomic replace.
- Media is copied into per-project storage, escaping paths are rejected, server is loopback-bound and browser Origin is restricted.
- Safety controls and PortAudio capability checks are **insufficient** for certified live-show deployment. Add C++ audio thread, fail-quiet watchdog, redundant controls and systematic fault injection.

## Proposed package boundaries for production

| Component | v0.1 | Planned production replacement |
|---|---|---|
| UI | Vanilla browser JS | Electron/Tauri or native SwiftUI wrapper around local UI |
| Cue persistence | JSON files | Schema-versioned SQLite with backup/migration and transactional edit history |
| Spatial audio | Python NumPy 2D VBAP | JUCE/Swift DSP graph with per-sample smooth interpolation and multi-source groups |
| Audio output | PortAudio CoreAudio backend | CoreAudio via JUCE with explicit device/channel matrix |
| Timing & sync | Callback frame counter | Buffer-scheduled real-time clock, timecode/MTC/OSC, measured latency |
| Research logs | JSONL | Signed experiment manifest, protocol IDs, synchronized cue and response timestamps |

## Development acceptance checkpoints

M1 exit criteria: a real Mac and 4+ output interface, correct isolation on each output, repeatable 48 kHz operation, 0 XRUNs during an agreed maximum-load rehearsal, physical mute emergency access, and documented acoustic calibration at each planned participant position. Do not claim these exit criteria are already met by tests in CI.
