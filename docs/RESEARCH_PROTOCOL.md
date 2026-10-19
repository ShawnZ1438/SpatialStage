# Research-use and theatre-workflow planning notes

The stated scientific objective is to study how spatial and dynamically moving sound affects ADHD participants during theatre performance. This document is **not** an experimental protocol or a clinical claim. It highlights factors that could invalidate interpretation if the engineering system fails to control them.

## What the technology can operationalize

For each cue, the system can record an intended source bearing (relative to a chosen stage reference), its envelope of angular offsets over elapsed time, trigger mode, nominal gain and fade shape. Stage projects can be cloned into separately named conditions. The current log stores a sample-frame marker for audio rendering, but **not** a measured participant sound exposure.

The technology cannot infer an individual actor's ADHD symptoms, attention level, cognitive state, emotional response or auditory acuity. It cannot know precise listener-facing source azimuth without measuring where they stand and how they orient their head.

## Design dimensions to decide with the research team

1. **Unit of observation:** a rehearsing actor with ADHD, an audience member with ADHD, or both? Their listening position and task are very different.
2. **Reference frame:** does 0° represent the front of the stage, the audience, or the facing direction of each performer?
3. **Study condition:** static versus moving sound, 2D bearing, modulation speed, trajectory, salience, loudness, soundtrack content, or some combination?
4. **Control:** non-spatial mono/identical sound, static four-channel VBAP, or no sound? Avoid conflating motion with changes in perceived loudness.
5. **Counterbalancing:** randomize or counterbalance cue condition order, actor scripts and scene sequence to limit learning/fatigue effects.
6. **Exposure and hearing comfort:** follow institutional safety and research policies, obtain consent, establish target SPL limits, measure peaks at several positions, permit immediate opt-out and add an operator-controlled emergency mute.
7. **Participant response:** decide whether collecting survey responses, performance timing, motion data, physiological measures or observations; store these separately from audio controller data with suitable permissions.
8. **Actor geometry:** note actor location/heading per scene; stage-centered VBAP cannot ensure one exact direction at multiple moving listeners.
9. **Session manifest:** record sound file checksum/version, project JSON revision, speaker placements, console patch, sample rate, master level, trial ordering and operator identity/role (without attaching personal diagnosis to cue logs).
10. **Latency validation:** measure software event to analog signal with loopback and analog SPL arrival, plus where xrun/dropouts occur. GUI rendering time is not physical cue timing.

If this is a University-affiliated human-participant study, seek the relevant research ethics/IRB determination **before** collecting participant responses or health-related information. Minimize data collection and do not interpret the system's calculated azimuth as verified perceptual localization.

## Suggested first pilot (engineering, not clinical study)

- Only staff or consenting adult pilot listeners, with a short non-study calibration run.
- Four physically patched independent loudspeakers and a measured stage reference point.
- Repeatable 4–6 second sound samples at carefully controlled amplitude.
- Conditions: one stationary front sound; one stationary side sound; one slow 0→360° motion; one rapid 0→360° motion, if approved for participant comfort.
- Record output-channel levels, response timing and whether the correct speaker pairs activate.
- Compare geometric gain design against measured acoustic output and listener localization ratings before defining the actual research experiment.

## Unresolved requirements tracker

| ID | Decision needed | Why it matters |
|---|---|---|
| R01 | Speaker positions: center distance + angle, or Cartesian `(x,y)`? | Calibration and panning model |
| R02 | Does 0° face audience, back of stage, or actor orientation? | Scientific comparison and UI meaning |
| R03 | Is the target listener stationary? One actor or several actors? | Accuracy claims |
| R04 | Exact interface and console USB/routing capabilities? | Four independent hardware buses |
| R05 | Should replace stop all playing voices or named tracks/groups only? | Cue behavior |
| R06 | Should manual GO use previous end-time gap, pre-wait, or both? | Scheduling semantics |
| R07 | Envelope: absolute angle, relative angle, speed, or easing? | Authoring model |
| R08 | Global steering: fixed rotation, authored envelope, or live sensor-driven movement? | Layer hierarchy |
| R09 | Are cues long music, short effects, ambient loops, stereo masters or mono? | Streaming/loops and decoder design |
| R10 | Should live microphones be included or just file input + physical output device? | Feedback safety and I/O architecture |
| R11 | Need OSC/MIDI footswitch/timecode / QLab interoperability? | Operator interface |
| R12 | Is project data a researcher-only local record or needs session/export/participant linking? | Ethics and persistence |
| R13 | Are operators allowed to alter parameters live during a running cue? | Real-time control smoothness |
| R14 | Mac OS version, Apple Silicon vs Intel, output sample rate and device availability? | Deployment testing |
| R15 | Needed interface language(s) and whether cue names contain Chinese/English? | UI and file naming |
