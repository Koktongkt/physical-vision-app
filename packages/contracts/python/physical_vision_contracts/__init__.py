from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SCHEMA_ROOT = Path(__file__).parents[2] / "schemas" / "v3.0"
SCHEMAS = {
    "vision-evidence-snapshot": "vision-evidence-snapshot.schema.json",
    "policy-decision": "policy-decision.schema.json",
    "analysis-result": "analysis-result.schema.json",
    "completion": "completion.schema.json",
    "failure-envelope": "failure-envelope.schema.json",
    "retained-photo-lifecycle": "retained-photo-lifecycle.schema.json",
}


class ContractValidationError(ValueError):
    """A stable contract validation failure."""


class NormalizedRegion(TypedDict):
    x: float
    y: float
    width: float
    height: float


class VisionEvidenceSnapshot(TypedDict):
    schema_version: str
    snapshot_version: str
    snapshot_id: str
    result_id: str
    observed_at: str
    support: dict[str, str]
    localization: dict[str, Any]
    quality: dict[str, dict[str, str]]
    ocr: dict[str, Any]
    freshness: dict[str, Any]
    versions: dict[str, str]


class PolicyDecision(TypedDict):
    schema_version: str
    decision_version: str
    decision_id: str
    result_id: str
    snapshot_id: str
    policy_version: str
    threshold_version: str
    status: str
    primary_action: dict[str, Any]
    gate_outcomes: dict[str, bool]
    all_required_gates_pass: bool
    automatic_completion_eligible: bool
    candidate_ready: bool


class Completion(TypedDict):
    schema_version: str
    completion_id: str
    result_id: str
    completion_source: str
    raw_candidate: str
    displayed_candidate: str
    final_serial: str
    supersedes_completion_id: str | None


class AnalysisResult(TypedDict):
    schema_version: str
    result_id: str
    vision_evidence_snapshot: VisionEvidenceSnapshot
    policy_decision: PolicyDecision
    status: str
    capture_complete: bool
    business_complete: bool
    completion: Completion | None


