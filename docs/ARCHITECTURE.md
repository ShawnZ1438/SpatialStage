# SpatialStage v0.2 architecture and implementation notes

## Component graph

```text
Chrome/Safari UI  ── 127.0.0.1:8765 ── FastAPI
  Cue list                              │
  360° dial                             ├── ProjectStore → project.json + media/
  ADSR/keyframe inspector               └── StageController → Cue scheduler/decode cache
  global angular envelope                                          │
  output + master controls                                         └── Mixer
                                                                        ├── frame clock (48k)
                                                                        ├── per-voice fades / live edit smoothing
                                                                        ├── cue offsets, global offsets, rotation
                                                                        └── 2D VBAP → four channels
                                                                                     │
                                                        sounddevice PortAudio → CoreAudio device
                                                                                     │
                                                     console 4 independent buses → physical speakers
```

Software panning is centered at the fixed (0,0) stage reference point. Actor tracking and participant experimental logging are deliberately absent. The UI can run without attached output hardware, whereas GO is disallowed without a four-output device and deliberate unmute.

## Deterministic project model

`Project(schema_version=2)` includes speakers (canonical `angle_deg`, `distance_m`, `output_channel`, manual `trim_db`), `distance_compensation`, `global_rotation_deg`, an opt-in global keyframe envelope, and a Cue stack. The UI accepts `x_m/y_m` and converts to the canonical speaker polar representation with `angle=atan2(x,y)` clockwise from +Y. Saving old schema v1 projects sets schema v2 using new defaults. A valid configuration needs exactly four unique output channels and angular gaps under 180°.

`Cue` holds file references, per-cue source volume, fade-in/out, replace style (`crossfade/cut`) and `transition_s`, source start mode (`replace/layer/queue`), chain mode (`manual/auto_continue/auto_follow`), pre/post waits, base bearing and either free angular keyframes or direction ADSR. Angular offsets may be unwrapped (e.g., +360 is a clockwise revolution). The engine currently downmixes every decoded clip to mono before panning. `stage.sync(project)` applies current cue direction/gain/curve to existing Voice references by `cue.id`; it does not reload PCM or reschedule already planned start/stop frames.

## Scheduler times and transitions

`Mixer.frame` increments per callback; cue voice `start_frame`, `end_frame`, and optional stop fade are measured in its sample domain, NOT acoustic output-time timestamps.

- FADE GO: respects `start_mode`, `pre_wait_s`, per-Cue `replace_style` and `transition_s`. Replacing fades old audio over the transition, the new audio fades in with its own duration and a transition ramp capped at half the new clip length. Layer preserves other voices. Queue waits for existing voices, including pending ones.
- CUT GO: `force_cut=True`, which overrides queue/layer/pre_wait, replaces active voices with 5ms de-click, cancels pending voices and only triggers one new Cue (doesn't auto follow the chain).
- STOP: short soft stop, cancels pending voices; PANIC kills voices and applies main mute instantly.
- `auto_continue`: anchor for next cue is outgoing voice's start frame + `post_wait_s`; `auto_follow`: outgoing voice's end frame + post-wait; next cue then adds its own pre-wait. Natural clip fade-in/out are internal and not subtracted from the intentional gap.
- Global show keyframe clock initializes at first scheduled clip start after arm/new show; live rotation scalar is independent.

## Direction DSP

At clip time `t` and show time `T`, we compute

```
theta = wrap360(cue.position_deg
              + cue_direction_offset(t)
              + project.global_rotation_deg
              + project.global_show_offset(T))
```

For cue ADSR, the angular offset follows (attack: 0→peak; decay: peak→sustain; hold; release: sustain→release final), proportional-compressing stages if A+D+R exceeds clip duration. In free keyframe mode, linear interpolation is on unwrapped angular offsets. Show envelope uses the same keyframe interpolation with `T`. The currently requested direction is then mapped to adjacent speaker gains by 2D normalized VBAP; manually entered trims and optional approximate distance gain compensation are applied afterward. Because distance trim can affect normalization and perceived loudness, no objective equal-loudness guarantee is made.

Stage calibration preview uses geometric formulas (speed of sound ~343 m/s at 20°C), *but does not apply delay compensation and does not measure actual latency or SPL*. The theoretical extra delay for nearer speakers is `(max(d)-d)/343` seconds. This figure could be used as a future DSP alignment control once actual delays have been measured.

## Device, data and operation boundaries

- A physical ≥4-channel CoreAudio device is mandatory for GO. Mixer starts muted, master defaults to -18 dB. A tone test exercises only one software output at a time.
- The server binds on 127.0.0.1 and uses loopback Host and browser Origin constraints; do not expose its endpoints to other hosts or port-forward it.
- Operator commands execute on HTTP threads. `ProjectStore` writes atomic JSON via replace and copies media to per-project folders. Project exports include media. No participant data is collected. Optional operator-only JSONL diagnostic events can be enabled by environment flag.
- `StageController.can_update()` rejects stage speaker geometry or physical channel reconfiguration when a connected stream is unmuted; only soft cue settings may update live.
- Cue decodes happen before scheduling, with 30-minute clip cap and a 700 MiB cache; preflight checks files and whether a four-output device was connected.

## Why the current audio engine is not production-safe

Python callback explicitly takes a re-entrant lock, creates NumPy arrays each render block, and merges control/audio state. PortAudio recommends the opposite for a real-time callback: **no blocking locks, memory allocation, file I/O or other unpredictable operations**. A heavy CPU load, concurrent save, decoder miss or a bug can cause audible underruns. `xruns` and `peak_over_count` are only software indicators; they do not measure actual acoustic output or peak SPL.

**Native transition roadmap:** move the mixer into JUCE/C++ or a carefully designed CoreAudio extension; preallocate voice buffers and channel matrices; use lock-free control events; preflight/decode on workers; add output loss/reconnect and redundant mute fail-safes, latency measurement, gain ceilings and hardware acceptance. Then consider multi-actor spatialization limitations, playback-device drift, cue snapshots and richer envelopes.

## Acceptance criteria before actor rehearsal

1. Physical device provides 4 separate outputs, with a diagram of USB bus and console routing.
2. CH1→L, CH2→R, CH3→RR, CH4→RL (or explicitly documented permutation) verified at safe volume with solo tones.
3. Local coordinate reference arrow/tape fixed, X/Y for each speaker measured.
4. Reference-center gain trims determined with a calibrated meter, safe maximum level established by production sound team.
5. GO/STOP/PANIC, global motion, fade/cut, file swap and recovery tested with actors absent.
6. A stress run at representative polyphony passes without measured dropouts/xruns; if it does not, **do not use v0.2 as the sole live audio controller**.
7. Non-center actor positions verified perceptually; no claim of uniform localization.

## Useful references

- Apple Audio MIDI Setup: https://support.apple.com/guide/audio-midi-setup/set-up-audio-devices-ams59f301fda/mac
- Speaker output mapping: https://support.apple.com/guide/audio-midi-setup/set-up-external-speakers-for-stereo-or-surround-sound-ams1005/mac
- Zotter & Frank, *Amplitude Panning Using Vector Bases*, 2019: https://link.springer.com/chapter/10.1007/978-3-030-17207-7_3
- PortAudio callback considerations: https://portaudio.com/docs/v19-doxydocs/writing_a_callback.html
