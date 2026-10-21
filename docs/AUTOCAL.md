# SpatialStage AutoCal v0.3 — 1-point XLR measurement and human-approved correction

**Status:** working software with simulated-device tests; **not yet validated against the actual Apple Silicon Mac, microphone, mixing console, or four loudspeakers**. It is a low-volume rehearsal measurement assistant, not Audyssey MultEQ, an SPL meter, a hearing-safety controller, or a clinical instrument.

## Locked scope in this release

| Setting | Value | Implication |
|---|---|---|
| Measurement points | `1` | Place mic at taped stage center `(0,0)` at approximate actor ear height |
| Optimization | `balanced` | **Degenerates to center-only** with one point, not a spatially balanced whole-stage optimization |
| Microphone | `xlr` | Condenser/dynamic measuring microphone through a preamp/USB audio interface; hardware phantom power **only if required by that model** |
| EQ | `false` | No corrective FIR/IIR filters; response spectrum plotted for diagnostic viewing only |
| Sample rate | 48,000 samples/sec | All playback and capture requests require 48k-supported CoreAudio/PortAudio routes |
| Outputs | Four discrete channels | Each channel driven and recorded separately to avoid ambiguity |
| Test signal | 200 Hz – 8.5 kHz logarithmic chirp with short smooth taper | 0.85 s chirp + 0.25 s lead silence + 0.60 s tail per channel |
| Digital test level | −30 dBFS default, selectable −36..−24 dBFS peak | Not equal to dB SPL at actor's ears. **Lower analogue gains before running.** |

## Hardware wiring (preferred)

```text
Mac (Apple Silicon; local web UI) ─USB-C─> shared-clock 4-out / XLR-in audio interface
                                     OUT 1 ─> console 1 isolated route ─> FL / 315°
                                     OUT 2 ─> console 2 isolated route ─> FR /  45°
                                     OUT 3 ─> console 3 isolated route ─> RR / 135°
                                     OUT 4 ─> console 4 isolated route ─> RL / 225°
                            XLR measurement mic ─> interface MIC IN 1 / selected channel
```

- A compatible USB mixing console exposing **four independent CoreAudio outputs AND an XLR input** may serve as both device endpoints. A separate input interface might work, but independent hardware clocks can drift or invalidate timing; the software cannot guarantee multi-device synchronization. Prefer both input/output on the same clocked interface or a verified aggregate device.
- Four console channels **must** go to four isolated speakers. Disable reverb, dynamics, console auto-level, auto-delay and input AGC. Prevent acoustic feedback between microphone and routed outputs.
- Before measuring: stop cues, disconnect the ordinary performance stream in SpatialStage, keep MAIN MUTE ON, verify that no actor is on stage, set an appropriately low **analogue** output volume and mic preamp gain, and communicate the test to everyone at the venue. The AutoCal wizard makes a separate temporary full-duplex stream and intentionally emits short test sweeps while the performance mixer is disconnected/muted.
- Verify speaker channel labels with a manually attenuated `Test CH` tone before AutoCal. Ensure the mic is not physically overloaded or clipping, and keep input gain fixed across all four measurements.

## Operator steps in UI

1. Launch `spatialstage` and open the show project. Set `Stage setup` XY geometry and CH1→CH4 patch mapping. **Set manual speaker trims to 0 dB and turn approximate distance compensation OFF** to avoid double correction.
2. Click `◉ AutoCal · XLR measurement` in the left sidebar.
3. Choose the **XLR input device**, mic input channel (1..16), and the **four-channel output device**. Choose a conservative digital sweep level (default −30 dBFS). Click `Save AutoCal setup` to persist project-local settings.
4. Place the microphone at the stage center; check the safety acknowledgement. Click `Measure CH1–CH4`. The UI reports channel progress. Each channel captures one microphone waveform and computes correlation with the known emitted reference signal.
5. Review all four rows: input dBFS level, arrival time including hardware latency, SNR, clipped-input checks, suggested attenuation (≤0 dB), and suggested extra delay (0..30 ms). Inspect the **relative level bars**, **arrival bars** and 7-band frequency response curves normalized to 1 kHz. A failing/imbalanced result cannot be applied; check hardware and rerun.
6. **Nothing automatically changes playback.** For a passing session, tick `I inspected...`, type the literal word `APPLY`, and press `Apply approved profile`. The server also requires that audio is disconnected, all cues stopped, and MAIN MUTE is ON. Corrections then persist with this project and take effect on subsequent live playback; the next audio connection remains muted.
7. A session can be disabled with `Disable AutoCal` while output is disconnected and muted. Geometric speaker changes, physical channel reassignment, manual trim changes, or toggling geometric distance compensation automatically invalidate the active profile. Remeasure with the real patch.
8. **Audible verification is still required**: perform center and off-center walk tests at safe levels, compare AutoCal ON vs OFF with the same audio material, check physical channel routing, and document console/amp changes.

