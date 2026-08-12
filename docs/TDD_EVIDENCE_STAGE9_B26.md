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

8. Semantic review remediation
   - RED: `.venv/Scripts/python.exe -m pytest tests/python/test_b26_study.py -q`
   - Observed: `40 failed, 16 passed`. Product action values such as `camera_closer` were rejected while fictional `move_*` / `tilt` values were accepted; multiple actions were permitted; intermediate rows could not be represented; session ordering/termination and exclusion-reason aggregation were not enforced; and adversarial nested report mutations reached an under-validating `validate_report`.
   - GREEN: the same focused command produced `56 passed in 0.36s` after binding the action allowlist to the product `BarcodeGuidanceAction` non-`NONE` values, enforcing one-action and coherent contiguous terminal sequencing, retaining separate missing/exclusion reason totals, and validating exact nested report shapes/types/ranges and cross-field sums.
   - The RED run and all GREEN work used synthetic contract fixtures only. No live observation was collected, inferred, or added, and no B26 validation claim is made.

## Current focused result

9. Final bounded protocol remediation
   - RED: `.venv/Scripts/python.exe -m pytest tests/python/test_b26_study.py -q`
   - Observed: `62 failed, 17 passed`. Representative failures showed the old implementation did
     not accept the exact 24-session fixture, accepted insufficient lock metadata and public-report
     validation, exposed the public bootstrap override, and did not enforce full-run completion.
   - GREEN after the minimal manifest/lock/aggregation/report/CLI changes: `79 passed in 1.10s`.
   - Tests monkeypatch the private bootstrap sampler only; the public aggregation API and emitted
     report remain locked to seed `260826` and 10,000 replicates. Fixtures are synthetic contract
     data only; no live evidence or validation claim was created.

10. Observation coherence and report metric cross-binding
    - RED: `uvx --from uv==0.11.31 uv run pytest tests/python/test_b26_study.py -q`
    - Observed: `18 failed, 86 passed in 1.90s`. The failures showed that target-support and
      localization types/coherence, nonnegative latency, human/system ready-guidance-veto
      relationships, and unsafe `not_evaluable` accounting were not enforced. The report had no
      independent evidence surface with which to reject forged derived metrics.
    - GREEN: the same focused command produced `104 passed in 1.57s` after minimal observation
      validation, safety eligibility accounting, and exact report-v2 `metric_evidence` counters
      cross-bound to every metric numerator and denominator. Adversarial tests mutate every metric
      and every evidence counter.
    - This RED/GREEN used synthetic contract fixtures only and creates no live or public evidence.

```text
uvx --from uv==0.11.31 uv run pytest tests/python/test_b26_study.py -q
104 passed in 1.57s
```

Final repository-wide gates are recorded in the PR and task handoff after execution. This file never claims unexecuted gates passed.
