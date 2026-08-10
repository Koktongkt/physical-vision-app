# Stage 8 B25 live resource policy

Status: provisional engineering safety policy for the localhost-only, single-user barcode framing prototype. This is an implemented B25 baseline, not a production security certification, validated performance envelope, SLO, or minimum-hardware claim.

## Versioned live policy

`live-resource-policy-v1` applies these validation-dependent thresholds (VTs):

| Guard                      |                                           Provisional value | Behavior                                                                                                                                                                                          |
| -------------------------- | ----------------------------------------------------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Concurrent analyzers       |                                                           1 | Admission is non-blocking. A second request receives content-free `LOCAL_BUSY` / HTTP 503; it is not queued and is not retried.                                                                   |
| Request analysis timeout   |                                                 2.0 seconds | The API propagates a monotonic deadline and cancellation callback into `analyze_barcode_frame`. Expiry returns content-free `LOCAL_TIMEOUT` / HTTP 504.                                           |
| Cancellation cleanup grace |                                                 0.1 seconds | The API signals cooperative cancellation and briefly awaits cleanup. Capacity remains occupied until the worker actually exits, so a timed-out native call cannot overlap a replacement analyzer. |
| Encoded frame              |                                             4,000,000 bytes | Existing API body admission remains enforced; over-budget input returns HTTP 413 before analysis.                                                                                                 |
| Source dimensions          |                              4,096 × 4,096 maximum per side | Existing bounded decoder setting.                                                                                                                                                                 |
| Decoded pixels             |                                                   8,000,000 | Existing bounded decoder setting.                                                                                                                                                                 |
| Estimated decoded RAM      |                                            48,000,000 bytes | Existing bounded decoder setting.                                                                                                                                                                 |
| GPU probe timeout          | 0.2 seconds default; 0.5 seconds hard configuration maximum | `nvidia-smi` is optional. A process-wide non-blocking lock permits at most one probe subprocess; contention, timeout, absence, malformed output, and process failure become `unavailable`.        |

The analyzer slot is released when its worker future finishes after success, typed failure, timeout, or cancellation. Executor submission failure releases the slot synchronously. The API has no automatic retry loop.

These values are intentionally small for one local tester and must be measured and reviewed before widening. A cooperative deadline cannot forcibly interrupt arbitrary native code. If a worker ignores cancellation, the HTTP timeout remains bounded by the timeout plus cleanup grace, but its slot remains busy until real worker termination to preserve the concurrency bound.

## API-visible content-free observation

Loopback-protected `GET /v1/system/resources` returns exactly these top-level keys:

- `schema_version = live-resource-observation-v1`
- `policy_version = live-resource-policy-v1`
- `elapsed_ms`
- `process_rss_bytes` (or `null` when unavailable)
- `host_available_memory_bytes` (or `null` when unavailable)
- `in_flight`
- `max_in_flight`
- `gpu`

`gpu.status` is `unavailable` or `observed`. An observed GPU object contains only aggregate scalar counts, VRAM bytes, maximum utilization, and maximum temperature. It omits device names and command output.

The observation allowlist excludes request bodies, image bytes or dimensions, barcode boxes and quality, decoded strings, OCR/serial/payload data, filenames, URLs, Host/Origin values, paths, exception strings, session/user identifiers, and arbitrary labels. Probe failure does not fail the request and is not logged or persisted by this implementation.

## Reproducible bounded measurement

Run from the repository root:

```text
uvx --from uv==0.11.31 uv run python scripts/measure_live_resources.py --iterations 5 --width 512 --height 384
```

The harness creates one solid-color fixture in memory, executes analyses serially (`max_in_flight = 1`) with a 2.0-second deadline per iteration, and emits JSON only. Inputs are bounded to 1–25 iterations, 1–1,024 pixels per side, and at most 1,000,000 synthetic pixels. It writes no media.

The content-free observed run from 2026-08-10 is tracked at `docs/measurements/stage8_live_resource_observation.json`:

- 5 successful analyses, 0 failed
- 91.711 ms wall time; 187.5 ms process CPU
- maximum analyzer-reported elapsed time 31.0 ms
- process RSS 38,580,224 bytes before and 46,706,688 bytes after
- minimum sampled host available memory 13,418,319,872 bytes
- GPU observation available; aggregate utilization 7% and temperature 46 °C before/after

This single synthetic local run is non-generalizable. It does not validate the VTs, represent camera workload diversity, or support a production performance claim.
