from __future__ import annotations

import inspect
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest
from physical_vision_contracts import validate_document
from physical_vision_policy import (
    DEFAULT_POLICY_CONFIG,
    PolicyInputError,
    canonical_decision_json,
    decision_to_document,
    evaluate_snapshot,
)

ROOT = Path(__file__).parents[2]
POLICY_FIXTURES = ROOT / "packages/policy/fixtures"


def load_v31_snapshot(name: str) -> dict[str, object]:
    path = ROOT / "packages/contracts/fixtures/v3.1/valid" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_positive_unsupported_evidence_is_terminal_before_other_failures() -> None:
    snapshot = load_v31_snapshot("positive-unsupported-no-label-unreadable.json")

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "unsupported_subject"
    assert decision["primary_action"] == {"kind": "unable", "referent": None}
    assert decision["automatic_completion_eligible"] is False
    assert decision["candidate_ready"] is False
    validate_document("policy-decision", decision_to_document(decision))


class _PolicyContextSwitchingDict(dict[str, object]):
    """Behave validly for contract code but lie when policy code reads the caller object."""

    def __getitem__(self, key: str) -> object:
        caller = inspect.currentframe().f_back
        if (
            key == "reason"
            and caller is not None
            and caller.f_code.co_filename.endswith("physical_vision_policy\\__init__.py")
        ):
            return "supported"
        return super().__getitem__(key)


def test_policy_executes_recursively_detached_snapshot_not_caller_mappings() -> None:
    snapshot = load_v31_snapshot("positive-unsupported-no-label-unreadable.json")
    snapshot["support"] = _PolicyContextSwitchingDict(snapshot["support"])
    snapshot["correction_candidate"] = {
        "camera_action": "camera_down",
        "reliability": "reliable",
    }

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "unsupported_subject"
    assert decision["primary_action"] == {"kind": "unable", "referent": None}


def test_no_label_is_distinct_from_ocr_failure() -> None:
    snapshot = load_v31_snapshot("positive-unsupported-no-label-unreadable.json")
    snapshot["support"] = {
        "state": "pass",
        "reason": "supported",
        "ood_state": "in_distribution",
        "probability_calibrated": 0.97,
    }

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "no_label"
    assert decision["primary_action"] == {"kind": "none", "referent": None}
    validate_document("policy-decision", decision_to_document(decision))


def test_stale_snapshot_is_rejected_instead_of_normalized() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["freshness"]["age_ms"] = snapshot["freshness"]["max_age_ms"] + 1

    with pytest.raises(PolicyInputError, match="stale"):
        evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)


def test_snapshot_version_compatibility_must_match_frozen_config() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["versions"]["policy_compatible"] = "policy-other"

    with pytest.raises(PolicyInputError, match="policy version"):
        evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)


def test_snapshot_threshold_compatibility_must_match_frozen_config() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["versions"]["threshold_compatible"] = "threshold-other"

    with pytest.raises(PolicyInputError, match="threshold version"):
        evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)


def test_reliable_correction_produces_exactly_one_camera_action() -> None:
    snapshot = load_v31_snapshot("reliable-camera-up-correction.json")

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "guidance"
    assert decision["primary_action"] == {"kind": "camera_up", "referent": "camera"}
    assert decision["candidate_ready"] is False
    validate_document("policy-decision", decision_to_document(decision))


def test_all_gates_and_probability_strictly_above_pet_are_automatic_eligible() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "automatic_complete"
    assert decision["primary_action"] == {"kind": "none", "referent": None}
    assert decision["all_required_gates_pass"] is True
    assert decision["automatic_completion_eligible"] is True
    assert decision["candidate_ready"] is True
    assert all(decision["gate_outcomes"].values())
    validate_document("policy-decision", decision_to_document(decision))


def test_probability_exactly_at_pet_is_candidate_ready_not_automatic() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["ocr"]["whole_string_exact_probability_calibrated"] = 0.8

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "ready_for_verification"
    assert decision["primary_action"] == {"kind": "none", "referent": None}
    assert decision["all_required_gates_pass"] is True
    assert decision["automatic_completion_eligible"] is False
    assert decision["candidate_ready"] is True
    validate_document("policy-decision", decision_to_document(decision))


