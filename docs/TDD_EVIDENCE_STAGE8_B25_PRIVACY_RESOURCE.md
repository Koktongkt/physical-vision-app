# Stage 8 B25 privacy/resource TDD evidence

This file records observed commands for the bounded analyzer and content-free resource slice. It does not fabricate RED results for cancellation coverage that passed on its first execution after the shared cancellation mechanism existed.

All Python commands use the repository-pinned `uv==0.11.31`. An initial unpinned `uv run ...` did not execute tests because the installed launcher was `0.12.2`; it is not counted as RED evidence.

## Slice 1 — non-queued overload, timeout recovery, resource endpoint

RED command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py -k 'overload or timeout_is_content_free or resource_endpoint or resource_probe_failure' -q
```

Observed RED: 4 failed, 7 deselected. `ApiSettings` was not exported, `create_app` did not accept `resource_probe`, and the endpoint/bounded analyzer behavior was absent.

GREEN command (after correcting one test assertion that incorrectly banned the explicitly permitted `host_available_memory_bytes` key):

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py -k 'overload or timeout_is_content_free or resource_endpoint or resource_probe_failure' -q
```

Observed GREEN: 4 passed, 7 deselected. The sole warning is the repository's existing Starlette/httpx test-client deprecation warning.

## Slice 2 — bounded synthetic live measurement

RED command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_resource_measurement.py -q
```

Observed RED: collection error because `measure_synthetic_live_analyze_workload` did not exist.

GREEN command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_resource_measurement.py -q
```

Observed GREEN: 5 passed in 1.81 seconds.

## Slice 3 — content-free typed analyzer failure and recovery

RED command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py::test_analyzer_failure_is_content_free_and_capacity_recovers -q
```

Observed RED: 1 failed. The injected sentinel exception message appeared as `message_key`.

GREEN command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py::test_analyzer_failure_is_content_free_and_capacity_recovers -q
```

Observed GREEN: 1 passed. Analyzer errors are now mapped from the fixed enum to safe API message keys and categories; the slot recovered for a following request.

## Slice 4 — enforce the resource response allowlist

RED command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py::test_resource_endpoint_filters_unexpected_probe_content -q
```

Observed RED: 1 failed. An injected probe could replace schema/policy/capacity values and add sentinel-bearing `payload`, `request`, and GPU `name` fields.

GREEN command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py::test_resource_endpoint_filters_unexpected_probe_content -q
```

Observed GREEN: 1 passed. The endpoint now rebuilds its response from a fixed scalar allowlist, uses actual capacity state, validates observed GPU scalars, and drops all unexpected probe content.

## Cancellation coverage

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_barcode_api.py::test_cancelled_request_signals_analyzer_and_capacity_recovers -q
```

Observed: 1 passed on first execution. It proves an ASGI request cancellation signals the analyzer's cooperative callback, the worker exits, and a following request obtains the released slot. This is coverage evidence, not claimed RED evidence.

## Measurement command

```text
uvx --from uv==0.11.31 uv run python scripts/measure_live_resources.py --iterations 5 --width 512 --height 384
```

Observed: exit 0; content-free `live-resource-measurement-v1` JSON with 5 successful analyses, 0 failed, and no media output. The exact output is tracked at `docs/measurements/stage8_live_resource_observation.json`.

## Final regression gates

- `uvx --from uv==0.11.31 uv run pytest -q` — 338 passed, 1 skipped, 1 pre-existing Starlette/httpx deprecation warning.
- `uvx --from uv==0.11.31 uv run ruff check .` — all checks passed.
- `uvx --from uv==0.11.31 uv run ruff format --check .` — 26 files already formatted.
- `npm run contracts:check` — generated contract types in sync.
- `npm run test:ts` — 141 passed, 0 failed.
- `npm run typecheck` — passed.
- `npm run format:check` — all matched files use Prettier formatting.
- `npm audit --audit-level=high` — 0 vulnerabilities.
- `uvx --from uv==0.11.31 uv run python scripts/check_sensitive_files.py` — passed for 237 tracked files before staging.
- `git diff --check` — passed.
