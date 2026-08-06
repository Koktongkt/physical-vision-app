# Physical Vision Policy

`packages/policy/python/physical_vision_policy` implements the thin B04 pure policy boundary for validated v3.1 evidence.

Public API:

- `PolicyConfig`: frozen, versioned policy configuration with explicit evaluation time, PET, priorities, costs, and tie keys.
- `DEFAULT_POLICY_CONFIG`: the frozen `policy-v31` / `auto-exact-pet-v1` configuration.
- `evaluate_snapshot(snapshot, config)`: validates one v3.1 snapshot and returns one recursively immutable, contract-valid v3.1 decision mapping.
- `decision_to_document(decision)`: creates a detached JSON-compatible decision document for validators or transport.
- `canonical_decision_json(decision)`: serializes the immutable decision deterministically.
- `PolicyInputError`: rejects stale/current-attempt, policy/threshold-incompatible, or unregistered configuration semantics.

The package uses only the Python standard library plus the existing shared contract package. It does not author prose, read ambient time/environment state, perform network or business-service I/O, create a completion, or mutate evidence. The shared validator reads the checked-in contract schemas before policy evaluation.

See `docs/POLICY_ORDER_V1.md` for the normative implementation order and `packages/policy/fixtures/manifest.json` for frozen replay vectors.
