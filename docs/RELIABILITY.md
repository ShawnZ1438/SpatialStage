# v0.3.1 audit repair and acceptance record

## Source provenance

Baseline: `main` commit `5761a7337b2619da8979faf34e045b417c1dbf29`, tree `6d0b7461c9a4686fca20164a5d4a3ec820b03b10`. Terminal GitHub DNS was unavailable in the test environment. The connected GitHub API supplied the current ref/tree; the available v0.3 archive reconstructed **exactly the same Git tree including file modes**. Thus repairs start from the latest verified source, not from an unverified old prototype. This is an API-verified shallow snapshot, not a claimed successful terminal pull.

## Required regressions

| Reported defect | Repair | Regression evidence |
|---|---|---|
| Repeated STOP/replace resets fading voice to full | Retain stop segments; restart only from current gain; never extend prior end | Repeated stop/replace, shorter stop and future replacement scheduling tests |
| Zero-wait auto-continue swallows first cue | Atomic chain schedule and same-start chain identity protection | Two- and three-cue groups assert energy on every intended output |
| Import re-sorts old cues | Numerically sort incoming batch only; append | Existing reversed rows survive importing an out-of-order004/003 batch |
| Mute/unmute sample discontinuities | Persistent 15 ms sample-counted final master ramp | Block sizes1/4/512; start continuity, endpoint and slope assertions |
| Save drops edits during in-flight PUT | Revisioned single-flight queue with dirty retry/error propagation | Actual app in Node VM: trailing edits, failed save/retry, settings acknowledgement, trailing failure |

Baseline had 31 passing existing Python tests. New failing-first runs demonstrated 10 Python failures and two frontend failures before fixes. Existing tests expecting instantaneous initial unmute were updated to explicitly warm up the newly intentional ramp; their DSP assertions remain. No test substitutes real measured speaker audio for synthetic PCM.

## Additional repaired edges

Stable NEXT ID and explicit re-arm on deletion; background decoding/cache synchronization with cold GO rejected; stream.active/finished/error latching; live fade-parameter blending; stable row DOM across polling; STOP superseding save-waiting GO; PANIC immediately clears AutoCal delay buffers; final mute downstream of compensation; cancel/abort AutoCal without persisting partial results; factory server without import side effects; exact loopback port Origin; streaming request quota; disk-spooled clean ZIP export; removal of obsolete upgrade/mock-preview scripts; portable browser test and wider CI configuration.

## Local validation record

- Python 3.13.5: **56 tests passed**. Hardware-facing tests use synthetic signals and mock streams.
- Node22: **6 save/transport regression tests passed**; both JS files pass `node --check`.
- Local Uvicorn factory startup, health/API requests and isolated project/media persistence exercised.
- Chromium interactions passed: numbered import/manual order preservation; held mouse click across polling; delayed save acknowledgements retaining latest rotation; invalid geometry save stays open and retries; refresh persistence; stable NEXT; AutoCal dialog; zero uncaught page errors.
- Browser HTTP navigation is blocked by this runner's administrator policy. Browser interaction evidence uses the explicit **offline DOM + local API bridge** mode, not a claim that ordinary browser navigation worked. CI is configured to run ordinary HTTP navigation.
- Python3.11/3.12 CI jobs and correctness lint are configured, but not claimed as locally executed. Read the per-commit CI result for remote outcomes.
- No target Mac, actual four-channel interface, loudspeaker, microphone, hardware unplug or measured SPL test was performed here.

Reproduce:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
node --check stagespatialcue/static/app.js
node --check stagespatialcue/static/save-queue.js
node --test tests/js/*.test.cjs
python -m ruff check stagespatialcue tests
python -m playwright install chromium
python scripts/browser_smoke.py --spawn
```

## Before involving actors

1. Save a project folder backup, identify the person operating independent hardware mute, and establish physical gain/headroom limits. Verify safe levels with appropriate measurement equipment; software meters alone are insufficient.
2. Confirm all four independent paths at low volume: CH1 L, CH2 R, CH3 RR, CH4 RL, or document another map. Test polarity/console DSP and a common clock; record only technical equipment settings, not participant data.
3. Preflight the actual show and wait for ready. Exercise manual/layer/queue, simultaneous automatic groups, nonzero pre/post waits, CUT, repeated STOP/GO, mute during sound, PANIC, and NEXT removal/re-arm. Confirm no delayed replay after rejected GO.
4. Confirm genuine stream loss forces silence and requires manual reconnect/unmute. Validate disconnect/reconnect, browser refresh and app restart with no surprise replay. An API mock is not this hardware test.
5. Test AutoCal with actors absent: correct input, sweep level, cancel/PANIC during capture, reject poor results, explicit APPLY, master mute after delay compensation and manual comparison. External mixer changes invalidate the physical assumptions even if not detected by software.
6. Run a full-length rehearsal with representative simultaneous voices and control edits. Inspect underruns, clipping warnings, memory and perceived click behavior. Verify off-center actor positions; center-calibrated panning is not spatially uniform.

## Deliberately unresolved

This update does not promise every requested feature is complete. True pause, triggered ADSR release, selective replace groups, Cartesian paths, stereo width, ZIP restore, revision conflicts/media-edit transactions, idempotent server triggers and a native real-time engine remain in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). No participant logging is added. The default digital clip guard is not an acoustic safety limiter.