def test_policy_preserves_inputs_and_returns_deeply_immutable_decision() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    before = json.dumps(snapshot, sort_keys=True)

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert json.dumps(snapshot, sort_keys=True) == before
    with pytest.raises(TypeError):
        decision["status"] = "manual_required"
    with pytest.raises(TypeError):
        decision["gate_outcomes"]["support"] = False
    with pytest.raises(TypeError):
        dict.__setitem__(decision, "status", "manual_required")
    with pytest.raises(TypeError):
        dict.__setitem__(decision["gate_outcomes"], "support", False)
    with pytest.raises((AttributeError, TypeError)):
        decision._FrozenMapping__data = MappingProxyType({"status": "manual_required"})
    assert decision_to_document(decision)["status"] == "automatic_complete"
    with pytest.raises((AttributeError, TypeError)):
        DEFAULT_POLICY_CONFIG.policy_version = "mutated"


def test_decision_identity_and_canonical_output_are_deterministic() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")

    canonical_replays = {
        canonical_decision_json(evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG))
        for _ in range(100)
    }
    other = load_v31_snapshot("vision-evidence-reasons.json")
    other["snapshot_id"] = "snapshot-other-synthetic"
    other["result_id"] = "result-other-synthetic"

    assert len(canonical_replays) == 1
    assert (
        evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)["decision_id"]
        != evaluate_snapshot(other, DEFAULT_POLICY_CONFIG)["decision_id"]
    )


def test_default_policy_configuration_freezes_priority_cost_and_tie_break_rules() -> None:
    assert DEFAULT_POLICY_CONFIG.outcome_priorities == (
        ("unsupported_subject", 10),
        ("unknown_support", 20),
        ("localization", 30),
        ("guidance", 40),
        ("ocr_uncertain", 50),
        ("candidate", 60),
        ("manual_fallback", 70),
    )
    assert DEFAULT_POLICY_CONFIG.fixed_costs == (
        ("automatic_complete", 0),
        ("ready_for_verification", 10),
        ("guidance", 20),
        ("manual_required", 100),
    )
    assert DEFAULT_POLICY_CONFIG.tie_break_order == (
        "automatic_complete",
        "ready_for_verification",
        "guidance",
        "manual_required",
    )


