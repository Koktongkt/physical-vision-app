# Stage 9 B26 TDD evidence

Scope: versioned manifest/report validation, canonical locking, deterministic grouped aggregation, privacy canaries, and an omitted public-supplement report. Base was verified clean at `af0541ea8f69bcf665aac9135017b6600906fb50` before implementation.

No live physical observation was created or inferred. Status remains `protocol_only` / `live_pending`; the public supplement is `public_supplement_omitted` because image rights and provenance were not established.

## Observed RED → GREEN slices

1. Manifest contract and lock
   - RED: `uvx uv@0.11.31 run --frozen pytest tests/python/test_b26_study.py -v`
   - Observed: collection failed with `ModuleNotFoundError: No module named 'physical_vision_study'`.
   - GREEN after minimal package plus canonical lock: two tests collected; the mutation test passed and dry-run rejection exposed a too-generic diagnostic. After moving the explicit check before exact-key validation: `2 passed`.

2. Deterministic aggregation and track separation
   - RED: `.venv/Scripts/python.exe -m pytest tests/python/test_b26_study.py -v`
   - Observed: collection failed because `aggregate_live_report` did not exist.
   - GREEN: deterministic reverse-order rerun, full session accounting, physical-item grouping, fixed-seed intervals, and live/public fingerprint gates passed: `4 passed`.

3. Privacy canaries and omitted public execution
   - RED: the focused file produced six expected failures: five unsafe manifest values were accepted and `scripts/run_b26_study.py` did not exist.
   - GREEN: content-free validators plus the public CLI yielded `10 passed`.

4. Honest status and observation-surface privacy
   - RED: all-missing rows incorrectly produced `completed_locked_run`; an unsafe observation action reached later accounting instead of failing at the privacy boundary.
   - GREEN: no analyzed observation now produces `live_pending`, and observation privacy validation fails before aggregation; the focused file passed.

5. Exact manifest version/operator shape
   - RED: deleting the browser version did not fail validation.
   - GREEN: exact required version and pseudonymous operator fields are validated; the focused file passed.

6. Required aggregate tables
   - RED: deterministic aggregate lacked count confusion, latency, transition, and capture-path subgroup tables (`KeyError: 'count_confusion'`).
   - GREEN: those content-free summaries were added and all 13 focused tests passed.

7. Strict report coherence
   - RED: a `completed_locked_run` report with zero analyzed observations and an incomplete public claim boundary both validated.
   - GREEN: report status/denominator coherence, proportion consistency, and exact public claim boundaries are now enforced; all 15 focused tests passed.

## Current focused result

```text
.venv/Scripts/python.exe -m pytest tests/python/test_b26_study.py -q
15 passed
```

Final repository-wide gates are recorded in the PR and task handoff after execution. This file never claims unexecuted gates passed.
