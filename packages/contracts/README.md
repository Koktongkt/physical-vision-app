# Executable contract v3.0

`schemas/v3.0/*.schema.json` are the language-neutral authority and use JSON Schema Draft 2020-12. The schemas separately version evidence, policy decisions, analysis results, completions/supersession, failures, and retained-photo deletion lifecycle records. Unknown fields are rejected.

## Authority and compatibility

The contract major/minor is `3.0`; component document versions are `1.0`. Consumers must reject unsupported major versions. Compatible additive changes require a new minor contract directory and regenerated consumers. Completion semantics, status meaning, evidence gates, retention, or coordinate conventions require the specification change-control process before a schema major/minor change.

JSON Schema is the structural interchange authority: it enforces structure, enums, ranges, required fields, and conditional shapes. The normative cross-field semantic rules are this document's rule list plus the shared valid/invalid fixture manifests. `physical_vision_contracts.validate_document` and `src/validator.mjs` must implement that same corpus identically for normalized containment, immutable identity/version linkage, freshness, gate conjunction, strict PET comparison, verbatim candidates, completion status/source/capture linkage, and supersession. A change to either semantic validator is incomplete until the same fixture proves both language paths. These validators do not choose guidance or run model inference. The later deterministic policy package consumes validated evidence and produces a separate decision.

The `0.80` threshold is explicitly `threshold_classification=PET`. It is not a validated accuracy or production claim. Automatic completion requires calibrated whole-string probability strictly greater than `0.80`, every enumerated current gate, current compatible versions, no unknown/blocker, and full immutable completion provenance.

Candidate readiness is also evidence-derived: it requires non-blank raw OCR text preserved exactly as the displayed candidate, current-attempt freshness, passing support/in-distribution OOD and localization evidence, every required quality/OCR-integrity measurement, compatible versions, and every current-attempt decision gate. `ready_for_verification` is capture-complete but never business-complete or automatically eligible. `guidance` requires exactly one camera action; `manual_required` requires `manual`; `unsupported_subject`, `unsupported_input`, and `internal_error` require `unable`; all remaining statuses require `none`. Only `ready_for_verification`, `automatic_complete`, and `user_complete` may carry a candidate or assert `capture_complete=true`, and user completion is never relabeled as automatically eligible. Guidance/waiting/success states cannot carry failures; OCR-uncertain, no-label, ambiguous-label, unsupported, and internal-error states require one. Freshness, retry, image-dimension, and deletion-attempt integers are bounded to JavaScript's exact integer range (`<= 9007199254740991`) in the authoritative schemas.

Failure code/category coherence is normative:

| Category              | Codes                                                                                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `capability`          | `PHOTO_PICKER_UNAVAILABLE`, `UPLOAD_UNAVAILABLE`                                                                                                                        |
| `not-found`           | `SESSION_EXPIRED`, `ATTEMPT_SUPERSEDED`, `NO_LABEL_FOUND`                                                                                                               |
| `ambiguous`           | `SEQUENCE_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `MULTIPLE_LABELS_AMBIGUOUS`, `OCR_AMBIGUOUS`                                                                               |
| `quality`             | `QUALITY_INSUFFICIENT`, `SERIAL_UNREADABLE`, `FORMAT_POLICY_MISMATCH`                                                                                                   |
| `unsupported-input`   | `UNSUPPORTED_MEDIA_TYPE`, `ANIMATED_OR_MULTIFRAME_UNSUPPORTED`, `INVALID_OR_CORRUPT_IMAGE`, `IMAGE_DIMENSIONS_UNSUPPORTED`, `INPUT_TOO_LARGE`, `DECODE_BUDGET_EXCEEDED` |
| `unsupported-subject` | `UNSUPPORTED_LABEL_OR_OBJECT`                                                                                                                                           |
| `unknown`             | `SUPPORT_UNKNOWN`                                                                                                                                                       |
| `timeout`             | `PROCESSING_TIMEOUT`                                                                                                                                                    |
| `local-resource`      | `LOCAL_STORAGE_LIMIT`                                                                                                                                                   |
| `deletion`            | `DELETION_PENDING`, `DELETION_FAILED`                                                                                                                                   |
| `dependency`          | `DEPENDENCY_UNAVAILABLE`                                                                                                                                                |
| `internal`            | `INTERNAL_PROCESSING_ERROR`                                                                                                                                             |

## Commands

Use CPython 3.11.15, uv 0.11.31, Node.js 24.14.1, and npm 11.12.1. The exact
runtime pins are recorded in `.python-version` and `.node-version`; the project
still supports CPython 3.11 through 3.14, so uv can create the pinned environment
even when the host Python is newer.

```text
npm install --global npm@11.12.1
uv sync --frozen --python 3.11.15
npm ci --ignore-scripts
npm run contracts:generate   # intentionally update generated TypeScript
npm run contracts:check      # fail on generated drift
uv run pytest
npm run test:ts
npm run typecheck
npm run format:check
```

The checked-in generated TypeScript under `src/generated` must never be edited manually. Python exposes typed contract boundaries plus Draft 2020-12 and semantic validation. Both runtime paths execute the same fixture manifests, proving schema and semantic conformance across languages.

Retained-photo `storage_key` values are canonical application-private POSIX-style relative keys. Absolute paths, backslashes, dot segments, and traversal are rejected at the contract boundary.

## Fixtures

`fixtures/valid/manifest.json` lists documents that must pass. `fixtures/invalid/manifest.json` lists documents that must fail and the intended diagnostic fragment. `NaN` and `Infinity` fixtures intentionally represent malformed JSON input; the JavaScript path rejects them during parse and Python explicitly rejects non-finite values.

Fixture serials, hashes, IDs, and timestamps are synthetic. No photos, real serials, evaluation records, datasets, or model artifacts belong here.
