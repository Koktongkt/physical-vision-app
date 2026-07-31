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
    support: dict[str, Any]
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
    threshold_classification: str
    auto_threshold_strictly_greater_than: float
    status: str
    primary_action: dict[str, Any]
    gate_outcomes: dict[str, bool]
    all_required_gates_pass: bool
    automatic_completion_eligible: bool
    candidate_ready: bool
    evaluated_at: str


class Completion(TypedDict):
    schema_version: str
    completion_version: str
    completion_id: str
    task_id: str
    session_id: str
    result_id: str
    decision_id: str
    snapshot_id: str
    completion_source: str
    raw_candidate: str
    displayed_candidate: str
    final_serial: str
    threshold_version: str
    threshold_classification: str
    auto_threshold_strictly_greater_than: float
    whole_string_exact_probability_calibrated: float | None
    gate_outcomes: dict[str, bool]
    policy_version: str
    calibration_version: str
    model_version: str
    preprocess_version: str
    schema_version_used: str
    idempotency_key: str
    idempotency_fingerprint: str
    created_at: str
    supersedes_completion_id: str | None


class AnalysisResult(TypedDict):
    schema_version: str
    result_id: str
    session: dict[str, Any]
    source: dict[str, Any]
    vision_evidence_snapshot: VisionEvidenceSnapshot
    policy_decision: PolicyDecision
    status: str
    capture_complete: bool
    business_complete: bool
    serial_candidate: dict[str, Any] | None
    completion: Completion | None
    recommendation: dict[str, Any] | None
    failure: FailureEnvelope | None
    versions: dict[str, str]


class FailureEnvelope(TypedDict):
    schema_version: str
    code: str
    category: str
    recoverable: bool
    retryable: bool
    retry_after_ms: int | None
    message_key: str
    identity_conflict: dict[str, str] | None


class RetainedPhotoLifecycle(TypedDict):
    schema_version: str
    retained_photo_id: str
    result_id: str
    storage_key: str
    content_fingerprint: str
    media_type: str
    width: int
    height: int
    capture_method: str
    created_at: str
    lifecycle: str
    deletion: dict[str, Any] | None


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
    if (
        snapshot["support"]["state"] == "pass"
        and snapshot["support"]["probability_calibrated"] is None
    ):
        raise ContractValidationError(
            "support.probability_calibrated: pass requires measured probability evidence"
        )
    localization = snapshot["localization"]
    label = localization["label_region"]
    text = localization["text_region"]
    if localization["state"] == "pass" and any(
        value is None
        for value in (
            label,
            text,
            localization["text_containment"],
            localization["label_confidence"],
        )
    ):
        raise ContractValidationError("localization: pass requires complete passing evidence")
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


def _validate_utc_timestamp(value: str, field: str) -> None:
    if not value.endswith("Z"):
        raise ContractValidationError(f"{field}: must use an RFC 3339 UTC-Z timestamp")


def _all_gates_pass(gates: Mapping[str, bool]) -> bool:
    return all(gates.values())


CAMERA_ACTIONS = {
    "camera_left",
    "camera_right",
    "camera_closer",
    "camera_farther",
    "camera_tilt_direct",
    "camera_reduce_glare",
}


FAILURE_CATEGORIES = {
    "PHOTO_PICKER_UNAVAILABLE": "capability",
    "UPLOAD_UNAVAILABLE": "capability",
    "SESSION_EXPIRED": "not-found",
    "SEQUENCE_CONFLICT": "ambiguous",
    "ATTEMPT_SUPERSEDED": "not-found",
    "IDEMPOTENCY_CONFLICT": "ambiguous",
    "UNSUPPORTED_MEDIA_TYPE": "unsupported-input",
    "ANIMATED_OR_MULTIFRAME_UNSUPPORTED": "unsupported-input",
    "INVALID_OR_CORRUPT_IMAGE": "unsupported-input",
    "IMAGE_DIMENSIONS_UNSUPPORTED": "unsupported-input",
    "INPUT_TOO_LARGE": "unsupported-input",
    "DECODE_BUDGET_EXCEEDED": "unsupported-input",
    "NO_LABEL_FOUND": "not-found",
    "MULTIPLE_LABELS_AMBIGUOUS": "ambiguous",
    "UNSUPPORTED_LABEL_OR_OBJECT": "unsupported-subject",
    "SUPPORT_UNKNOWN": "unknown",
    "QUALITY_INSUFFICIENT": "quality",
    "SERIAL_UNREADABLE": "quality",
    "OCR_AMBIGUOUS": "ambiguous",
    "FORMAT_POLICY_MISMATCH": "quality",
    "PROCESSING_TIMEOUT": "timeout",
    "DEPENDENCY_UNAVAILABLE": "dependency",
    "LOCAL_STORAGE_LIMIT": "local-resource",
    "DELETION_PENDING": "deletion",
    "DELETION_FAILED": "deletion",
    "INTERNAL_PROCESSING_ERROR": "internal",
}