def _load_document(document: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(document, Mapping):
        return dict(document)
    with Path(document).open(encoding="utf-8") as handle:
        return json.load(handle)


def _reject_non_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractValidationError(f"{path}: numbers must be finite")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_non_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_non_finite(child, f"{path}[{index}]")


def _validate_region_containment(snapshot: dict[str, Any]) -> None:
    localization = snapshot["localization"]
    label = localization["label_region"]
    text = localization["text_region"]
    for name, region in (("label_region", label), ("text_region", text)):
        if region is not None and (
            region["x"] + region["width"] > 1 or region["y"] + region["height"] > 1
        ):
            raise ContractValidationError(
                f"localization.{name}: region exceeds normalized image bounds"
            )
    if label is not None and text is not None:
        inside = (
            text["x"] >= label["x"]
            and text["y"] >= label["y"]
            and text["x"] + text["width"] <= label["x"] + label["width"]
            and text["y"] + text["height"] <= label["y"] + label["height"]
        )
        if not inside:
            raise ContractValidationError(
                "localization.text_region: must be contained by label_region"
            )


def _all_gates_pass(gates: Mapping[str, bool]) -> bool:
    return all(gates.values())


def _validate_policy(decision: dict[str, Any]) -> None:
    conjunction = _all_gates_pass(decision["gate_outcomes"])
    if decision["all_required_gates_pass"] is not conjunction:
        raise ContractValidationError(
            "policy_decision.all_required_gates_pass: must equal the gate conjunction"
        )
    if decision["automatic_completion_eligible"] and not (
        conjunction and decision["candidate_ready"]
    ):
        raise ContractValidationError(
            "policy_decision.automatic_completion_eligible: requires every gate and a candidate"
        )


def _validate_completion(completion: dict[str, Any]) -> None:
    source = completion["completion_source"]
    if source == "automatic_ocr":
        probability = completion["whole_string_exact_probability_calibrated"]
        if probability is None or probability <= completion["auto_threshold_strictly_greater_than"]:
            raise ContractValidationError(
                "completion: automatic calibrated whole-string evidence must be strictly above PET"
            )
        if not _all_gates_pass(completion["gate_outcomes"]):
            raise ContractValidationError("completion: automatic completion requires every gate")
    if source == "user_confirmed_ocr_unchanged" and not (
        completion["raw_candidate"]
        == completion["displayed_candidate"]
        == completion["final_serial"]
    ):
        raise ContractValidationError(
            "completion: unchanged confirmation must preserve the verbatim candidate"
        )


def _validate_result(result: dict[str, Any]) -> None:
    snapshot = result["vision_evidence_snapshot"]
    decision = result["policy_decision"]
    completion = result["completion"]
    _validate_region_containment(snapshot)
    _validate_policy(decision)
    if completion is not None:
        _validate_completion(completion)

    if result["result_id"] != snapshot["result_id"] or result["result_id"] != decision["result_id"]:
        raise ContractValidationError("analysis_result: mismatched result identity")
    if snapshot["snapshot_id"] != decision["snapshot_id"]:
        raise ContractValidationError("analysis_result: mismatched snapshot identity")
    if result["status"] != decision["status"]:
        raise ContractValidationError("analysis_result: policy and result status must match")
    expected_recommendation = (
        None if decision["primary_action"]["kind"] == "none" else decision["primary_action"]
    )
    if result["recommendation"] != expected_recommendation:
        raise ContractValidationError(
            "analysis_result.recommendation: must exactly mirror the single primary action"
        )
    if result["business_complete"] is not (completion is not None):
        raise ContractValidationError(
            "analysis_result.business_complete: must exactly track immutable completion linkage"
        )
    if completion is not None and (
        completion["result_id"] != result["result_id"]
        or completion["session_id"] != result["session"]["session_id"]
        or completion["decision_id"] != decision["decision_id"]
        or completion["snapshot_id"] != snapshot["snapshot_id"]
    ):
        raise ContractValidationError("analysis_result: completion provenance linkage mismatch")
    if completion is not None:
        if (
            completion["raw_candidate"] != snapshot["ocr"]["raw_string"]
            or completion["displayed_candidate"] != snapshot["ocr"]["displayed_string"]
        ):
            raise ContractValidationError(
                "analysis_result.completion: candidate provenance must remain verbatim"
            )
        if (
            completion["whole_string_exact_probability_calibrated"]
            != snapshot["ocr"]["whole_string_exact_probability_calibrated"]
        ):
            raise ContractValidationError(
                "analysis_result.completion: calibrated probability provenance mismatch"
            )
        if completion["gate_outcomes"] != decision["gate_outcomes"]:
            raise ContractValidationError("analysis_result.completion: gate provenance mismatch")
        if completion["completion_source"] == "automatic_ocr" and not (
            completion["raw_candidate"]
            == completion["displayed_candidate"]
            == completion["final_serial"]
        ):
            raise ContractValidationError(
                "analysis_result.completion: automatic final serial must remain verbatim"
            )

    candidate = result["serial_candidate"]
    if candidate is not None and (
        candidate["raw"] != snapshot["ocr"]["raw_string"]
        or candidate["displayed"] != snapshot["ocr"]["displayed_string"]
    ):
        raise ContractValidationError(
            "analysis_result: candidate mutation or silent repair detected"
        )

    versions = result["versions"]
    expected_versions = {
        "schema": snapshot["versions"]["schema"],
        "model": snapshot["versions"]["model"],
        "preprocess": snapshot["versions"]["preprocess"],
        "calibration": snapshot["versions"]["calibration"],
        "policy": decision["policy_version"],
        "threshold": decision["threshold_version"],
    }
    if versions != expected_versions:
        raise ContractValidationError("analysis_result: stale or mismatched active versions")
    if completion is not None and (
        completion["schema_version_used"] != versions["schema"]
        or completion["model_version"] != versions["model"]
        or completion["preprocess_version"] != versions["preprocess"]
        or completion["calibration_version"] != versions["calibration"]
        or completion["policy_version"] != versions["policy"]
        or completion["threshold_version"] != versions["threshold"]
    ):
        raise ContractValidationError("analysis_result.completion: version provenance mismatch")
    if (
        snapshot["versions"]["policy_compatible"] != decision["policy_version"]
        or snapshot["versions"]["threshold_compatible"] != decision["threshold_version"]
    ):
        raise ContractValidationError("analysis_result: incompatible evidence versions")
    freshness = snapshot["freshness"]
    fresh = freshness["is_current_attempt"] and freshness["age_ms"] <= freshness["max_age_ms"]

    if result["status"] == "automatic_complete":
        evidence_gates_pass = (
            snapshot["support"]["state"] == "pass"
            and snapshot["support"]["ood_state"] == "in_distribution"
            and snapshot["localization"]["state"] == "pass"
            and all(gate["state"] == "pass" for gate in snapshot["quality"].values())
            and fresh
        )
        if not (
            result["capture_complete"]
            and result["business_complete"]
            and completion is not None
            and completion["completion_source"] == "automatic_ocr"
            and decision["automatic_completion_eligible"]
            and evidence_gates_pass
        ):
            raise ContractValidationError(
                "analysis_result: automatic completion requires current passing evidence "
                "and provenance"
            )
        probability = snapshot["ocr"]["whole_string_exact_probability_calibrated"]
        if probability is None or probability <= decision["auto_threshold_strictly_greater_than"]:
            raise ContractValidationError(
                "analysis_result: calibrated whole-string evidence must be strictly above PET"
            )
    if result["status"] == "ready_for_verification" and not (
        result["capture_complete"]
        and not result["business_complete"]
        and completion is None
        and candidate is not None
        and decision["candidate_ready"]
    ):
        raise ContractValidationError(
            "analysis_result: candidate-ready state separates capture from business completion"
        )


def _load_schemas() -> tuple[dict[str, dict[str, Any]], Registry[Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for kind, filename in SCHEMAS.items():
        with (SCHEMA_ROOT / filename).open(encoding="utf-8") as handle:
            schema = json.load(handle)
        schemas[kind] = schema
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return schemas, Registry().with_resources(resources)


def validate_document(kind: str, document: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    """Validate one contract document structurally and semantically."""
    if kind not in SCHEMAS:
        raise ContractValidationError(f"unknown contract kind: {kind}")
    payload = _load_document(document)
    _reject_non_finite(payload)
    schemas, registry = _load_schemas()
    schema = schemas[kind]
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker(), registry=registry).iter_errors(
            payload
        ),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "$"
        raise ContractValidationError(f"{location}: {error.message}") from error
    if kind == "vision-evidence-snapshot":
        _validate_region_containment(payload)
    elif kind == "policy-decision":
        _validate_policy(payload)
    elif kind == "completion":
        _validate_completion(payload)
    elif kind == "analysis-result":
        _validate_result(payload)
    return payload


__all__ = [
    "AnalysisResult",
    "Completion",
    "ContractValidationError",
    "NormalizedRegion",
    "PolicyDecision",
    "VisionEvidenceSnapshot",
    "validate_document",
]
