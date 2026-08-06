# Deterministic Policy Order V1

## Scope

This document freezes the thin B04 policy implemented by `physical_vision_policy`. It consumes one semantically validated `VisionEvidenceSnapshot` v1.1 (`schema_version=3.1`) and one immutable `PolicyConfig`, and emits one immutable `PolicyDecision` v1.1. It does not implement admission, transport, privacy, resource, provenance-flow, persistence, completion creation, UI wording, overlays, or physical-guidance qualification.

## Admission boundary

The policy first invokes the shared Python contract validator. Schema-invalid, semantically incoherent, non-finite, or unsupported-version snapshots are rejected. It then rejects:

1. evidence not marked as the current attempt;
2. evidence whose `age_ms` is greater than `max_age_ms` (the exact cutoff remains admissible);
3. `policy_compatible` values that do not equal the config's `policy_version`; and
4. `threshold_compatible` values that do not equal the config's `threshold_version`.

The policy does not repair or normalize rejected evidence.

## Resolution order

Applicable outcomes are collected independently and sorted by the frozen `outcome_priorities` value. Lower values win:

| Group                 | Priority | Result                                                                            |
| --------------------- | -------: | --------------------------------------------------------------------------------- |
| `unsupported_subject` |       10 | Positively unsupported support evidence -> `unsupported_subject` / `unable`       |
| `unknown_support`     |       20 | Unknown or OOD support -> `manual_required` / `manual`                            |
| `localization`        |       30 | No label -> `no_label`; multiple labels -> `ambiguous_label`; uncertain -> manual |
| `guidance`            |       40 | One `reliable` typed correction -> `guidance` with that camera action             |
| `ocr_uncertain`       |       50 | Unreadable or ambiguous OCR -> `ocr_uncertain` / `none`                           |
| `candidate`           |       60 | All gates and a verbatim non-empty candidate -> candidate or automatic outcome    |
| `manual_fallback`     |       70 | No safe preceding outcome -> `manual_required` / `manual`                         |

This ordering is independent of object/dictionary insertion order. A reliable correction is evidence for exactly its one typed camera action; the policy never derives a direction from quality gates. A null or unreliable correction cannot produce directional guidance.

## Candidate and automatic gates

`gate_outcomes` is a deterministic conjunction of:

- supported, in-distribution support evidence;
- trustworthy localization;
- every non-OCR quality gate passing;
- passing OCR-integrity quality and `ocr.reason=usable`;
- current evidence with `age_ms <= max_age_ms`;
- verbatim raw/displayed OCR with neither silent repair nor candidate mutation;
- no pending correction candidate for completion safety;
- no unknown support, OOD, localization, quality, or OCR blocker; and
- exact policy/threshold compatibility.

A candidate is ready only when every gate passes and the verbatim OCR value is non-empty. Automatic eligibility additionally requires calibrated whole-string exact probability strictly greater than `0.80`. Exactly `0.80` is candidate-ready but not automatic. Format and checksum warnings do not authorize, repair, or veto the candidate; they remain warning-only evidence.

When both candidate and automatic outcomes are safe, the frozen costs select one:

- `automatic_complete`: 0
- `ready_for_verification`: 10
- `guidance`: 20
- `manual_required`: 100

Equal costs use this stable tie order: `automatic_complete`, `ready_for_verification`, `guidance`, `manual_required`. The final lexical status/action key is a last deterministic fallback. Before evaluation, the policy requires exact built-in tuple, string, integer, and float runtime types and rejects scalar subclasses, booleans used as integers, and coercible container alternatives. The only registered B04 configuration is `policy-v31` with the exact threshold version/value and priority/cost/tie vectors listed here; incomplete, duplicate, unknown, or value-altered entries fail closed. Validation and selection use private registry constants independent of the exported default config object, and resolution never executes caller-owned comparison objects. Snapshot evidence is recursively detached into exact JSON built-ins before contract validation or policy selection, so validated caller mappings cannot change behavior between phases. A different semantic vector requires a separately implemented and registered policy version rather than changing a label in caller data.

## Identity, time, and immutability

`evaluated_at` is an explicit config fact; the policy does not read a clock. `decision_id` is the first 24 hexadecimal characters of SHA-256 over canonical JSON containing the complete snapshot and config (`sort_keys=true`, compact separators, UTF-8, non-finite numbers forbidden). Consequently, changing any canonical snapshot/config fact changes the identity while identical inputs replay byte-identically.

`PolicyConfig` is a frozen dataclass containing only immutable tuples. Private registry constants remain authoritative even if a caller uses Python reflection to replace a field on the exported default object; the altered object then fails validation. The returned decision is a recursively immutable `FrozenMapping` without a mutable `dict` base class and blocks backing-slot reassignment after construction. `decision_to_document()` creates a detached JSON-compatible copy for contract validation or transport, and `canonical_decision_json()` provides deterministic serialization. The input snapshot is never mutated.

## Versioning rule

Any threshold, outcome priority, fixed cost, tie key, evaluated-time convention, gate meaning, or identity algorithm change requires a new `policy_version`, updated frozen vectors, and Python/Node parity verification. The `0.80` value remains a Product Owner-approved PET, not a validated accuracy or production claim.
