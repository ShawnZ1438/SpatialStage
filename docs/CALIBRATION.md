# Physical four-speaker setup and center-point calibration / 四音箱实地标定

**Scope:** no audience; four speakers surround ADHD actors and point toward the **fixed stage reference center**. The actor may move inside the loudspeaker quadrilateral/circle. The software calculates a reference-center virtual-source mix, **not** a spatially uniform field across all actor positions. Measurement should be carried out by qualified sound staff with actors absent until safe levels are established.

## A. Record the geometry (required before using VBAP live)

1. Tape the center point `(0,0)` on the stage floor and a distinct **12 o'clock** arrow. +X goes right/3 o'clock; +Y up/12 o'clock.
2. For each speaker mark the center of its acoustic front face in the horizontal plane. Measure `(X,Y)` from the stage origin, in **metres**. Do not guess exact lengths from a diagram.
3. Aim each physical cabinet toward `(0,0)` and ensure actors can move without intersecting cables and stands.
4. In `Stage setup`, enter each `X/Y`, console output channel and speaker label. The software calculates `distance`, `bearing`, `face center bearing`, theoretical arrival time, distance-gain hint and extra-delay hint.
5. All four speakers should surround the center, so no angular gap can be 180° or larger.

| Output / label | X (m) | Y (m) | Calculated bearing | Center distance | Aimed toward center? |
|---|---|---|---|---|---|
| CH1 = L | TBD | TBD | ~315° | TBD | TBD |
| CH2 = R | TBD | TBD | ~45° | TBD | TBD |
| CH3 = RR | TBD | TBD | ~135° | TBD | TBD |
| CH4 = RL | TBD | TBD | ~225° | TBD | TBD |

**Distance data by itself cannot determine direction.** A measured X/Y pair or bearing+distance is required for every box. If loudspeakers are shifted backward to clear the edge of the circular acting area, update these actual measured coordinates instead of changing the software's 0° convention.

## B. Identify Mac → console routing (required before audible tests)

| Requested detail | Example / what to verify | Current state |
|---|---|---|
| Apple Silicon model + macOS version | M-series Mac; exact model and OS for driver checks | Apple Silicon confirmed; exact model TBD |
| Interface or mixer product | USB/Thunderbolt 4+ independently routable outputs | TBD |
| Physical 4-wire path | e.g., interface 1–4 → console line 1–4 → four isolated AUX/matrix buses | TBD |
| Sampling configuration | Prefer 48 kHz, float32/CoreAudio device compatible | Hardware unverified |
| Console routing | No 4→stereo collapse, no unexpected matrixing or mono summing | TBD |
| Mixer/amp/speaker trims | Output gains, powered speaker master setting, gain ceilings | TBD |

**Connection options**: a dedicated multi-output interface is easiest; a multichannel-USB console is valid if it exposes at least four independent outputs to CoreAudio and four separately routable physical outputs. HDMI/AirPlay/ordinary 2-channel USB audio is not by itself suitable. A multi-output aggregate device does not automatically provide a synchronized four-channel installation.

## C. Verify routing, then level matching (required)

1. Before connecting: mute console/amp, connect data and 4 independent output cables.
2. Open macOS `Audio MIDI Setup`, select compatible device, use 48 kHz if supported, and confirm actual number of output channels.
3. Launch SpatialStage, select the device and click `Connect audio`; master comes up muted and initially at −18 dB.
4. Reduce console/amp gain. Unmute intentionally, test **one channel at a time** with `Test CH` and trace software CH1..4 through console input LED, isolated bus and **one physically correct loudspeaker**. No two speakers should sound during a solo test.
5. Record actual measured SPL per speaker at the stage center, and verify a safe operating ceiling with the production sound lead; there are **no automatic SPL limits** in the app. One-second 440Hz sine is **for routing only**, not a sufficient broad-band calibration source.
6. For serious level matching, run an independently verified calibrated test signal (e.g., appropriately limited pink noise) with an SPL meter/measurement microphone, one channel at a time, same microphone location, same console gain conditions; choose manual `trim_db` adjustments from **real measured level differences**. Do not simply apply the mathematical suggested gain values.
7. Walk the actor's allowed positions around the center, confirm there are no unexpectedly loud hotspots or major dropouts, and re-check directional perception. A single center calibration does not make off-center localization uniform.
8. Store the speaker coordinates + channel mapping in the project's JSON and preserve the cable patch sheet.

## D. Time alignment is a *future* audio DSP feature

At ~20°C, air propagation is about 343 m/s. If CH1 is at 2 m and CH2 at 3 m, CH1 sound theoretically arrives roughly `2.92 ms` earlier at the center. A **candidate** extra delay for the closer speaker is `(3-2)/343 ≈ 2.92 ms`. The app displays this candidate but **does not currently add it to the output**. Real timing also contains USB/CoreAudio buffering and possible per-bus console DSP latency. Accurate compensation requires synchronized arrival-time measurement, ideally a calibrated mic + appropriate loopback/sweep procedure. Whether these distances are acoustically worthwhile to compensate is TBD and should not be guessed.

## E. Minimum send-back checklist / 需补充给开发者的数据

- Four speaker `(X,Y)` coordinates in metres, measured relative to the taped center, and stage radius/actor movement boundary.
- Mixer/audio interface manufacturer, precise model, macOS version, number of visible CoreAudio output channels; a screenshot of Audio MIDI Setup and console routing settings can help.
- For each output 1–4: which physical speaker it goes to, and whether independent gain/delay DSP is enabled anywhere in the console or amplifier.
- If available: actual center-point SPL readings under one consistent safe calibration signal, and optional measured delay arrival times.
- Target safe volume limits / production sound safety procedure. The tool has no medically validated ADHD-stimulus limits.

All these are **pending physical site information**. Software geometry is functional; acoustic calibration is not completed.
