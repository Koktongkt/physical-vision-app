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

## GREEN observations

- Snapshot tracer: `1 passed`.
- Full automatic-completion tracer: `1 passed`.
- Python suite: `39 passed`.
- Node cross-language fixture suite: `37 passed`.
- `npm run contracts:generate && npm run contracts:check && npm run typecheck`: generated types updated, drift check in sync, typecheck passed.
- `npm audit --audit-level=moderate`: `found 0 vulnerabilities` after pinning AJV 8.20.0.

Final clean-suite results are also recorded in the pull request and Kanban review handoff. This document records observed output only; it does not assert unexecuted checks.