def test_registry_execution_is_independent_from_exported_config_object_mutation() -> None:
    snapshot = load_v31_snapshot("positive-unsupported-no-label-unreadable.json")
    snapshot["correction_candidate"] = {
        "camera_action": "camera_down",
        "reliability": "reliable",
    }
    original = DEFAULT_POLICY_CONFIG.outcome_priorities
    mutated = tuple(
        (name, 100 if name == "unsupported_subject" else 0 if name == "guidance" else rank)
        for name, rank in original
    )
    try:
        object.__setattr__(DEFAULT_POLICY_CONFIG, "outcome_priorities", mutated)
        with pytest.raises(PolicyInputError, match="policy config"):
            evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)
    finally:
        object.__setattr__(DEFAULT_POLICY_CONFIG, "outcome_priorities", original)

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)
    assert decision["status"] == "unsupported_subject"
    assert decision["primary_action"] == {"kind": "unable", "referent": None}


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("outcome_priorities", DEFAULT_POLICY_CONFIG.outcome_priorities[:-1]),
        (
            "outcome_priorities",
            DEFAULT_POLICY_CONFIG.outcome_priorities
            + (DEFAULT_POLICY_CONFIG.outcome_priorities[0],),
        ),
        (
            "outcome_priorities",
            DEFAULT_POLICY_CONFIG.outcome_priorities + (("unknown_group", 80),),
        ),
        ("fixed_costs", DEFAULT_POLICY_CONFIG.fixed_costs[:-1]),
        (
            "fixed_costs",
            DEFAULT_POLICY_CONFIG.fixed_costs + (DEFAULT_POLICY_CONFIG.fixed_costs[0],),
        ),
        ("fixed_costs", DEFAULT_POLICY_CONFIG.fixed_costs + (("unknown_status", 200),)),
        ("tie_break_order", DEFAULT_POLICY_CONFIG.tie_break_order[:-1]),
        (
            "tie_break_order",
            DEFAULT_POLICY_CONFIG.tie_break_order + (DEFAULT_POLICY_CONFIG.tie_break_order[0],),
        ),
        ("tie_break_order", DEFAULT_POLICY_CONFIG.tie_break_order + ("unknown_status",)),
    ),
)
def test_policy_config_collections_fail_closed_when_not_exact(
    field: str,
    value: tuple[object, ...],
) -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    malformed = replace(DEFAULT_POLICY_CONFIG, **{field: value})

    with pytest.raises(PolicyInputError, match="policy config"):
        evaluate_snapshot(snapshot, malformed)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        (
            "outcome_priorities",
            tuple(
                (name, 0 if name == "guidance" else 100 if name == "unsupported_subject" else rank)
                for name, rank in DEFAULT_POLICY_CONFIG.outcome_priorities
            ),
        ),
        (
            "fixed_costs",
            tuple(
                (
                    name,
                    20
                    if name == "automatic_complete"
                    else 0
                    if name == "ready_for_verification"
                    else cost,
                )
                for name, cost in DEFAULT_POLICY_CONFIG.fixed_costs
            ),
        ),
        ("tie_break_order", tuple(reversed(DEFAULT_POLICY_CONFIG.tie_break_order))),
        ("auto_threshold", 0.79),
        ("threshold_version", "auto-exact-pet-v2"),
    ),
)
def test_policy_v31_rejects_unversioned_semantic_drift(field: str, value: object) -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    altered = replace(DEFAULT_POLICY_CONFIG, **{field: value})

    with pytest.raises(PolicyInputError, match="policy config"):
        evaluate_snapshot(snapshot, altered)


class _DemotedInt(int):
    def __lt__(self, other: object) -> bool:
        return False


class _HostileFloat(float):
    def __gt__(self, other: object) -> bool:
        return True


class _HostileStr(str):
    pass


@pytest.mark.parametrize(
    ("field", "value"),
    (
        (
            "outcome_priorities",
            tuple(
                (name, _DemotedInt(rank) if name == "unsupported_subject" else rank)
                for name, rank in DEFAULT_POLICY_CONFIG.outcome_priorities
            ),
        ),
        (
            "fixed_costs",
            tuple(
                (name, _DemotedInt(cost) if name == "automatic_complete" else cost)
                for name, cost in DEFAULT_POLICY_CONFIG.fixed_costs
            ),
        ),
        (
            "tie_break_order",
            (_HostileStr("automatic_complete"),) + DEFAULT_POLICY_CONFIG.tie_break_order[1:],
        ),
        ("auto_threshold", _HostileFloat(0.8)),
        ("auto_threshold", 0),
        ("auto_threshold", True),
        (
            "fixed_costs",
            (("automatic_complete", False),) + DEFAULT_POLICY_CONFIG.fixed_costs[1:],
        ),
        ("outcome_priorities", list(DEFAULT_POLICY_CONFIG.outcome_priorities)),
        (
            "outcome_priorities",
            (["unsupported_subject", 10],) + DEFAULT_POLICY_CONFIG.outcome_priorities[1:],
        ),
    ),
)
def test_policy_config_rejects_non_exact_runtime_types(field: str, value: object) -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    hostile = replace(DEFAULT_POLICY_CONFIG, **{field: value})

    with pytest.raises(PolicyInputError, match="policy config"):
        evaluate_snapshot(snapshot, hostile)


def test_unregistered_cost_vector_is_rejected_even_with_matching_snapshot_label() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["versions"]["policy_compatible"] = "policy-cost-test"
    candidate_first = replace(
        DEFAULT_POLICY_CONFIG,
        policy_version="policy-cost-test",
        fixed_costs=(
            ("automatic_complete", 20),
            ("ready_for_verification", 0),
            ("guidance", 20),
            ("manual_required", 100),
        ),
    )

    with pytest.raises(PolicyInputError, match="policy config"):
        evaluate_snapshot(snapshot, candidate_first)


