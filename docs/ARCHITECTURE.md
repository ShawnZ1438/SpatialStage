# SpatialStage v0.3.1 architecture

```text
Browser UI (one editing window)
  ├─ keyed cue rows, angle dial, cue/global envelopes
  ├─ revisioned single-flight save queue / retry state
  └─ HTTP, exact loopback origin:8765
       FastAPI factory (no import-time data directory)
       ├─ byte-limited request receive / project path validation
       ├─ ProjectStore: atomic JSON / project media / disk-spooled ZIP
       ├─ AutoCal worker: explicit test stream, capture/analyze/review
       └─ StageController
           ├─ NEXT cue ID, readiness, latched output errors
           ├─ one background decode worker + separately locked LRU cache
           └─ atomic chain scheduling → Mixer (48 kHz frame clock)
                PCM → natural fades + stop envelope → cue gain
                → cue/global angular modulation → VBAP → four channels
                → approved physical-channel AutoCal trim/delay
                → persistent final master gain/mute ramp → clip guard
                → PortAudio/CoreAudio → four discrete console buses
```

## Data and geometry

`Project(schema_version=3)` preserves existing data compatibility. Speakers store bearing, distance, output channel and optional manual trim. The UI converts X/Y relative to the taped center using clockwise `atan2(x,y)`. Four unique outputs and adjacent bearing gaps below 180° are validated. The center is fixed; software does not locate actors, infer a new origin or model room reflections. Perceptual accuracy differs from the 0.01° input resolution.

Cue IDs are immutable navigation identities. The NEXT index is derived for display/API compatibility; reorder/import preserves identity. Deleting NEXT enters `needs_rearm`. Clicking a row is selection only; ARM SELECTED is a distinct action. The UI's BEFORE badge means list position, not observed playback history.

Cue parameters include start behavior, waits, fades, replace style/transition, continue mode, base bearing, angular ADSR/keyframes. Live sync updates voice cue parameters by ID but never swaps decoded PCM or rewrites a previously scheduled start. Live fade edits blend from the last rendered natural-envelope value for 15 ms. Existing v0.3 gain/direction smoothing remains a prototype, not a fully sample-accurate automation subsystem.

## Timeline and stop envelopes

GO first validates that every linked clip is already decoded, then schedules the complete chain under one mixer lock. No partial chain is emitted if a file is missing. `auto_continue` anchors to start+post-wait; `auto_follow` anchors to scheduled end+post-wait; the incoming pre-wait is added. Fades run inside these intervals, not subtracted from waits. Queue mode may further postpone the incoming voice until existing voices end.

A per-GO chain ID protects equal-start automatic siblings from replacing one another. This explicit simultaneous-group exception fixes zero-wait chains without breaking manual replacement or CUT GO. Nonzero-start replacements still stop older voices at their incoming start time.

Each voice keeps scheduled stop segments. A new stop starts from the current stop-envelope value and can only shorten the existing deadline. Taking the minimum of applicable segments preserves past fade history when future replacements are planned. Pending voices can be cancelled without ever emitting PCM. The monotonic guarantee concerns the **stop envelope**, not every sample of arbitrary audio or independently edited volume.

MAIN MUTE uses a sample-counted 15 ms ramp which survives callback boundaries. AutoCal delays are upstream of this final gate. Fully muted blocks clear delayed PCM; PANIC clears buffers immediately, clears voices and resets the ramp to zero. PANIC prioritizes immediate digital silence over a click-free tail. It cannot undo hardware-buffered samples. MAIN MUTE keeps both cue and global clocks running; true pause is not implemented.

## Decode and output state

ARM/sync starts background preload of the next automatic group. Cache operations use a separate lock; decoding/FFmpeg uses a worker/decode lock, not the controller/mixer lock. Cached buffers are immutable and keyed by project/path/size/mtime. GO is cache-only and rejects a not-ready command without moving NEXT. Preflight warms all assets but reports shows above 700 MiB. Cache eviction and large automatic groups remain capacity limits, not streaming support.

A stream object alone does not mean active output. Status/GO checks stream.active; inactive/finished/error paths latch mute, clear voices and require manual reconnect. A software callback failure emits zero for that block and latches an error. There is deliberately no automatic unmute/replay after reconnect. Stream hardware indices/names are not permanent universal device identifiers.

Control still performs some filesystem reads/stat checks and acquires locks; the prototype does **not** provide a hard real-time latency bound. Callback NumPy allocation, Python/GIL scheduling, repeated control sync and hardware-driver behavior require load testing. Native preallocated DSP and lock-free control events are the production migration path.

## Persistence, concurrency and web boundary

Project PUT uses atomic file replacement. The browser snapshots each save revision, serializes PUTs and drains newer edits before resolving explicit Save. Save errors retain dirty state, display Retry and keep the settings dialog open. Transport preparation awaits saves; a STOP/PANIC epoch cancels GO still waiting on save acknowledgement. Requests already dispatched cannot be recalled by this client-side mechanism.

Keyed cue row elements survive periodic status polling. Import only sorts new rows. Single browser ownership is an operational restriction: there is no server compare-and-swap revision/ETag, project-wide transaction or cross-tab conflict merge. Media import/replacement/project-switch requests can still race with simultaneous editor changes; avoid editing during these operations. This is tracked, not silently declared fixed by the save queue.

ASGI limits whole request receipt to 256 MiB, including chunked requests; per-file upload checks remain 150 MiB/250-file limits. JSON/media paths are constrained to a project. Export streams a spooled ZIP, includes only current referenced media/project/AutoCal JSON and excludes logs/temporary files. ZIP import is not implemented.

Host and browser Origin allow only localhost/127.0.0.1:8765 (HTTP); absent Origin is allowed for CLI/API use. These controls restrict foreign browser pages, not local untrusted processes. There is no LAN auth model. `create_app` constructs storage explicitly; `server.main` uses Uvicorn factory mode.

## AutoCal boundary

One center point, balanced, XLR, experimental EQ off. A separate measurement worker owns temporary duplex audio while show output is disconnected/muted. Report JSON is persisted atomically, raw microphone audio is not. Approval requires a passing unchanged profile and explicit APPLY. Only bounded attenuation/relative delays are applied, upstream of final mute. Recalibrate after external console gain/routing changes which the software cannot detect.

Cancellation marks cancelling, requests sounddevice.stop and retains measurement ownership until the worker acknowledges. Before saving a report the cancellation flag is checked under lock. A cancelled partial run cannot become an applied profile. Driver interruption is best-effort; physical mute remains the emergency boundary.

## Validation and limits

See [RELIABILITY.md](RELIABILITY.md) for regression evidence and real-hardware acceptance. Software tests use synthetic buffers and mocked output; they do not certify absolute dB SPL, sound localization, aggregate-device clock compatibility, native Mac performance or participant outcomes.

Reference: [PortAudio callback requirements](https://portaudio.com/docs/v19-doxydocs/writing_a_callback.html). No blocking operations or unpredictable allocation should be in a production callback; this prototype still violates that objective.
