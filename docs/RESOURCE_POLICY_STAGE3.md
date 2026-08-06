# Stage 3 B02 resource policy and non-exhaustion plan

Status: provisional engineering safety policy for the approved one-user localhost test machine. It is not a validated product upload policy, production quota, SLO, availability target, or support commitment.

## Versioned decoder policy

`decode-resource-policy-v1` is an explicit frozen `DecodeConfig` in `physical_vision_image`. The current guards are:

| Guard                   |          Provisional value | B06 enforcement                                                                                                                                                                |
| ----------------------- | -------------------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Encoded input           |           20,000,000 bytes | A byte input is checked directly; a binary stream is read only through `max + 1` bytes before rejection.                                                                       |
| Source width and height |                12,000 each | Positive decoder-observed dimensions are required before pixel allocation. PNG IHDR dimensions are also checked before Pillow opens the image.                                 |
| Decoded pixels          |                 40,000,000 | Inclusive source/canonical pixel guard; Pillow decompression-bomb warnings and errors are independently converted to rejection.                                                |
| Frames                  |                  exactly 1 | Decoder-observed frame count is checked before format acceptance or full decode. APNG and deceptive multi-frame containers are rejected.                                       |
| Metadata                | 1,000,000 bytes/work units | JPEG APP/COM and PNG ancillary payloads are counted before full decode. Compressed PNG text is expanded only through `remaining budget + 1`.                                   |
| Estimated decoded RAM   |          160,000,000 bytes | Conservative `width × height × max(3, decoder bands)` estimate is checked before `load()`.                                                                                     |
| Decode elapsed time     |                5.0 seconds | Monotonic checks occur before/after stream admission, decoder open, pixel load, EXIF transpose, and detach. Exact-boundary elapsed time is allowed; over-boundary is rejected. |
| Deadline/cancellation   |            caller supplied | Cooperative monotonic deadline and cancellation checks return typed `DECODE_BUDGET_EXCEEDED` failures. B13 owns propagation from sessions/requests.                            |

These values prevent unbounded parser work on the personal test machine while measurement is still incomplete. They must not be represented as validated upload-quality limits. In particular, later model input dimensions are preprocessing settings, not upload caps. This policy introduces no guidance-attempt ceiling.

All decoder failures are content-free and stable. The boundary exposes only an enum code, category, and allowlisted message key. It does not include caller strings, metadata values, image bytes, filesystem paths, OCR, or serial-like content.

## Ownership by backlog boundary

| Resource or behavior                                                                                                                                                            | B06 now                                                                                                   | Deferred owner                                                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Encoded bytes, decoded dimensions/pixels, one frame, metadata work, decoded-RAM estimate, Pillow bomb handling, decode elapsed checkpoints, direct deadline/cancellation checks | Enforced and tested                                                                                       | B13 integrates request/session deadlines and cancellation; B17 performs adversarial system hardening.    |
| Temporary disk                                                                                                                                                                  | Decoder uses in-memory buffers and writes no temporary files; harness samples free space                  | B13 bounds coordinator spooling if introduced; B17 enforces final process-wide temporary-storage policy. |
| Process CPU/RAM                                                                                                                                                                 | Harness observes process CPU and working-set/peak working-set                                             | B13 owns bounded queues/concurrency; B17 owns process containment and overload behavior.                 |
| GPU/VRAM                                                                                                                                                                        | Harness observes NVIDIA state when `nvidia-smi` exists and records that Pillow decode did not use the GPU | B12 owns inference GPU/VRAM benchmarks and guards; B17 owns integrated enforcement.                      |
| Retained local storage                                                                                                                                                          | Harness samples storage headroom; decoder retains no encoded input                                        | B13/B16 own retention integration; B17 owns storage-exhaustion enforcement without silent eviction.      |
| Thermal state                                                                                                                                                                   | Harness records NVIDIA temperature when exposed and explicitly records unavailable CPU thermal telemetry  | B12 observes inference thermal load; B17 chooses platform-specific sensors/limits after evidence.        |
| Hard interruption of a native decoder call                                                                                                                                      | Cooperative checkpoints only; synchronous Pillow work cannot be preempted safely in-process               | B13/B17 must place work in a killable bounded worker if hard deadlines are required.                     |

## Reproducible content-free measurement

Run from the repository root with the pinned environment:

```text
uvx --from uv==0.11.31 uv run python scripts/measure_decode_resources.py --iterations 10 --width 1024 --height 768
```

The harness generates solid-color JPEG and PNG fixtures in memory, decodes them under `decode-resource-policy-v1`, exercises cancellation and deadline probes, and emits JSON only. Input dimensions and iterations are bounded (`1..2048` per dimension, at most 4,000,000 pixels, and `1..100` iterations). It emits no image bytes, metadata values, OCR, serials, private paths, or telemetry to a remote service.

## Provisional current-machine observation

Measured 2026-08-06 on the approved personal-test machine. These results are one synthetic run, are non-generalizable, and do not validate product limits or an SLO.

- OS: Windows 10, AMD64; 20 logical CPUs.
- CPU identifier discovered from the platform: `Intel64 Family 6 Model 198 Stepping 2, GenuineIntel`. The standard API did not expose a marketing model name, so none is assumed.
- Host RAM: 33,931,792,384 bytes total; minimum available sample 14,830,821,376 bytes.
- GPU: NVIDIA GeForce RTX 5070; 12,820,938,752 VRAM bytes reported; 1,092,616,192 bytes used before/after; 0% utilization and 37 °C before/after. Pillow decode used no GPU.
- Storage headroom sample: 624,907,235,328 bytes free for both temporary and retained-storage locations.
- Workload: ten 1024×768 synthetic JPEG decodes and ten synthetic PNG decodes.
- Outcome: 20 successful, 0 failed; 168.254 ms wall time and 171.875 ms process CPU time.
- Maximum decoder-observed elapsed time: 16.0 ms; maximum encoded input 12,916 bytes; decoded-RAM estimate 2,359,296 bytes; metadata 14 bytes.
- Process working set: 22,499,328 bytes before and 26,615,808 bytes after; peak working set sample 37,478,400 bytes.
- Cancellation and deadline probes both returned `DECODE_BUDGET_EXCEEDED`.
- CPU thermal observation was unavailable through the dependency-free standard-library harness.
- Free-space samples increased by 1,572,864 bytes during the run. The harness performs no file writes; this delta is ambient filesystem activity and is reported rather than interpreted as decoder disk use.

Before widening any guard or claiming minimum hardware, rerun bounded representative workloads, record platform sensor availability, and obtain the applicable B12/B13/B17 evidence and review.
