# Research use and ethical boundaries

SpatialStage provides **technical sound-cue control** for a drama workshop exploring actor-centered hearing and auditory spatial effects. The only participants are performers within a four-speaker perimeter; there is no audience-facing sound field. The software provides **controllable sound stimuli**, not a scientific measurement of perception or a claim about ADHD treatment, performance, diagnostic status, cognition or neural effects.

## What the application stores

Only show projects, audio files copied into per-project media storage, speaker setup, Cue execution/position settings and audio design envelopes. **No participant names, behavioral measures, ratings, research conditions or experimental response logs are collected.** Optional operator-only troubleshooting events can be enabled with `SPATIALSTAGE_DIAGNOSTICS=1` but are OFF by default. They are not synchronized acoustic timestamps.

## Physical safety

Actor listening position moves within the four-box enclosure. Sound pressure may vary and any precise source azimuth is primarily valid at the reference center. Use a sound professional to establish sound pressure limits appropriate for participants, provide a stop/mute procedure, review acoustic stimulus intensity and duration with relevant local research or theatre oversight, and keep actors informed of surprising sound effects in advance. Audio levels should not be inferred from software dBFS or `gain_db` alone.

## Experimental interpretation

If investigators later want to evaluate ADHD-related outcomes, they need a separately designed study with appropriate consent/oversight, controlled stimuli, repeatability and independent outcome measurement; no such workflow is included in this program. UI directional angle is a **requested DSP parameter**, not evidence that a moving actor perceived the exact angle.