## Measurements vs acoustic truth

The software derives correlation peak lag `arrival_samples` using FFT cross-correlation of microphone samples against the output reference. This lag **includes** capture/playback buffering and digital console effects; the reported absolute `arrival_ms` is NOT just propagation time. Relative arrival differences can be used as tentative channel delays *only if all measurements use a stable clock path and configuration*. The recommended extra delay is `(maximum_lag − channel_lag) / 48000` seconds, capped at 30 ms. The system cannot measure true acoustic time of flight if input/output latencies drift between sequential channels.

Input level is microphone **dBFS**, NOT acoustic dB SPL. The level estimate is time-domain RMS during the swept tone. Relative gain recommendations attenuate channels down to the quietest measured channel, never boost (range −12..0 dB); if spread exceeds 12 dB, the profile is rejected. Same XLR mic/preamp gain must be maintained across all channels. A clipped channel (peak ≥ 0.97 digital full scale), very weak signal, low estimated SNR (under 12 dB), or >200 ms capture latency fails automated checks.

The plotted frequency response is a **rough diagnostic** from the regularized deconvolved impulse estimate (125, 250, 500, 1000, 2000, 4000, 8000 Hz); it is *not* microphone response-corrected, phase corrected, or automatically EQ'd. To compare across sessions/frequency bands, a calibrated measurement mic and validated procedure are necessary. No FIR/IIR EQ is generated or applied.

**Single-point limitation:** for an actor moving away from center, arrival times and SPL vary spatially, and VBAP virtual-source localization can change. `balanced` is a chosen configuration label, not an area-optimizer at `measurement_points=1`. This system cannot establish an audibly consistent 360° image for all actor positions or prove any response relevant to ADHD.

## Persistence and approval safety

- Config: `~/.spatialstage/projects/<project-id>/autocal/config.json`
- Session summaries: `~/.spatialstage/projects/<project-id>/autocal/<session-id>.json`
- Project reference: `project.json` fields `calibration_enabled` and `active_calibration_id`
- Stored fields include channel correspondence, original speaker geometry checksum, device names, tested configuration, quality diagnostics, response plot points, proposed correction arrays, and approval timestamp. **No raw microphone sound is written to disk** and no personal/participant information is gathered.
- Session lifecycle: `review_required` → manually `applied`, or stay pending. Failed-quality profiles cannot be applied. A new measurement is stored as a separate reviewable session. An approved profile is bound to the four-speaker stage geometry and named output device, and can be disabled; changes in patch/routing require remeasurement.
- API `POST /api/projects/{id}/autocal/sessions/{sid}/apply` requires `{ "confirm": "APPLY" }` and validates safe engine state, stored quality and geometry. A regular project PUT request **cannot** forge approval or inject arbitrary correction arrays.
- Corrections (per physical CH1..CH4) are a bounded attenuation stage and causal output delay FIFO **after VBAP/master gain**. Muting flushes all queued delayed samples. DSP is still prototype Python/NumPy on an audio callback, not hard real-time.
- Untrusted local operators with direct filesystem access can manipulate local JSON: this is **not** a security/authentication boundary. Keep show projects under a trusted macOS account.

## API routes

| Method | Route | Function |
|---|---|---|
| GET | `/api/projects/{id}/autocal` | Config, list of sessions, current run and active state |
| PUT | `/api/projects/{id}/autocal/config` | Validate/save exact v0.3 one-point balanced XLR no-EQ config |
| POST | `/api/projects/{id}/autocal/start` | Explicit safety acknowledgement starts background capture worker |
| GET | `/api/projects/{id}/autocal/run` | Current run progress/failure/completion |
| GET | `/api/projects/{id}/autocal/sessions/{sid}` | Channel metrics and plot data; no raw microphone PCM |
| POST | `/api/projects/{id}/autocal/sessions/{sid}/apply` | Manual approval and persistent postmix trims/delays |
| POST | `/api/projects/{id}/autocal/disable` | Disable active compensation while audio disconnected/muted |

## Tests and limitations

`python -m pytest -q` uses deterministic synthetic microphone captures and mock devices, checks actual channel-lag measurements, clipping rejection, config validation, no-boost recommendations, persistent profiles, geometry invalidation and tamper-resistant API approval. `node --check stagespatialcue/static/app.js` checks browser script syntax. **These are not measurements of your actual microphones or speakers.** Prior to live use, verify four independent hardware outputs, intended XLR input, phase/polarity by trusted equipment, swept-sine non-clipping, correct matched route clocks, gain limits and actor-space coverage.

**Pending site details:** actual four-speaker XY coordinates, console/interface make/model, selected XLR microphone + preamp, mapping of Mac audio channels to isolated buses, playback/recording clock compatibility, safe sound pressure monitoring, manual centre and off-centre validation. Nothing here supplies Audyssey's proprietary MultEQ algorithms or licensed EQ databases.