def test_unregistered_tie_vector_is_rejected_even_with_matching_snapshot_label() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["versions"]["policy_compatible"] = "policy-tie-test"
    tied = replace(
        DEFAULT_POLICY_CONFIG,
        policy_version="policy-tie-test",
        fixed_costs=(
            ("automatic_complete", 0),
            ("ready_for_verification", 0),
            ("guidance", 20),
            ("manual_required", 100),
        ),
    )

    with pytest.raises(PolicyInputError, match="policy config"):
        evaluate_snapshot(snapshot, tied)


def test_frozen_policy_vectors_match_and_validate_in_python_and_node() -> None:
    manifest = json.loads((POLICY_FIXTURES / "manifest.json").read_text(encoding="utf-8"))

    for case in manifest:
        snapshot = json.loads((POLICY_FIXTURES / case["snapshot"]).read_text(encoding="utf-8"))
        expected = json.loads((POLICY_FIXTURES / case["decision"]).read_text(encoding="utf-8"))
        decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

        assert decision == expected
        validate_document("policy-decision", decision_to_document(decision))
        completed = subprocess.run(
            [
                "node",
                "--input-type=module",
                "--eval",
                (
                    "import { validateDocument } from "
                    "'./packages/contracts/src/validator.mjs';"
                    "const chunks=[]; for await (const chunk of process.stdin) chunks.push(chunk);"
                    "validateDocument('policy-decision', JSON.parse(chunks.join('')));"
                ),
            ],
            cwd=ROOT,
            input=canonical_decision_json(decision),
            capture_output=True,
            check=False,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr


def test_unknown_support_outweighs_multiple_label_failure_and_abstains() -> None:
    snapshot = load_v31_snapshot("unknown-multiple-labels-ambiguous-ocr.json")

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "manual_required"
    assert decision["primary_action"] == {"kind": "manual", "referent": None}
    assert decision["automatic_completion_eligible"] is False


def test_known_out_of_distribution_evidence_sets_blocking_gate() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["support"] = {
        "state": "fail",
        "reason": "unknown_or_ood",
        "ood_state": "out_of_distribution",
        "probability_calibrated": None,
    }

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "manual_required"
    assert decision["gate_outcomes"]["no_unknown_blocking"] is False


def test_positive_unsupported_outweighs_reliable_camera_correction() -> None:
    snapshot = load_v31_snapshot("positive-unsupported-no-label-unreadable.json")
    snapshot["correction_candidate"] = {
        "camera_action": "camera_down",
        "reliability": "reliable",
    }

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "unsupported_subject"
    assert decision["primary_action"] == {"kind": "unable", "referent": None}


def test_unreliable_correction_abstains_from_directional_guidance() -> None:
    snapshot = load_v31_snapshot("reliable-camera-up-correction.json")
    snapshot["correction_candidate"]["reliability"] = "unreliable"

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "manual_required"
    assert decision["primary_action"] == {"kind": "manual", "referent": None}


def test_unknown_quality_vetoes_candidate_and_automatic_completion() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["quality"]["blur"]["state"] = "unknown"
    snapshot["quality"]["overall"]["state"] = "unknown"

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "manual_required"
    assert decision["gate_outcomes"]["quality"] is False
    assert decision["gate_outcomes"]["no_unknown_blocking"] is False
    assert decision["candidate_ready"] is False
    assert decision["automatic_completion_eligible"] is False


def test_freshness_at_exact_cutoff_remains_admissible() -> None:
    snapshot = load_v31_snapshot("vision-evidence-reasons.json")
    snapshot["freshness"]["age_ms"] = snapshot["freshness"]["max_age_ms"]

    decision = evaluate_snapshot(snapshot, DEFAULT_POLICY_CONFIG)

    assert decision["status"] == "automatic_complete"
    assert decision["gate_outcomes"]["freshness"] is True
