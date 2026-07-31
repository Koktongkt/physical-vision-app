# Repository rules

## Normative sources

1. `docs/IMPLEMENTATION_SPEC.md` is the normative implementation specification.
2. `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md` is supporting research, not permission to override the normative specification.
3. Record material architectural decisions in `docs/adr/` and retain traceability to the applicable specification sections.
4. If code, tests, or prose conflict with the normative specification, stop and resolve the conflict explicitly; do not silently reinterpret requirements.

## Scope and safety

- Keep this repository local-first and privacy-conscious.
- Never commit real photos, serial numbers, evaluation records, databases, credentials, environment files, generated media, model weights, or local runtime state.
- Store only data/model manifests in the tracked `data/` and `models/` trees.
- Do not claim a dataset, model, dependency, or weight is cleared for use or redistribution without recorded evidence in `docs/PROVENANCE.md`.
- Preserve immutable evidence and correction provenance required by the normative specification.
- Do not implement automatic completion, policy shortcuts, OCR correction, or confidence behavior that weakens the specification's gates.

## Change discipline

- Make focused changes in the appropriate workspace boundary.
- Keep public contracts versioned and shared through `packages/contracts`.
- Keep deterministic decision and safety logic in `packages/policy`; model outputs are evidence, not policy decisions.
- Add or update tests for every behavioral change and regression fix.
- Avoid new dependencies unless their need, license, provenance, and operational cost are documented.

## Required verification

Before declaring a change complete, run the relevant formatter, linter, type checks, unit/integration tests, security checks, and build. Exercise the changed path when possible. Report exact commands and outcomes; never claim unexecuted checks passed. Confirm `git status --short` contains no sensitive or accidental files before commit.
