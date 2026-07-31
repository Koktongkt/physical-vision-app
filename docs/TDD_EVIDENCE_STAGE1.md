# Stage 1 TDD evidence

Date: 2026-07-31. Commands were run in the isolated `feat/stage1-executable-contracts` worktree.

## Representative RED observations

1. `uv run pytest tests/python/test_contracts.py::test_complete_vision_evidence_snapshot_is_valid -v`
   - Failed during collection with `ModuleNotFoundError: No module named 'physical_vision_contracts'` before the first schema/validator implementation.
2. `uv run pytest tests/python/test_contracts.py::test_automatic_completion_result_with_full_provenance_is_valid -v`
   - Failed with `ContractValidationError: unknown contract kind: analysis-result` before result, policy, completion, and reference validation existed.
3. `uv run pytest tests/python/test_contracts.py -q`
   - The expanded fixture suite initially reported two intended-reason mismatches (`text-outside-label.json` and case-sensitive `Additional properties`), proving the negative manifest assertions were active; fixture intent was corrected without weakening validation.
4. `npm run test:ts`
   - Failed with `ERR_MODULE_NOT_FOUND` for `packages/contracts/src/validator.mjs` before the JavaScript/TypeScript consumer existed.
5. `npm run typecheck`
   - Failed with TS2308 duplicate wildcard exports after the first generated-type pass; the generator was narrowed to explicit authoritative top-level type exports.
6. `uv run pytest tests/python/test_contracts.py::test_complete_vision_evidence_snapshot_is_valid -v`
   - Failed because calibrated support and label-confidence fields were initially rejected as additional properties; the schema then gained explicit finite `[0,1]` boundaries and negative fixtures.
7. `uv run pytest tests/python/test_contracts.py -q`
   - The mismatched result recommendation fixture failed with `DID NOT RAISE` before both semantic consumers enforced exact identity with the single policy primary action.
8. `uv run pytest tests/python/test_contracts.py -q`
   - Two automatic-completion fixtures failed with `DID NOT RAISE` before both consumers enforced verbatim final serial and calibrated-probability provenance.
9. `uv run python C:/Users/Tan19/AppData/Local/hermes/workspace/stage1_adversarial_repro.py`
   - Reported all five unsafe cases as `ACCEPT` and exited 1: automatic-source relabeling, automatic completion with a camera action, empty automatic serials, Windows-absolute storage keys, and self-supersession.
10. `uv run pytest tests/python/test_contracts.py -q` and `npm run test:ts`
    - Both paths reported `DID NOT RAISE` / `Missing expected exception` for the source/status, action, and Windows-storage-key fixtures before the parity fixes.
11. Targeted empty-serial and self-supersession fixture commands in both language paths
    - Each failed with `DID NOT RAISE` / `Missing expected exception` before its minimal semantic fix.
12. `uv run pytest tests/python/test_sensitive_files.py -q`
    - Five common credential shapes failed detection before the tracked-file scanner was expanded.
13. Python and Node fixture suites with `user-source-non-user-status.json`
    - Failed with `DID NOT RAISE` / `Missing expected exception` before user-originated completion sources were required to use `status=user_complete`.
14. Python and Node fixture suites with `completed-with-capture-false.json`
    - Failed with `DID NOT RAISE` / `Missing expected exception` before every linked completion required `capture_complete=true`.
15. Fresh exact-commit adversarial review of `ab8f1cc`
    - Independently accepted unavailable passing evidence, incomplete outcome/failure mappings, cross-task completion linkage, JavaScript-unsafe sequence identities, Windows-reserved storage segments, equal-fingerprint idempotency conflicts, and non-UTC timestamps before the expanded shared corpus and parity validators.
16. Expanded Python and Node invalid-fixture manifests
    - The review-driven RED slice initially left 26 expected failures. A later parent `npm run test:ts` run observed 10 remaining failures: two unsafe integer cases were still accepted and eight documents were rejected for an earlier unintended invariant. The schema bounds, single-purpose fixture setup, and canonical intended-reason diagnostics were then corrected without removing the underlying checks.
17. `uvx --from uv==0.11.31 uv run pytest tests/python/test_contracts.py::test_python_contract_types_expose_every_schema_required_field -q`
    - The final schema-to-`TypedDict` regression gate passed only after all six public Python top-level contract types exposed exactly the authoritative schema-required keys; this closes the independent type-conformance finding.
18. Fresh exact-commit review of `2bfe402d2c56bb425f5315e1f7f544eca95ec24f`
    - The isolated 74-case adversarial harness found 13 violated expectations: JavaScript freshness rounding accepted stale automatic evidence; candidate readiness trusted stale/unknown/failing evidence and empty candidates; the status/action/candidate/eligibility/capture matrix admitted five incompatible states; and failure code/category coherence was not enforced.
19. Shared regression corpus before the second remediation
    - `uvx --from uv==0.11.31 uv run pytest -q` reported exactly `13 failed, 100 passed`.
    - `npm run test:ts` reported exactly `13` failed and `86` passed.
    - The same 13 newly checked-in fixtures failed in both language paths, proving the intended RED state before validator/schema changes.
20. Fresh exact-commit review of `fcc7be06772315ab6d7d7d4815e153b3824573b5`
    - The prior 74-case corpus stayed green, but a new 371-case exhaustive outcome/boundary matrix found contradictory terminal actions, user automatic relabeling, hidden candidates, success-with-failure states, incomplete failure requirements, synchronized displayed-string rewrites, whitespace-only candidates, and four additional JavaScript-unsafe integers.
21. Third shared RED cycle
    - The first nine exact blocker/boundary fixtures produced `9 failed, 113 passed` in Python and `9 failed, 99 passed` in Node.
    - Twelve additional exhaustive-matrix fixtures then produced `12 failed, 122 passed` in Python and `12 failed, 108 passed` in Node before the terminal/failure/candidate matrix was completed.
22. Fresh exact-commit review of `c9b5d8284db60ab809045189fef82240307f1f1e`
    - A new 138-case supplemental matrix found one remaining contradiction: `user_complete` accepted a null result-level serial candidate while claiming candidate readiness and immutable completion.
    - The checked-in symmetric fixture produced exactly `1 failed, 134 passed` in Python and `1 failed, 120 passed` in Node before the minimal status-specific non-null requirement.

## GREEN observations

- Snapshot tracer: `1 passed`.
- Full automatic-completion tracer: `1 passed`.
- Final Python suite: `135 passed`.
- Final Node cross-language fixture suite: `121 passed`.
- Python schema-to-`TypedDict` conformance: `6 passed` within the full suite.
- Adversarial reproduction: five `REJECT` results and `UNSAFE_ACCEPT_COUNT=0`.
- Fresh 74-case exact-review harness after the second remediation: `violations=0`, `acceptance_parity_failures=0`, `value_drifts=0`, and no typed-key mismatch.
- Corrected 371-case novel outcome/boundary harness after the third remediation: `violations=0`, `acceptance_parity_failures=0`, and `value_drifts=0`.
- Fresh 38-case boundary suite: `violations=0`, `acceptance_parity_failures=0`, and `value_drifts=0`.
- Fresh 138-case supplemental outcome matrix after the final remediation: `violations=0` and `acceptance_parity_failures=0`.
- `npm run contracts:generate && npm run contracts:check && npm run typecheck`: generated types updated, drift check in sync, typecheck passed.
- `npm audit --audit-level=moderate`: `found 0 vulnerabilities` after pinning AJV 8.20.0.

Final clean-suite results are also recorded in the pull request and Kanban review handoff. This document records observed output only; it does not assert unexecuted checks.
