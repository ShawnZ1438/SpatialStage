# Confirmed boundaries and unresolved decisions

## Confirmed — do not silently change

Actor-centered four speakers, no audience; actors move inside the perimeter. 0° up, clockwise; L/R/RR/RL default outputs1/2/3/4. Apple Silicon Mac, actual console/interface TBD. Prepared numbered local audio, no live microphone cue input. Cue-level and global angular envelopes, live cue editing, local projects. Two transition actions: configurable fade and de-click cut. No participant experiment logging. AutoCal remains exactly **one center point / balanced / XLR / EQ off**, and compensation needs human approval.

## Explicit current behavior (may be revised only deliberately)

- Zero-wait auto-continue siblings at the same start frame play as a group, despite default replace. Other replace cues stop all older voices, not only a selected sound layer.
- Selecting a row is not ARM; NEXT is stable by ID; deleting NEXT blocks GO until re-armed.
- MAIN MUTE is not pause: clocks and files progress. SKIP changes NEXT only. CUT GO plays one cue, not its automatic chain.
- Angular ADSR release is file-end-relative, not triggered by STOP. Global envelope includes silent gaps and mute time.
- Media replacement applies on next playback. Current playback is not hot-swapped or paused/resumed. Audio sources are downmixed to mono.
- Pending timing changes affect subsequent scheduling, not the already planned automatic chain.
- One browser editor owns a project at a time. Avoid edits during media import/replacement/project switching.
- ZIP export exists; safe ZIP restore/import does not. No hidden “complete all features” claim.

## Decisions needing the operator / creative team's input

| Topic | Question | Suggested next design, not approved |
|---|---|---|
| Replacement scope | Should car/footstep FX interrupt background ambience, or only previous FX? | Named playback groups, group STOP/replacement, simultaneous Group Cue |
| Pause and global clock | Should pausing freeze file playheads and show envelope? Does mute continue? | Separate PAUSE/RESUME from MUTE; explicit show-clock reset/freeze |
| Direction release | Should STOP trigger an angular release before sound stops? | Distinct key-off release, bounded by stop/fade duration |
| Spatial motion | Is a circular bearing sweep sufficient, or must a car follow a Cartesian path? | Bearing-first MVP; XY trajectories and distance gain require a separate perceptual design |
| Source format | Is mono spatialization adequate for all assets? | Optional stereo width/two-source mode, never silently repan original stereo |
| Editing reliability | Is more than one operator/window needed? Can active cues be protected? | Revision/ETag conflicts, transactional media edits, show lock, undo/version snapshots |
| Recovery | Must a replacement Mac restore a show from one file? | Validated ZIP import, media hashes, device-remap confirmation, muted recovery |
| Trigger safety | Are repeated deliberate GO presses common, or should accidental doubles be guarded? | Request IDs/server idempotency; optional guarded trigger, not arbitrary debounce swallowing intended cues |
| External control | Is keyboard sufficient, or are MIDI/OSC/foot pedals required? | Explicit configured mappings, transport priority and no unauthenticated LAN API |
| Levels and polyphony | Maximum concurrent voices and acoustic limits? | Metering/headroom policy, warning/limiter design and physical sound-level verification |

## Site information still TBD

Actual measured speaker X/Y and actor movement radius; console and sound interface model; four independent bus mapping; microphone model/preamp/input and whether phantom power is required; common playback/recording clock; channel gain and DSP settings; physical mute owner; acceptable test-sweep level and venue sound pressure limits. Software dBFS is not calibrated SPL, and one-point correction cannot optimize all moving positions.

## Engineering limits still open

Native audio engine / preallocated callback; reliable device IDs across reconnect; rolling decode streaming for long shows; slow decoder cancellation; hardware failover; aggregate-device drift; multi-tab conflict checks; import/replacement transactions; sample-accurate parameter automation; hardware round-trip latency measurements. AutoCal device-name checks cannot detect every external mixer gain/EQ change. Room reflections and speaker directivity exist even when omitted from the geometric model.
