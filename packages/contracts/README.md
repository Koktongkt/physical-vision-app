# Executable contract v3.0

`schemas/v3.0/*.schema.json` are the language-neutral authority and use JSON Schema Draft 2020-12. The schemas separately version evidence, policy decisions, analysis results, completions/supersession, failures, and retained-photo deletion lifecycle records. Unknown fields are rejected.

## Authority and compatibility

The contract major/minor is `3.0`; component document versions are `1.0`. Consumers must reject unsupported major versions. Compatible additive changes require a new minor contract directory and regenerated consumers. Completion semantics, status meaning, evidence gates, retention, or coordinate conventions require the specification change-control process before a schema major/minor change.

JSON Schema enforces structure, enums, ranges, required fields, and conditional shapes. `physical_vision_contracts.validate_document` and `src/validator.mjs` add only cross-field semantic validation: normalized containment, immutable identity/version linkage, freshness, gate conjunction, strict PET comparison, verbatim candidates, completion linkage, and supersession. These validators do not choose guidance or run model inference. The later deterministic policy package consumes validated evidence and produces a separate decision.

The `0.80` threshold is explicitly `threshold_classification=PET`. It is not a validated accuracy or production claim. Automatic completion requires calibrated whole-string probability strictly greater than `0.80`, every enumerated current gate, current compatible versions, no unknown/blocker, and full immutable completion provenance.

## Commands

```text
uv sync --frozen --python 3.11
npm ci --ignore-scripts
npm run contracts:generate   # intentionally update generated TypeScript
npm run contracts:check      # fail on generated drift
uv run pytest
npm run test:ts
npm run typecheck
```

The checked-in generated TypeScript under `src/generated` must never be edited manually. Python exposes typed contract boundaries plus Draft 2020-12 and semantic validation. Both runtime paths execute the same fixture manifests, proving schema and semantic conformance across languages.

## Fixtures

`fixtures/valid/manifest.json` lists documents that must pass. `fixtures/invalid/manifest.json` lists documents that must fail and the intended diagnostic fragment. `NaN` and `Infinity` fixtures intentionally represent malformed JSON input; the JavaScript path rejects them during parse and Python explicitly rejects non-finite values.

Fixture serials, hashes, IDs, and timestamps are synthetic. No photos, real serials, evaluation records, datasets, or model artifacts belong here.
