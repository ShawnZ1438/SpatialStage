# Independent audit repairs — 2026-10-23

These repairs follow the independent audit of `d68400e`. They preserve the local
simulation console and existing cue timing semantics. Publication is on the feature
branch for review; main is not force-pushed or merged by this work.

## Repairs

- **F1, media/edit race:** uploading a new file no longer replaces the entire
  browser project with an older response. Only new immutable cue IDs are appended
  to the current editor state, then the save queue persists that merged state.
  Existing edits, ordering and cue deletions survive. Replacement audio updates only
  filename/path/duration on a still-existing cue. Media operations are serialized,
  project switching waits for them, and closing during one prompts for unsaved work.
  The server rereads current project fields after decoding instead of saving its
  pre-upload snapshot. This is single-editor protection, not multi-client revision
  control or a crash-safe distributed transaction.
- **F2, degenerate geometry:** all four neighboring bearings must differ by at
  least 0.01°, including the circular last-to-first gap. Duplicate bearings such as
  `[0,0,120,240]`, 0/360 aliases and 0/359.999 are rejected before mixing.
  Existing unique routing and gaps below 180° remain required.
- **F3, unavailable output:** negative device IDs return validation errors.
  Query/settings/open/start/cleanup failures produce an actionable HTTP 400 response
  and leave output disconnected, master muted and voices cleared. The stereo UI
  no longer overwrites a failed-connect toast with a success message. AutoCal owns
  the device while measuring; ordinary connection attempts still cannot interrupt it.
- **F4, 360 endpoint:** cue and speaker inputs accept 360° as the alias of 0° and
  persist canonical values in `[0,360)`. The dial and numeric bearing editor agree.
  Negative/out-of-range API inputs remain invalid. Angular envelope offsets remain
  unwrapped: 360° there still means a full turn.

## Local verification

Windows Python 3.12, installed Edge headless, isolated fixture data. No physical
audio playback or microphone sweeps. The user's existing port 8765 session was
left intact. Real-browser regression servers use 8766/8767 with a test-only exact
Host/Origin adapter; foreign origins retain the production rejection policy.

- Project Python suite: **80 passed** (including 15 new parameterized audit cases).
- Node save/editor suite: **9 passed** (three new race/endpoint cases).
- Independent audit replay: **38 API/engine + 15 supplemental + 5 route/CLI +
  4 frontend logic + 21 real Edge UI checks passed**. Original audit evidence was
  preserved; replays used a separate ignored directory. One old assertion requiring
  HTTP 422 for cue bearing 360 was removed from the replay's malformed-input list:
  it encoded F4's old behavior. Canonical 0 persistence/rendering is tested instead.
- New `scripts/browser_audit_regressions.py`: five real UI scenario groups cover
  delayed import and replacement responses, subsequent PUT/reload persistence,
  360 numeric input/reload/dial, geometry rejection/recovery and wrap duplicates,
  hardware/stereo driver errors and mute/disconnect state. Zero uncaught page errors.
- Original browser smoke suite passed on the isolated guarded server: import/order,
  saves/retry, reload/NEXT, AutoCal dialog and silent capture/download. Its first
  local wrapper attempt nested Playwright sync loops and failed before execution;
  running that suite in a separate process corrected the harness issue.
- Ruff correctness checks, JavaScript syntax checks and diff whitespace checks pass.

CI now runs both the original browser smoke and the new guarded audit browser
regressions, in addition to Python 3.11/3.12/3.13 and Node tests. CI results must be
verified against the exact published SHA, not inferred from this configuration.

Reproduce:

```text
python -m pytest -q
node --test tests/js/*.test.cjs
python -m ruff check stagespatialcue tests
python scripts/browser_smoke.py --spawn
python scripts/browser_audit_regressions.py
```

Use `--browser-path` with installed Edge on Windows, or install Playwright Chromium.
Do not run the smoke's default server if the user's port 8765 is occupied. The new
audit regression script refuses an occupied 8767 and always uses temporary data.
Local raw logs, screenshots, WAVs and copied audit probes remain ignored and are
not included in public source commits. One Starlette/httpx deprecation warning
remains in the local Python suite.

## Limits retained

Automated digital tests do not validate the physical four-output interface, console
bus routing, speaker levels/polarity, microphone, room acoustics, device hot-unplug,
long-duration load or Apple Silicon/CoreAudio. Test those on the target hardware.
ZIP restore/import, pause/resume, loop/trim, stereo-width preservation, MIDI/OSC,
multi-editor conflict resolution, automatic room EQ and HRTF remain unimplemented.
This change adds none of those features. Existing CUT natural fades, additive
pre/post waits, simultaneous zero-wait auto-continue groups and show-clock semantics
are unchanged; the audit's design questions about them are not silently resolved.
