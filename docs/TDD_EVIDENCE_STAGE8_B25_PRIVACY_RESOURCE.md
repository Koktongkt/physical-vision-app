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

## Browser lifecycle and loopback launcher slice

Scope: browser stop/cleanup lifecycle and loopback web launcher, based on `e7e797192aea9ab98db818e3152b598ac94a25c0`. This evidence makes no B26, production-security, performance, decode, OCR, persistence, or LAN-access claim.

### Browser resource owner

RED:

```text
node --test apps/web/tests/lifecycle.test.mjs
ERR_MODULE_NOT_FOUND: apps/web/lifecycle.mjs
0 passed, 1 failed
```

GREEN after adding the DOM-light resource owner:

```text
node --test apps/web/tests/lifecycle.test.mjs
1 passed, 0 failed
```

### Application lifecycle wiring

RED:

```text
node --test apps/web/tests/lifecycle.test.mjs
4 passed, 1 failed
AssertionError: app.js did not contain createCameraResources
```

GREEN after wiring Stop, Retake, pagehide, beforeunload, visibility-hidden, and track-ended cleanup:

```text
node --check apps/web/app.js && node --test apps/web/tests/lifecycle.test.mjs
5 passed, 0 failed
```

### Bounded loopback-only browser analysis

RED:

```text
node --test --test-name-pattern="analysis is bounded" apps/web/tests/lifecycle.test.mjs
0 passed, 1 failed
AssertionError: fixed 127.0.0.1 API base was absent
```

GREEN after removing the editable API target, adding AbortController timeout/cancellation, and clearing scratch pixels:

```text
node --check apps/web/app.js && node --test apps/web/tests/lifecycle.test.mjs
6 passed, 0 failed
```

### Reviewer-found async exit races

Independent pre-commit review found that an already-resolved response could repopulate cleared UI after Stop, and a stale camera-start rejection could stop a newer stream. Regression tests were added before the fix.

RED:

```text
node --test apps/web/tests/lifecycle.test.mjs
5 passed, 2 failed
TypeError: resources.releaseStream is not a function
AssertionError: analysis epoch guard was absent
```

GREEN after identity-aware stream release and camera/request epoch checks:

```text
node --check apps/web/app.js && node --test apps/web/tests/lifecycle.test.mjs
7 passed, 0 failed
```

### Loopback web launcher

RED:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_local_web_launcher.py -q
ModuleNotFoundError: scripts.run_local_barcode_web
0 passed, 1 failed
```

GREEN after adding the standard-library launcher:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_local_web_launcher.py -q
5 passed
```

Covered launcher behavior at this slice: exact `127.0.0.1` bind, exact approved URL, live static-server smoke/security headers, normal server stop, browser startup failure, and serving cancellation cleanup.

### Implemented provisional browser budgets

- Sample rate: at most 5 Hz (existing B21 VT retained).
- Sample max side: 1280 px (existing B21 VT retained).
- One client request at a time; overlap is rejected by state/resource owner.
- Browser analyze timeout: 2500 ms; abort propagates through `fetch`.
- Hidden pages stop the camera and require explicit Start to resume.

These are provisional personal-test engineering limits, not validated performance or production limits.

## Integration remediation — independent exact-SHA review blockers

The independent review of browser commit `c2a67ab8bb9c362607632ceb17b194800b1d32fc` found three blockers. The integration worker added regression tests before each production fix.

### Stop-owned analyze timeout and content-free browser errors

RED command:

```text
node --test apps/web/tests/lifecycle.test.mjs
```

Observed RED: module instantiation failed because `safeAnalyzeError` was not exported. The same test change also required the camera resource owner to expose and stop-clear the active analyze timeout, and statically rejected `data.message_key` / `data.error` rendering.

GREEN command:

```text
node --check apps/web/app.js && npm run test:web
```

Observed GREEN: 8 passed, 0 failed. Stop/Retake/pagehide/beforeunload/hidden/track-ended now clear the owned analyze timeout even while frame capture is pending; stale completion cannot clear a newer request timeout. Non-2xx responses map status only to fixed local copy and never render server-controlled fields.

### Exact web Host boundary

RED command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_local_web_launcher.py -q
```

Observed RED: 6 failed, 5 passed. Hostile and malformed Host values reached static-file handling and returned 404 instead of a boundary rejection.

GREEN command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_local_web_launcher.py -q
```

Observed GREEN: 11 passed. The launcher accepts exactly `127.0.0.1:<bound-port>` or `localhost:<bound-port>` and returns a fixed content-free 403 for missing, hostile, malformed, userinfo-like, comma-joined, suffix-confusion, and wrong-authority Host values.

### Cross-surface privacy canary

Command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_b25_privacy_canaries.py -q
```

Observed: 1 passed on first execution. This is coverage evidence, not fabricated RED. Unmistakable barcode-payload, absolute-local-path, hostile-Origin/Host, and exception-message sentinels were injected. The test proves absence from Host/Origin/analyzer/resource endpoint responses, resource metrics, response `repr`, captured default logs/stdout/stderr, and a temporary persistence surface.

Integrated focused command:

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_api_loopback_boundary.py tests/python/test_barcode_api.py tests/python/test_b25_privacy_canaries.py tests/python/test_local_web_launcher.py tests/python/test_resource_measurement.py -q
```

Observed: 66 passed.

## Integrated final verification before exact-SHA review

- `uvx --from uv==0.11.31 uv run pytest -q` — 386 passed, 1 skipped.
- `uvx --from uv==0.11.31 uv run ruff check .` — all checks passed.
- `uvx --from uv==0.11.31 uv run ruff format --check .` — 30 files already formatted.
- `npm run contracts:check` — generated contract types in sync.
- `npm run test:ts` — 149 passed, 0 failed, including 8 browser lifecycle tests.
- `npm run typecheck` — passed.
- `npm run format:check` — all matched files use Prettier formatting.
- `npm audit --audit-level=high` — 0 vulnerabilities.
- `uvx --from uv==0.11.31 uv run python scripts/check_sensitive_files.py` — passed for 243 tracked files.
- `uvx --from uv==0.11.31 uv run python scripts/measure_live_resources.py --iterations 5 --width 512 --height 384` — exit 0; 5 successful analyses, 0 failed, content-free JSON only.
- `git diff --check` — passed.
- Added-file media/model/database scan — no new JPEG/PNG/GIF/WebP/video, SQLite/database, ONNX, or model-weight files.
- Added-line security scan — no hardcoded-secret, shell-injection, `eval`/`exec`, or unsafe-deserialization patterns.
- Scope-token review — the sole added B26 mention is the README's explicit exclusion; no LAN listener, persistence implementation, decode path, PaddleOCR, or B26 implementation was added.

Live launcher smoke used the real servers. API startup reported `Uvicorn running on http://127.0.0.1:8000`; the web server reported `('127.0.0.1', 5173)`. Observed statuses were API health 200, API resources 200, hostile API Host 403, web root 200, and hostile web Host 403. Both servers were then stopped.