def _validate_policy(decision: dict[str, Any]) -> None:
    _validate_utc_timestamp(decision["evaluated_at"], "evaluated_at")
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
    if decision["status"] == "automatic_complete" and not decision["automatic_completion_eligible"]:
        raise ContractValidationError(
            "policy_decision: automatic_complete requires automatic completion eligibility"
        )
    if (
        decision["status"] in {"automatic_complete", "user_complete"}
        and decision["primary_action"]["kind"] != "none"
    ):
        raise ContractValidationError(
            "policy_decision: completed decision cannot include a primary action"
        )
    if (
        decision["status"] == "ready_for_verification"
        and decision["primary_action"]["kind"] != "none"
    ):
        raise ContractValidationError(
            "policy_decision: candidate-ready status cannot include a primary action"
        )
    if decision["status"] == "guidance" and decision["automatic_completion_eligible"]:
        raise ContractValidationError(
            "policy_decision: guidance decision cannot be completion eligible"
        )
    if decision["status"] == "guidance" and decision["candidate_ready"]:
        raise ContractValidationError(
            "policy_decision: guidance decision cannot be candidate ready"
        )
    if (
        decision["status"] == "guidance"
        and decision["primary_action"]["kind"] not in CAMERA_ACTIONS
    ):
        raise ContractValidationError(
            "policy_decision: guidance decision requires one camera action"
        )
    if decision["status"] == "ready_for_verification":
        if decision["automatic_completion_eligible"]:
            raise ContractValidationError(
                "policy_decision: ready_for_verification decision cannot be automatic "
                "completion eligible"
            )
        if not decision["candidate_ready"]:
            raise ContractValidationError(
                "policy_decision: ready_for_verification requires candidate readiness"
            )
    if (
        decision["status"] not in {"automatic_complete", "user_complete"}
        and decision["automatic_completion_eligible"]
    ):
        raise ContractValidationError(
            f"policy_decision: {decision['status']} decision cannot be automatic completion "
            "eligible"
        )
    if (
        decision["status"] not in {"ready_for_verification", "automatic_complete", "user_complete"}
        and decision["candidate_ready"]
    ):
        raise ContractValidationError(
            f"policy_decision: {decision['status']} decision cannot be candidate ready"
        )


