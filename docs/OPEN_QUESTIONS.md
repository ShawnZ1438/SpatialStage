# Confirmed and unresolved project decisions / 项目决策状态

## Confirmed (2026-10-20)

- No audience orientation. ADHD performers inside a roughly circular area are the only participants/listeners. They can move; all DSP initially references the stage center only.
- Fixed convention: 0° at 12 o'clock/top, 90° right, 180° down, 270° left, clockwise positive, 0.01° editing.
- Four angled corners, approximately 315° L, 45° R, 135° RR, 225° RL; all face the center. Physical speaker placements may be shifted to avoid edges.
- Device computer: Apple Silicon Mac. Console model currently unknown. Support 4+ output USB/Thunderbolt interfaces or compatible multichannel USB consoles.
- Two operator switch buttons: a configurable fade transition versus immediate direct switch (with a very short de-click safety ramp).
- Independent Cue volume fade-in, fade-out and **direction** modulation with ADSR or free keyframes; master-wide angular rotation plus optional global show envelope.
- Design-time and during-playback editing are allowed. Clicking a future Cue row edits it; ARM SELECTED changes the next-Cue pointer.
- Audio sources are numbered/prepared local effect files, not live microphones. Motion such as car left→right and clockwise revolutions are important.
- Do not collect research participant or experimental response records.
- Public GitHub destination: `https://github.com/ShawnZ1438/SpatialStage`.

## Unresolved — these are not blockers for v0.3 software exploration

| ID | Detail to confirm on-site | Current fallback |
|---|---|---|
| P1 | The four exact measured speaker X/Y coordinates (m), actor circular area radius and reference top arrow | Default symmetric 3m diagonal speakers; no real calibration claim |
| P2 | Exact mixing console, interface, cabling, 4-output CoreAudio route and physical patch chart | Output selector only accepts a device with ≥4 channels; no stereo downmix fallback |
| P3 | Measured speaker levels at reference center and actor walk-test locations | No measured SPL; manual per-speaker trim at 0dB; software master defaults −18dB and mute ON |
| P4 | Any measured per-channel latency and whether the hardware console can set isolated bus delays | Geometry delay remains preview-only; optional single-point XLR AutoCal measures relative arrival and can apply delay **after manual approval** (not hardware-verified) |
| P5 | Should CUT GO cancel a previously scheduled auto-next chain? | **Yes**: cut overrides queue/layer, cancels pending voices and fires one Cue; re-arm as necessary |
| P6 | If speaker geometry is changed mid-playback, should control surface allow it? | **No** while an output device is connected and unmuted |
| P7 | When should global envelope clock restart? | After new ARM with no voices, on first new GO audio start; selecting a Cue during active playback does not reset it |
| P8 | Long ambient looping and stereo bed preservation needed? | Not implemented; mostly short monoized effects |
| P9 | Should Cue switching interrupt all active sounds or only a chosen group? | Replace/CUT currently target all active and pending voices; no group bus control |
| P10 | Any actor head tracking, adaptive speaker correction or force-of-effect research protocol? | None in current scope; the tool cannot assert individual perceived angles |
| P11 | Required UX language, touch screen/remote MIDI controls and operator permissions? | English UI, bilingual documentation, local desktop browser |
| P12 | Native audio engine target/acceptance date for full performance use? | Python reference prototype only; production requires JUCE/CoreAudio redesign and testing |

## Not implemented intentionally

- No patient profile, ADHD diagnosis, clinical recommendations, or experimental logging.
- No assumption that walls, floor reflections, off-center hearing, near-field SPL or actual physical loudspeaker directivity have been corrected.
- No automatically enabled measured-delay DSP or calibrated absolute sound pressure measurement from mere speaker position input. AutoCal v0.3 enables relative measured corrections only with manual approval, and does not measure dB SPL.

## AutoCal v0.3 scope/remaining decisions (2026-10-20)

- **Confirmed:** 1 measurement at stage center; `balanced` mode (with one point, center-only); XLR input through audio interface; experimental EQ explicitly OFF; persistence, result plots, explicit APPLY approval before processing output.
- **Still TBD (hardware):** exact XLR measurement mic, preamp/interface models, matching input/output hardware clocks, four console bus mappings, measured physical stage center, speaker coordinates, output gain ceiling, on-site acceptance criteria.
- **Future only:** 5/9-point area coverage, multiple mic spatial weighting, SPL calibration, verified phase/polarity check, hardware clock drift checks, adaptive EQ. None implemented or implicitly enabled.
