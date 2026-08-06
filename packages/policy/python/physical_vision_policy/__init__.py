from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, TypeVar

from physical_vision_contracts import (
    PolicyDecisionV31,
    VisionEvidenceSnapshotV31,
    validate_document,
)

T = TypeVar("T")


class PolicyInputError(ValueError):
    """Validated evidence is not admissible for this policy evaluation."""


class FrozenMapping(Mapping[str, Any]):
    """Read-only mapping with no mutable ``dict`` base-class escape hatch."""

    __slots__ = ("__data",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_FrozenMapping__data", MappingProxyType(dict(values)))

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __getitem__(self, key: str) -> Any:
        return self.__data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return dict(self.items()) == dict(other.items())

    def __repr__(self) -> str:
        return f"FrozenMapping({dict(self.items())!r})"


def _freeze(value: T) -> T:
    if isinstance(value, Mapping):
        return FrozenMapping({key: _freeze(child) for key, child in value.items()})  # type: ignore[return-value]
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)  # type: ignore[return-value]
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def decision_to_document(decision: Mapping[str, Any]) -> PolicyDecisionV31:
    """Return a detached JSON-compatible document for validation or transport."""
    return _thaw(decision)


def canonical_decision_json(decision: Mapping[str, Any]) -> str:
    """Serialize one immutable decision deterministically for replay or transport."""
    return json.dumps(
        decision_to_document(decision),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    policy_version: str
    threshold_version: str
    auto_threshold: float
    evaluated_at: str
    outcome_priorities: tuple[tuple[str, int], ...]
    fixed_costs: tuple[tuple[str, int], ...]
    tie_break_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Resolution:
    group: str
    status: str
    action: str


_POLICY_VERSION = "policy-v31"
_THRESHOLD_VERSION = "auto-exact-pet-v1"
_AUTO_THRESHOLD = 0.8
_OUTCOME_PRIORITIES = (
    ("unsupported_subject", 10),
    ("unknown_support", 20),
    ("localization", 30),
    ("guidance", 40),
    ("ocr_uncertain", 50),
    ("candidate", 60),
    ("manual_fallback", 70),
)
_FIXED_COSTS = (
    ("automatic_complete", 0),
    ("ready_for_verification", 10),
    ("guidance", 20),
    ("manual_required", 100),
)
_TIE_BREAK_ORDER = (
    "automatic_complete",
    "ready_for_verification",
    "guidance",
    "manual_required",
)

DEFAULT_POLICY_CONFIG = PolicyConfig(
    policy_version=_POLICY_VERSION,
    threshold_version=_THRESHOLD_VERSION,
    auto_threshold=_AUTO_THRESHOLD,
    evaluated_at="2026-08-01T10:00:01Z",
    outcome_priorities=_OUTCOME_PRIORITIES,
    fixed_costs=_FIXED_COSTS,
    tie_break_order=_TIE_BREAK_ORDER,
)

_EXPECTED_OUTCOME_GROUPS = frozenset(name for name, _ in _OUTCOME_PRIORITIES)
_EXPECTED_COST_STATUSES = frozenset(name for name, _ in _FIXED_COSTS)
_EXPECTED_TIE_STATUSES = frozenset(_TIE_BREAK_ORDER)


def _require_exact_keys(label: str, keys: tuple[str, ...], expected: frozenset[str]) -> None:
    if len(keys) != len(expected) or frozenset(keys) != expected:
        raise PolicyInputError(
            f"policy config {label} must contain each supported key exactly once"
        )


def _validate_config_shape(config: PolicyConfig) -> None:
    if type(config) is not PolicyConfig:
        raise PolicyInputError("policy config must use the registered PolicyConfig type")
    if (
        any(
            type(value) is not str
            for value in (config.policy_version, config.threshold_version, config.evaluated_at)
        )
        or type(config.auto_threshold) is not float
    ):
        raise PolicyInputError("policy config scalar types must be exact built-in types")
    for label, entries in (
        ("outcome priorities", config.outcome_priorities),
        ("fixed costs", config.fixed_costs),
    ):
        if type(entries) is not tuple or any(
            type(entry) is not tuple
            or len(entry) != 2
            or type(entry[0]) is not str
            or type(entry[1]) is not int
            for entry in entries
        ):
            raise PolicyInputError(
                f"policy config {label} must use exact tuple, str, and int types"
            )
    if type(config.tie_break_order) is not tuple or any(
        type(name) is not str for name in config.tie_break_order
    ):
        raise PolicyInputError("policy config tie-break order must use exact tuple and str types")


def _validate_config(config: PolicyConfig) -> None:
    _validate_config_shape(config)
    _require_exact_keys(
        "outcome priorities",
        tuple(name for name, _ in config.outcome_priorities),
        _EXPECTED_OUTCOME_GROUPS,
    )
    _require_exact_keys(
        "fixed costs",
        tuple(name for name, _ in config.fixed_costs),
        _EXPECTED_COST_STATUSES,
    )
    _require_exact_keys("tie-break order", config.tie_break_order, _EXPECTED_TIE_STATUSES)
    frozen_semantics = (
        config.policy_version,
        config.threshold_version,
        config.auto_threshold,
        config.outcome_priorities,
        config.fixed_costs,
        config.tie_break_order,
    )
    expected_semantics = (
        _POLICY_VERSION,
        _THRESHOLD_VERSION,
        _AUTO_THRESHOLD,
        _OUTCOME_PRIORITIES,
        _FIXED_COSTS,
        _TIE_BREAK_ORDER,
    )
    if frozen_semantics != expected_semantics:
        raise PolicyInputError("policy config semantics are not registered for policy-v31")


def _decision_id(snapshot: VisionEvidenceSnapshotV31, config: PolicyConfig) -> str:
    canonical = json.dumps(
        {"config": asdict(config), "snapshot": snapshot},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"decision-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def _gate_outcomes(snapshot: VisionEvidenceSnapshotV31) -> dict[str, bool]:
    quality = snapshot["quality"]
    quality_names = tuple(name for name in quality if name != "ocr_integrity")
    no_unknown = (
        snapshot["support"]["state"] != "unknown"
        and snapshot["support"]["ood_state"] == "in_distribution"
        and snapshot["localization"]["state"] != "unknown"
        and snapshot["ocr"]["reason"] == "usable"
        and all(gate["state"] != "unknown" for gate in quality.values())
    )
    return {
        "support": snapshot["support"]["reason"] == "supported",
        "localization": snapshot["localization"]["reason"] == "trustworthy",
        "quality": all(quality[name]["state"] == "pass" for name in quality_names),
        "ocr_integrity": (
            quality["ocr_integrity"]["state"] == "pass" and snapshot["ocr"]["reason"] == "usable"
        ),
        "freshness": (
            snapshot["freshness"]["is_current_attempt"]
            and snapshot["freshness"]["age_ms"] <= snapshot["freshness"]["max_age_ms"]
        ),
        "format_policy": (
            not snapshot["ocr"]["silent_repair_applied"]
            and not snapshot["ocr"]["candidate_mutated"]
            and snapshot["ocr"]["raw_string"] == snapshot["ocr"]["displayed_string"]
        ),
        "deterministic_safety": snapshot["correction_candidate"] is None,
        "no_unknown_blocking": no_unknown,
        "version_compatibility": True,
    }


def _detach_json_value(value: Any) -> Any:
    """Copy caller data to exact built-ins before validation or policy execution."""
    if isinstance(value, Mapping):
        detached: dict[str, Any] = {}
        for key, child in value.items():
            if type(key) is not str:
                raise PolicyInputError("snapshot object keys must be exact built-in strings")
            detached[key] = _detach_json_value(child)
        return detached
    if isinstance(value, list | tuple):
        return [_detach_json_value(child) for child in value]
    if type(value) in (str, int, float, bool, type(None)):
        return value
    raise PolicyInputError("snapshot values must use JSON-compatible built-in types")


def evaluate_snapshot(
    snapshot: VisionEvidenceSnapshotV31,
    config: PolicyConfig,
) -> FrozenMapping:
    """Return one deterministic immutable decision for validated v3.1 evidence."""
    _validate_config(config)
    detached = _detach_json_value(snapshot)
    validated = validate_document("vision-evidence-snapshot", detached)
    freshness = validated["freshness"]
    if not freshness["is_current_attempt"] or freshness["age_ms"] > freshness["max_age_ms"]:
        raise PolicyInputError("snapshot is stale or not from the current attempt")
    if validated["versions"]["policy_compatible"] != config.policy_version:
        raise PolicyInputError("snapshot policy version is incompatible with configuration")
    if validated["versions"]["threshold_compatible"] != config.threshold_version:
        raise PolicyInputError("snapshot threshold version is incompatible with configuration")
    gates = _gate_outcomes(validated)
    all_required_gates_pass = all(gates.values())
    ocr = validated["ocr"]
    candidate_ready = bool(ocr["raw_string"].strip()) and all_required_gates_pass
    probability = ocr["whole_string_exact_probability_calibrated"]
    automatic_eligible = (
        candidate_ready and probability is not None and probability > _AUTO_THRESHOLD
    )
    resolutions = [_Resolution("manual_fallback", "manual_required", "manual")]
    support_reason = validated["support"]["reason"]
    localization_reason = validated["localization"]["reason"]
    if support_reason == "positively_unsupported":
        resolutions.append(_Resolution("unsupported_subject", "unsupported_subject", "unable"))
    elif support_reason == "unknown_or_ood":
        resolutions.append(_Resolution("unknown_support", "manual_required", "manual"))
    localization_outcomes = {
        "no_label": ("no_label", "none"),
        "multiple_labels": ("ambiguous_label", "none"),
        "uncertain": ("manual_required", "manual"),
    }
    if localization_reason in localization_outcomes:
        localization_status, localization_action = localization_outcomes[localization_reason]
        resolutions.append(_Resolution("localization", localization_status, localization_action))
    correction = validated["correction_candidate"]
    if correction is not None and correction["reliability"] == "reliable":
        resolutions.append(_Resolution("guidance", "guidance", correction["camera_action"]))
    if ocr["reason"] in {"unreadable", "ambiguous"}:
        resolutions.append(_Resolution("ocr_uncertain", "ocr_uncertain", "none"))
    if candidate_ready:
        resolutions.append(_Resolution("candidate", "ready_for_verification", "none"))
        if automatic_eligible:
            resolutions.append(_Resolution("candidate", "automatic_complete", "none"))

    priorities = dict(_OUTCOME_PRIORITIES)
    costs = dict(_FIXED_COSTS)
    tie_breaks = {name: index for index, name in enumerate(_TIE_BREAK_ORDER)}
    try:
        selected = min(
            resolutions,
            key=lambda item: (
                priorities[item.group],
                costs[item.status] if item.status in _EXPECTED_COST_STATUSES else 0,
                (
                    tie_breaks[item.status]
                    if item.status in _EXPECTED_TIE_STATUSES
                    else len(tie_breaks)
                ),
                item.status,
                item.action,
            ),
        )
    except KeyError as error:
        raise PolicyInputError(f"policy config lacks priority for {error.args[0]}") from error
    status, action = selected.status, selected.action
    selected_candidate_ready = candidate_ready and status in {
        "ready_for_verification",
        "automatic_complete",
    }
    decision: PolicyDecisionV31 = {
        "schema_version": "3.1",
        "decision_version": "1.1",
        "decision_id": _decision_id(validated, config),
        "result_id": validated["result_id"],
        "snapshot_id": validated["snapshot_id"],
        "policy_version": _POLICY_VERSION,
        "threshold_version": _THRESHOLD_VERSION,
        "threshold_classification": "PET",
        "auto_threshold_strictly_greater_than": _AUTO_THRESHOLD,
        "status": status,
        "primary_action": {
            "kind": action,
            "referent": "camera" if status == "guidance" else None,
        },
        "gate_outcomes": gates,
        "all_required_gates_pass": all_required_gates_pass,
        "automatic_completion_eligible": automatic_eligible and status == "automatic_complete",
        "candidate_ready": selected_candidate_ready,
        "evaluated_at": config.evaluated_at,
    }
    validate_document("policy-decision", decision)
    return _freeze(decision)