def _validate_completion(completion: dict[str, Any]) -> None:
    _validate_utc_timestamp(completion["created_at"], "created_at")
    source = completion["completion_source"]
    if completion["supersedes_completion_id"] == completion["completion_id"]:
        raise ContractValidationError("completion: cannot supersede itself")
    if source == "automatic_ocr":
        if not all(
            completion[field] for field in ("raw_candidate", "displayed_candidate", "final_serial")
        ):
            raise ContractValidationError(
                "completion: automatic completion requires non-empty serial evidence"
            )
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
    _validate_utc_timestamp(snapshot["observed_at"], "observed_at")
    _validate_region_containment(snapshot)
    _validate_policy(decision)
    if result["failure"] is not None:
        _validate_failure(result["failure"])
    if completion is not None:
        _validate_completion(completion)
        if (
            completion["completion_source"] == "automatic_ocr"
            and result["status"] != "automatic_complete"
        ):
            raise ContractValidationError(
                "analysis_result: automatic_ocr completion requires automatic_complete status"
            )
        if (
            completion["completion_source"] in {"user_corrected", "user_confirmed_ocr_unchanged"}
            and result["status"] != "user_complete"
        ):
            raise ContractValidationError(
                "analysis_result: user completion source requires user_complete status"
            )
    if result["status"] == "automatic_complete":
        if completion is None or completion["completion_source"] != "automatic_ocr":
            raise ContractValidationError(
                "analysis_result: automatic_complete status requires automatic_ocr completion"
            )
        if decision["primary_action"]["kind"] != "none":
            raise ContractValidationError(
                "analysis_result: automatic completion cannot include a primary action"
            )
        if result["serial_candidate"] is None:
            raise ContractValidationError(
                "analysis_result.serial_candidate: automatic completion requires the current "
                "verbatim candidate"
            )
        if snapshot["support"]["probability_calibrated"] is None:
            raise ContractValidationError(
                "analysis_result: automatic support pass requires calibrated probability"
            )
        if any(
            snapshot["localization"][field] is None
            for field in (
                "label_region",
                "text_region",
                "text_containment",
                "label_confidence",
            )
        ):
            raise ContractValidationError(
                "analysis_result: automatic localization requires passing evidence"
            )

    if result["status"] == "user_complete" and (
        completion is None
        or completion["completion_source"] not in {"user_corrected", "user_confirmed_ocr_unchanged"}
    ):
        raise ContractValidationError(
            "analysis_result: user_complete status requires a user confirmation or correction"
        )

    if result["result_id"] != snapshot["result_id"] or result["result_id"] != decision["result_id"]:
        raise ContractValidationError("analysis_result: mismatched result identity")
    if snapshot["snapshot_id"] != decision["snapshot_id"]:
        raise ContractValidationError("analysis_result: mismatched snapshot identity")
    if result["status"] != decision["status"]:
        raise ContractValidationError("analysis_result: policy and result status must match")
    if (
        result["status"] in {"automatic_complete", "user_complete"}
        and decision["primary_action"]["kind"] != "none"
    ):
        raise ContractValidationError(
            "analysis_result: completed result cannot include a primary action"
        )
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
    if completion is not None and not result["capture_complete"]:
        raise ContractValidationError(
            "analysis_result.capture_complete: must be true for a completed result"
        )
    if completion is not None and result["failure"] is not None:
        raise ContractValidationError("analysis_result: completed result cannot include a failure")
    if result["status"] == "internal_error" and result["failure"] is None:
        raise ContractValidationError("analysis_result: internal_error requires a failure")
    if result["status"] == "internal_error" and (
        completion is not None
        or result["business_complete"]
        or result["capture_complete"]
        or result["serial_candidate"] is not None
        or decision["candidate_ready"]
        or decision["automatic_completion_eligible"]
    ):
        raise ContractValidationError(
            "analysis_result: internal_error must remain candidate-safe and incomplete"
        )
    if result["status"] == "guidance" and result["capture_complete"]:
        raise ContractValidationError(
            "analysis_result: guidance cannot claim capture_complete=true"
        )
    if (
        result["status"] not in {"ready_for_verification", "automatic_complete", "user_complete"}
        and result["capture_complete"]
    ):
        raise ContractValidationError(
            f"analysis_result: {result['status']} result cannot be capture complete"
        )

    if completion is not None and (
        completion["result_id"] != result["result_id"]
        or completion["session_id"] != result["session"]["session_id"]
        or completion["decision_id"] != decision["decision_id"]
        or completion["snapshot_id"] != snapshot["snapshot_id"]
    ):
        raise ContractValidationError("analysis_result: completion provenance linkage mismatch")
    if completion is not None and completion["task_id"] != result["session"]["task_id"]:
        raise ContractValidationError("analysis_result: task provenance linkage mismatch")
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
    if result["status"] == "ready_for_verification":
        if not (
            result["capture_complete"]
            and not result["business_complete"]
            and completion is None
            and candidate is not None
            and decision["candidate_ready"]
        ):
            raise ContractValidationError(
                "analysis_result: candidate-ready state separates capture from business completion"
            )
        if not candidate["raw"] or not candidate["displayed"]:
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires non-empty candidate"
            )
        if not fresh:
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires fresh evidence"
            )
        if not (
            snapshot["support"]["state"] == "pass"
            and snapshot["support"]["ood_state"] == "in_distribution"
            and snapshot["support"]["probability_calibrated"] is not None
        ):
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires passing support evidence"
            )
        if snapshot["localization"]["state"] != "pass":
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires passing localization evidence"
            )
        if snapshot["quality"]["ocr_integrity"]["state"] != "pass":
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires passing OCR integrity evidence"
            )
        if any(
            gate["state"] != "pass"
            for name, gate in snapshot["quality"].items()
            if name != "ocr_integrity"
        ):
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires passing quality evidence"
            )
        if not decision["all_required_gates_pass"]:
            raise ContractValidationError(
                "analysis_result: candidate-ready result requires every current-attempt gate"
            )


def _validate_failure(failure: dict[str, Any]) -> None:
    expected_category = FAILURE_CATEGORIES[failure["code"]]
    if failure["category"] != expected_category:
        raise ContractValidationError(
            f"failure code {failure['code']} requires category {expected_category}"
        )
    conflict = failure["identity_conflict"]
    if (
        failure["code"] == "IDEMPOTENCY_CONFLICT"
        and conflict["expected_fingerprint"] == conflict["received_fingerprint"]
    ):
        raise ContractValidationError(
            "failure.identity_conflict: IDEMPOTENCY_CONFLICT requires different fingerprints"
        )


def _validate_retained_photo(document: dict[str, Any]) -> None:
    _validate_utc_timestamp(document["created_at"], "created_at")
    if document["deletion"] is not None:
        _validate_utc_timestamp(document["deletion"]["requested_at"], "requested_at")
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{index}" for index in range(1, 10))
    reserved.update(f"LPT{index}" for index in range(1, 10))
    for segment in document["storage_key"].split("/"):
        base = segment.split(".", 1)[0].upper()
        if segment.endswith((".", " ")) or base in reserved:
            raise ContractValidationError(
                "storage_key: segments must not alias Windows device names or end in dot/space"
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
        _validate_utc_timestamp(payload["observed_at"], "observed_at")
        _validate_region_containment(payload)
    elif kind == "policy-decision":
        _validate_policy(payload)
    elif kind == "completion":
        _validate_completion(payload)
    elif kind == "failure-envelope":
        _validate_failure(payload)
    elif kind == "retained-photo-lifecycle":
        _validate_retained_photo(payload)
    elif kind == "analysis-result":
        _validate_result(payload)
    return payload


__all__ = [
    "AnalysisResult",
    "Completion",
    "ContractValidationError",
    "FailureEnvelope",
    "NormalizedRegion",
    "PolicyDecision",
    "RetainedPhotoLifecycle",
    "VisionEvidenceSnapshot",
    "validate_document",
]
