from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
from typing import Any

from physical_vision_barcode import BarcodeGuidanceAction

MANIFEST_SCHEMA_VERSION = "b26-study-manifest-v1"
REPORT_SCHEMA_VERSION = "b26-study-report-v1"
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?:https?://|data:image/|(?:[A-Za-z]:[\\/]|/Users/|/home/)|"
    r"(?:RuntimeError|ValueError|Exception|Traceback):)",
    re.IGNORECASE,
)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:payload|decode(?:d)?_?(?:text|string)|image_?bytes|host|origin|exception|"
    r"(?:input|fixture|media|image)_?path)",
    re.IGNORECASE,
)


class StudyValidationError(ValueError):
    """A content-free B26 study contract validation failure."""


def canonical_json_bytes(document: object) -> bytes:
    try:
        serialized = json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise StudyValidationError("document is not canonical JSON") from error
    return f"{serialized}\n".encode("ascii")


def _require_mapping(value: object, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise StudyValidationError(f"{field} must be an object")
    return value


def _require_exact_keys(document: dict[str, Any], keys: set[str], field: str) -> None:
    missing = sorted(keys - document.keys())
    extra = sorted(document.keys() - keys)
    if missing or extra:
        raise StudyValidationError(f"{field} has missing or unsupported fields")


def _assert_content_free(value: object) -> None:
    if type(value) is dict:
        for key, nested in value.items():
            if key in {"decode_payload", "payload_decode"} and nested is False:
                pass
            elif _SENSITIVE_KEY_PATTERN.search(str(key)):
                raise StudyValidationError("document contains prohibited sensitive content")
            _assert_content_free(nested)
    elif type(value) is list:
        for nested in value:
            _assert_content_free(nested)
    elif type(value) is str and (
        _SENSITIVE_VALUE_PATTERN.search(value) or re.fullmatch(r"\d{12,14}", value)
    ):
        raise StudyValidationError("document contains prohibited sensitive content")


def validate_manifest(manifest: object) -> None:
    document = _require_mapping(manifest, "manifest")
    _assert_content_free(document)
    _require_exact_keys(
        document,
        {
            "schema_version",
            "protocol_version",
            "study_track",
            "run_kind",
            "repository",
            "versions",
            "configuration",
            "operator",
            "capture_paths",
            "allowed_reason_codes",
            "sessions",
        },
        "manifest",
    )
    if document["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise StudyValidationError("unsupported manifest schema_version")
    if document["protocol_version"] != "B26-live-v1.0":
        raise StudyValidationError("unsupported protocol_version")
    if document["study_track"] != "live_physical" or document["run_kind"] != "locked":
        raise StudyValidationError(
            "locked manifest requires live_physical track and locked run_kind"
        )

    repository = _require_mapping(document["repository"], "repository")
    _require_exact_keys(repository, {"commit", "clean", "app_build"}, "repository")
    if not _COMMIT_PATTERN.fullmatch(repository["commit"]):
        raise StudyValidationError("repository commit must be an exact SHA")
    if repository["clean"] is not True or not repository["app_build"]:
        raise StudyValidationError("repository must identify a clean exact build")

    versions = _require_mapping(document["versions"], "versions")
    _require_exact_keys(
        versions,
        {
            "report_schema",
            "opencv",
            "detector_recipe",
            "ready_policy",
            "guidance_policy",
            "python",
            "browser",
            "os",
        },
        "versions",
    )
    if versions["report_schema"] != REPORT_SCHEMA_VERSION or not all(versions.values()):
        raise StudyValidationError("versions must contain exact non-empty values")

    operator = _require_mapping(document["operator"], "operator")
    _require_exact_keys(operator, {"operator_id", "labeler_id"}, "operator")
    if not all(operator.values()):
        raise StudyValidationError("operator pseudonymous IDs must be non-empty")

    configuration = _require_mapping(document["configuration"], "configuration")
    required_configuration = {
        "decode_payload",
        "learned_detector",
        "max_observations_per_session",
        "bootstrap_seed",
        "bootstrap_replicates",
        "ready_thresholds",
        "measurement_tolerances",
        "resource_limits",
    }
    _require_exact_keys(configuration, required_configuration, "configuration")
    if (
        configuration["decode_payload"] is not False
        or configuration["learned_detector"] is not False
    ):
        raise StudyValidationError("decode and learned detectors are prohibited")
    if configuration["max_observations_per_session"] != 6:
        raise StudyValidationError("max observations must remain frozen at six")
    if configuration["bootstrap_seed"] != 260826 or configuration["bootstrap_replicates"] != 10000:
        raise StudyValidationError("confidence method configuration does not match protocol")

    capture_paths = document["capture_paths"]
    sessions = document["sessions"]
    reasons = document["allowed_reason_codes"]
    if type(capture_paths) is not list or not capture_paths:
        raise StudyValidationError("capture_paths must be non-empty")
    if type(sessions) is not list or not sessions:
        raise StudyValidationError("sessions must be non-empty")
    if type(reasons) is not list or not reasons or len(reasons) != len(set(reasons)):
        raise StudyValidationError("allowed_reason_codes must be unique and non-empty")

    capture_ids = set()
    for capture in capture_paths:
        capture = _require_mapping(capture, "capture path")
        _require_exact_keys(
            capture,
            {"capture_path_id", "device", "camera", "resolution", "sample_rate_hz"},
            "capture path",
        )
        capture_ids.add(capture["capture_path_id"])
    if len(capture_ids) != len(capture_paths):
        raise StudyValidationError("capture_path_id values must be unique")

    orders = []
    session_ids = set()
    for session in sessions:
        session = _require_mapping(session, "session")
        if "run_kind" in session:
            raise StudyValidationError("session run_kind cannot differ from locked manifest")
        _require_exact_keys(
            session,
            {
                "order",
                "session_id",
                "physical_item_id",
                "capture_path_id",
                "scene_truth",
                "target_support",
                "assigned_challenge",
                "subgroups",
                "max_observations",
            },
            "session",
        )
        if session["capture_path_id"] not in capture_ids:
            raise StudyValidationError("session references an unknown capture path")
        if session["max_observations"] != 6:
            raise StudyValidationError("session max observations must remain six")
        if session["scene_truth"] not in {"none", "one", "multiple", "2d_only"}:
            raise StudyValidationError("unsupported scene_truth")
        subgroup_fields = {
            "barcode_family",
            "scale_distance",
            "angle_skew",
            "blur_motion",
            "crop_margin",
            "glare_exposure",
            "background_clutter",
            "ordinary_appearance",
        }
        subgroups = _require_mapping(session["subgroups"], "session subgroups")
        _require_exact_keys(subgroups, subgroup_fields, "session subgroups")
        if not all(subgroups.values()):
            raise StudyValidationError("session subgroups must be frozen and non-empty")
        orders.append(session["order"])
        session_ids.add(session["session_id"])
    if orders != list(range(1, len(sessions) + 1)) or len(session_ids) != len(sessions):
        raise StudyValidationError("sessions require unique IDs in contiguous locked order")

    canonical_json_bytes(document)


def lock_manifest(manifest: object, *, locked_at: str, signer_id: str) -> dict[str, Any]:
    validate_manifest(manifest)
    if not locked_at.endswith("Z") or not signer_id:
        raise StudyValidationError("lock metadata must identify UTC lock time and signer")
    frozen = copy.deepcopy(manifest)
    return {
        "schema_version": "b26-study-manifest-lock-v1",
        "manifest": frozen,
        "lock": {
            "algorithm": "sha256",
            "fingerprint": hashlib.sha256(canonical_json_bytes(frozen)).hexdigest(),
            "locked_at": locked_at,
            "signer_id": signer_id,
        },
    }


def verify_manifest_lock(locked: object) -> None:
    document = _require_mapping(locked, "locked manifest")
    _require_exact_keys(document, {"schema_version", "manifest", "lock"}, "locked manifest")
    if document["schema_version"] != "b26-study-manifest-lock-v1":
        raise StudyValidationError("unsupported lock schema_version")
    validate_manifest(document["manifest"])
    lock = _require_mapping(document["lock"], "lock")
    _require_exact_keys(lock, {"algorithm", "fingerprint", "locked_at", "signer_id"}, "lock")
    actual = hashlib.sha256(canonical_json_bytes(document["manifest"])).hexdigest()
    if lock["algorithm"] != "sha256" or lock["fingerprint"] != actual:
        raise StudyValidationError("manifest fingerprint does not match locked content")


def _validate_observation(
    observation: object,
    *,
    fingerprint: str,
    sessions: dict[str, dict[str, Any]],
    allowed_reasons: set[str],
) -> dict[str, Any]:
    document = _require_mapping(observation, "observation")
    _assert_content_free(document)
    common_keys = {
        "schema_version",
        "manifest_fingerprint",
        "study_track",
        "run_kind",
        "session_id",
        "observation_index",
        "disposition",
        "reason_code",
    }
    if document.get("schema_version") != "b26-study-observation-v1":
        raise StudyValidationError("unsupported observation schema_version")
    if document.get("manifest_fingerprint") != fingerprint:
        raise StudyValidationError("observation fingerprint does not match manifest")
    if document.get("study_track") != "live_physical":
        raise StudyValidationError("locked aggregation accepts live_physical observations only")
    if document.get("run_kind") != "locked":
        raise StudyValidationError("locked aggregation rejects non-locked observations")
    if document.get("session_id") not in sessions:
        raise StudyValidationError("observation references an unknown session")
    index = document.get("observation_index")
    if (
        type(index) is not int
        or not 1 <= index <= sessions[document["session_id"]]["max_observations"]
    ):
        raise StudyValidationError("observation_index is outside the locked session bound")

    disposition = document.get("disposition")
    if disposition in {"missing", "excluded"}:
        _require_exact_keys(document, common_keys, "non-analyzed observation")
        if document.get("reason_code") not in allowed_reasons:
            raise StudyValidationError("missing or exclusion reason is not preregistered")
        return document
    if disposition != "analyzed":
        raise StudyValidationError("unsupported observation disposition")
    _require_exact_keys(
        document,
        common_keys
        | {
            "human",
            "system",
            "guidance_transition",
            "unsafe",
            "latency_ms",
            "session_end",
        },
        "analyzed observation",
    )
    if document["reason_code"] is not None:
        raise StudyValidationError("analyzed observation cannot have a reason_code")
    human = _require_mapping(document["human"], "human label")
    system = _require_mapping(document["system"], "system decision")
    _require_exact_keys(
        human,
        {"count", "target_support", "ready", "guidance_eligible"},
        "human label",
    )
    _require_exact_keys(
        system,
        {"count", "ready", "guidance_actions", "localization_success"},
        "system decision",
    )
    counts = {"none", "one", "multiple", "unknown"}
    if human["count"] not in counts or system["count"] not in counts:
        raise StudyValidationError("count class is invalid")
    if human["ready"] not in {"ready", "not_ready", "unknown"}:
        raise StudyValidationError("human ready label is invalid")
    if type(human["guidance_eligible"]) is not bool:
        raise StudyValidationError("human guidance eligibility must be boolean")
    if type(system["ready"]) is not bool or type(system["guidance_actions"]) is not list:
        raise StudyValidationError("system ready and guidance action types are invalid")
    allowed_actions = {
        action.value for action in BarcodeGuidanceAction if action is not BarcodeGuidanceAction.NONE
    }
    if len(system["guidance_actions"]) > 1 or any(
        action not in allowed_actions for action in system["guidance_actions"]
    ):
        raise StudyValidationError("guidance actions are outside the content-free allowlist")
    if system["ready"] and system["guidance_actions"]:
        raise StudyValidationError("ready observation cannot include a guidance action")
    if document["guidance_transition"] not in {
        None,
        "improving",
        "unchanged",
        "worsening",
        "not_evaluable",
    }:
        raise StudyValidationError("guidance transition is invalid")
    if type(document["unsafe"]) is not bool:
        raise StudyValidationError("unsafe must be boolean")
    if document["session_end"] not in {
        None,
        "ready_shutter",
        "user_exit",
        "unsupported",
        "input_error",
        "resource_error",
        "dependency_error",
        "internal_error",
        "max_observations",
    }:
        raise StudyValidationError("session end is invalid")
    if type(document["latency_ms"]) not in {int, float} or not math.isfinite(
        document["latency_ms"]
    ):
        raise StudyValidationError("latency must be finite")
    return document


def _percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise StudyValidationError("cannot take percentile of empty values")
    rank = max(1, math.ceil(probability * len(sorted_values)))
    return sorted_values[rank - 1]


def _cluster_interval(
    rows: list[dict[str, Any]],
    sessions: dict[str, dict[str, Any]],
    predicate,
    eligible,
    *,
    replicates: int,
) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item_id = sessions[row["session_id"]]["physical_item_id"]
        clusters.setdefault(item_id, []).append(row)
    item_ids = sorted(clusters)
    if not item_ids:
        return {"lower": None, "upper": None, "usable_replicates": 0}
    generator = random.Random(260826)
    values = []
    for _ in range(replicates):
        sampled_rows = []
        for _ in item_ids:
            sampled_rows.extend(clusters[generator.choice(item_ids)])
        denominator = sum(eligible(row) for row in sampled_rows)
        if denominator:
            values.append(sum(predicate(row) for row in sampled_rows) / denominator)
    minimum_usable = math.ceil(replicates * 0.95)
    if len(values) < minimum_usable:
        return {"lower": None, "upper": None, "usable_replicates": len(values)}
    values.sort()
    return {
        "lower": round(_percentile(values, 0.025), 6),
        "upper": round(_percentile(values, 0.975), 6),
        "usable_replicates": len(values),
    }


def _proportion_metric(
    rows: list[dict[str, Any]],
    sessions: dict[str, dict[str, Any]],
    predicate,
    eligible,
    *,
    replicates: int,
) -> dict[str, Any]:
    denominator = sum(eligible(row) for row in rows)
    numerator = sum(predicate(row) for row in rows)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": round(numerator / denominator, 6) if denominator else None,
        "interval_95": _cluster_interval(
            rows,
            sessions,
            predicate,
            eligible,
            replicates=replicates,
        ),
    }


def aggregate_live_report(
    locked: object,
    observations: list[object],
    *,
    bootstrap_replicates: int = 10000,
) -> dict[str, Any]:
    verify_manifest_lock(locked)
    if type(bootstrap_replicates) is not int or not 1 <= bootstrap_replicates <= 10000:
        raise StudyValidationError("bootstrap_replicates must be an integer in [1, 10000]")
    manifest = locked["manifest"]
    fingerprint = locked["lock"]["fingerprint"]
    sessions = {row["session_id"]: row for row in manifest["sessions"]}
    rows = [
        _validate_observation(
            row,
            fingerprint=fingerprint,
            sessions=sessions,
            allowed_reasons=set(manifest["allowed_reason_codes"]),
        )
        for row in observations
    ]
    rows.sort(key=lambda row: (sessions[row["session_id"]]["order"], row["observation_index"]))
    identities = [(row["session_id"], row["observation_index"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise StudyValidationError("observation identity is duplicated")
    analyzed = [row for row in rows if row["disposition"] == "analyzed"]
    missing = [row for row in rows if row["disposition"] == "missing"]
    excluded = [row for row in rows if row["disposition"] == "excluded"]
    for session_id in sessions:
        session_rows = [row for row in rows if row["session_id"] == session_id]
        analyzed_rows = [row for row in session_rows if row["disposition"] == "analyzed"]
        if analyzed_rows:
            indices = [row["observation_index"] for row in analyzed_rows]
            if indices != list(range(1, len(analyzed_rows) + 1)):
                raise StudyValidationError(
                    "analyzed session indices must be contiguous starting at 1"
                )
            terminal_rows = [row for row in analyzed_rows if row["session_end"] is not None]
            if len(terminal_rows) != 1 or terminal_rows[0] is not analyzed_rows[-1]:
                raise StudyValidationError(
                    "analyzed session requires exactly one terminal row last"
                )
            terminal = terminal_rows[0]
            if (
                terminal["session_end"] == "max_observations"
                and terminal["observation_index"] != sessions[session_id]["max_observations"]
            ):
                raise StudyValidationError(
                    "max_observations terminal requires the sixth observation"
                )
        elif len(session_rows) != 1 or session_rows[0]["observation_index"] != 1:
            raise StudyValidationError(
                "missing or excluded session requires one accounting row at index 1"
            )
    attempted_sessions = {row["session_id"] for row in analyzed}
    missing_sessions = {row["session_id"] for row in missing}
    excluded_sessions = {row["session_id"] for row in excluded}
    accounted = attempted_sessions | missing_sessions | excluded_sessions
    if attempted_sessions & (missing_sessions | excluded_sessions):
        raise StudyValidationError("session cannot be both analyzed and missing or excluded")
    if accounted != set(sessions):
        raise StudyValidationError(
            "every planned session requires analyzed, missing, or excluded accounting"
        )

    def evaluable_count(row: dict[str, Any]) -> bool:
        return row["human"]["count"] != "unknown"

    def count_correct(row: dict[str, Any]) -> bool:
        return evaluable_count(row) and row["human"]["count"] == row["system"]["count"]

    def ready_evaluable(row: dict[str, Any]) -> bool:
        return row["human"]["ready"] in {"ready", "not_ready"}

    def human_not_ready(row: dict[str, Any]) -> bool:
        return row["human"]["ready"] == "not_ready"

    def false_ready(row: dict[str, Any]) -> bool:
        return human_not_ready(row) and row["system"]["ready"]

    def predicted_ready(row: dict[str, Any]) -> bool:
        return ready_evaluable(row) and row["system"]["ready"]

    def system_abstained(row: dict[str, Any]) -> bool:
        return not row["system"]["ready"] and not row["system"]["guidance_actions"]

    def abstention_required(row: dict[str, Any]) -> bool:
        return row["human"]["count"] in {"none", "multiple", "unknown"}

    def ready_predicted(row: dict[str, Any]) -> bool:
        return row["system"]["ready"] and ready_evaluable(row)

    def ready_correct(row: dict[str, Any]) -> bool:
        return ready_predicted(row) and row["human"]["ready"] == "ready"

    def guidance_eligibility_evaluable(row: dict[str, Any]) -> bool:
        return row["human"]["ready"] == "not_ready"

    def guidance_eligibility_correct(row: dict[str, Any]) -> bool:
        return guidance_eligibility_evaluable(row) and (
            row["human"]["guidance_eligible"] == bool(row["system"]["guidance_actions"])
        )

    def localization_eligible(row: dict[str, Any]) -> bool:
        return row["human"]["count"] == "one" and row["system"]["localization_success"] is not None

    def localization_success(row: dict[str, Any]) -> bool:
        return localization_eligible(row) and row["system"]["localization_success"] is True

    def guidance_displayed(row: dict[str, Any]) -> bool:
        return bool(row["system"]["guidance_actions"])

    def exactly_one_action(row: dict[str, Any]) -> bool:
        return len(row["system"]["guidance_actions"]) == 1

    def transition_evaluable(row: dict[str, Any]) -> bool:
        return row["guidance_transition"] in {"improving", "unchanged", "worsening"}

    def transition_improving(row: dict[str, Any]) -> bool:
        return row["guidance_transition"] == "improving"

    def unsafe_or_worsening(row: dict[str, Any]) -> bool:
        return transition_evaluable(row) and (
            row["unsafe"] or row["guidance_transition"] == "worsening"
        )

    metrics = {
        "count_accuracy": _proportion_metric(
            analyzed, sessions, count_correct, evaluable_count, replicates=bootstrap_replicates
        ),
        "false_ready": _proportion_metric(
            analyzed,
            sessions,
            false_ready,
            human_not_ready,
            replicates=bootstrap_replicates,
        ),
        "ready_coverage": _proportion_metric(
            analyzed,
            sessions,
            predicted_ready,
            ready_evaluable,
            replicates=bootstrap_replicates,
        ),
        "ready_precision": _proportion_metric(
            analyzed,
            sessions,
            ready_correct,
            ready_predicted,
            replicates=bootstrap_replicates,
        ),
        "required_abstention": _proportion_metric(
            analyzed,
            sessions,
            system_abstained,
            abstention_required,
            replicates=bootstrap_replicates,
        ),
        "guidance_eligibility": _proportion_metric(
            analyzed,
            sessions,
            guidance_eligibility_correct,
            guidance_eligibility_evaluable,
            replicates=bootstrap_replicates,
        ),
        "localization_success": _proportion_metric(
            analyzed,
            sessions,
            localization_success,
            localization_eligible,
            replicates=bootstrap_replicates,
        ),
        "exactly_one_action": _proportion_metric(
            analyzed,
            sessions,
            exactly_one_action,
            guidance_displayed,
            replicates=bootstrap_replicates,
        ),
        "guidance_improvement": _proportion_metric(
            analyzed,
            sessions,
            transition_improving,
            transition_evaluable,
            replicates=bootstrap_replicates,
        ),
        "unsafe_or_worsening": _proportion_metric(
            analyzed,
            sessions,
            unsafe_or_worsening,
            transition_evaluable,
            replicates=bootstrap_replicates,
        ),
    }
    reason_counts: dict[str, int] = {}
    for row in missing:
        reason_counts[row["reason_code"]] = reason_counts.get(row["reason_code"], 0) + 1
    exclusion_reason_counts: dict[str, int] = {}
    for row in excluded:
        exclusion_reason_counts[row["reason_code"]] = (
            exclusion_reason_counts.get(row["reason_code"], 0) + 1
        )
    item_groups: dict[str, list[str]] = {}
    for session in manifest["sessions"]:
        item_groups.setdefault(session["physical_item_id"], []).append(session["session_id"])
    count_classes = ("none", "one", "multiple", "unknown")
    confusion = {human: {predicted: 0 for predicted in count_classes} for human in count_classes}
    for row in analyzed:
        confusion[row["human"]["count"]][row["system"]["count"]] += 1
    latency_values = sorted(row["latency_ms"] for row in analyzed)
    latency = {
        "count": len(latency_values),
        "median": round(_percentile(latency_values, 0.5), 3) if latency_values else None,
        "p95": round(_percentile(latency_values, 0.95), 3) if latency_values else None,
        "maximum": round(max(latency_values), 3) if latency_values else None,
    }
    transitions = {
        transition: sum(
            (row["guidance_transition"] or "not_evaluable") == transition for row in analyzed
        )
        for transition in ("improving", "unchanged", "worsening", "not_evaluable")
    }
    subgroup_accumulators: dict[str, dict[str, dict[str, Any]]] = {"capture_path": {}}
    for row in analyzed:
        session = sessions[row["session_id"]]
        subgroup = subgroup_accumulators["capture_path"].setdefault(
            session["capture_path_id"], {"analyzed_observations": 0, "items": set()}
        )
        subgroup["analyzed_observations"] += 1
        subgroup["items"].add(session["physical_item_id"])
        for field, value in session["subgroups"].items():
            subgroup = subgroup_accumulators.setdefault(field, {}).setdefault(
                value, {"analyzed_observations": 0, "items": set()}
            )
            subgroup["analyzed_observations"] += 1
            subgroup["items"].add(session["physical_item_id"])
    subgroups = {
        field: {
            value: {
                "analyzed_observations": values["analyzed_observations"],
                "physical_item_families": len(values["items"]),
            }
            for value, values in sorted(value_map.items())
        }
        for field, value_map in sorted(subgroup_accumulators.items())
    }
    diagnostics = {
        "false_single_count": sum(
            row["human"]["count"] != "one" and row["system"]["count"] == "one" for row in analyzed
        ),
        "unknown_prediction_count": sum(row["system"]["count"] == "unknown" for row in analyzed),
        "veto_violation_count": sum(
            bool(row["system"]["guidance_actions"])
            and (row["human"]["count"] != "one" or row["human"]["target_support"] != "supported_1d")
            for row in analyzed
        ),
    }
    ready_attempts: dict[str, int] = {}
    for row in analyzed:
        if row["system"]["ready"]:
            ready_attempts[row["session_id"]] = min(
                ready_attempts.get(row["session_id"], row["observation_index"]),
                row["observation_index"],
            )
    attempt_values = sorted(ready_attempts.values())
    attempts_to_ready = {
        "reached_ready_sessions": len(attempt_values),
        "values": attempt_values,
        "cumulative_sessions_by_attempt": {
            str(attempt): sum(value <= attempt for value in attempt_values)
            for attempt in range(1, 7)
        },
    }
    last_rows: dict[str, dict[str, Any]] = {}
    for row in analyzed:
        last_rows[row["session_id"]] = row
    session_outcomes: dict[str, int] = {}
    for row in last_rows.values():
        session_outcomes[row["session_end"]] = session_outcomes.get(row["session_end"], 0) + 1
    item_summaries = []
    for item_id in sorted(item_groups):
        item_rows = [
            row for row in analyzed if sessions[row["session_id"]]["physical_item_id"] == item_id
        ]
        item_summaries.append(
            {
                "physical_item_id": item_id,
                "analyzed_observations": len(item_rows),
                "count_correct": sum(count_correct(row) for row in item_rows),
                "predicted_ready": sum(row["system"]["ready"] for row in item_rows),
                "guidance_decisions": sum(guidance_displayed(row) for row in item_rows),
            }
        )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_version": manifest["protocol_version"],
        "manifest_fingerprint": fingerprint,
        "study_track": "live_physical",
        "status": "completed_locked_run" if analyzed else "live_pending",
        "scope": "bounded-live-physical-mini-study-not-validation",
        "public_supplement_status": "public_supplement_omitted",
        "denominators": {
            "planned_sessions": len(sessions),
            "attempted_sessions": len(attempted_sessions),
            "missing_sessions": len(missing_sessions),
            "excluded_sessions": len(excluded_sessions),
            "analyzed_observations": len(analyzed),
            "physical_item_clusters": len(
                {sessions[row["session_id"]]["physical_item_id"] for row in analyzed}
            ),
        },
        "confidence_method": {
            "name": "physical-item-cluster-bootstrap-percentile",
            "confidence": 0.95,
            "seed": 260826,
            "replicates": bootstrap_replicates,
        },
        "metrics": metrics,
        "count_confusion": confusion,
        "latency_ms": latency,
        "guidance_transitions": transitions,
        "subgroups": subgroups,
        "diagnostics": diagnostics,
        "attempts_to_ready": attempts_to_ready,
        "session_outcomes": dict(sorted(session_outcomes.items())),
        "item_summaries": item_summaries,
        "missing_reasons": dict(sorted(reason_counts.items())),
        "exclusion_reasons": dict(sorted(exclusion_reason_counts.items())),
        "groups": [
            {"physical_item_id": item_id, "session_ids": sorted(session_ids)}
            for item_id, session_ids in sorted(item_groups.items())
        ],
        "claim_boundary": {
            "live_and_public_denominators_separate": True,
            "production_validation": False,
            "payload_decode": False,
            "onnx_detector_implemented": False,
        },
    }
    validate_report(report)
    return report


def _require_nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise StudyValidationError(f"{field} must be a nonnegative integer")
    return value


def _require_finite_nonnegative_number(value: object, field: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise StudyValidationError(f"{field} must be a finite nonnegative number")
    return float(value)


def _validate_reason_counts(value: object, field: str, expected_total: int) -> None:
    reasons = _require_mapping(value, field)
    total = 0
    for reason, count in reasons.items():
        if type(reason) is not str or not reason or type(count) is not int or count <= 0:
            raise StudyValidationError(f"{field} entries must be non-empty positive counts")
        total += count
    if total != expected_total:
        raise StudyValidationError(f"{field} total does not match its session denominator")


def validate_report(report: object) -> None:
    document = _require_mapping(report, "report")
    _assert_content_free(document)
    _require_exact_keys(
        document,
        {
            "schema_version",
            "protocol_version",
            "manifest_fingerprint",
            "study_track",
            "status",
            "scope",
            "public_supplement_status",
            "denominators",
            "confidence_method",
            "metrics",
            "count_confusion",
            "latency_ms",
            "guidance_transitions",
            "subgroups",
            "diagnostics",
            "attempts_to_ready",
            "session_outcomes",
            "item_summaries",
            "missing_reasons",
            "exclusion_reasons",
            "groups",
            "claim_boundary",
        },
        "report",
    )
    if document["schema_version"] != REPORT_SCHEMA_VERSION:
        raise StudyValidationError("unsupported report schema_version")
    if document["protocol_version"] != "B26-live-v1.0":
        raise StudyValidationError("unsupported report protocol_version")
    if document["study_track"] != "live_physical":
        raise StudyValidationError("live report requires live_physical study_track")
    if document["scope"] != "bounded-live-physical-mini-study-not-validation":
        raise StudyValidationError("live report scope is invalid")
    if document["public_supplement_status"] != "public_supplement_omitted":
        raise StudyValidationError("live report must preserve public_supplement_omitted")
    if not re.fullmatch(r"[0-9a-f]{64}", document["manifest_fingerprint"]):
        raise StudyValidationError("report manifest fingerprint is invalid")

    denominators = _require_mapping(document["denominators"], "report denominators")
    denominator_keys = {
        "planned_sessions",
        "attempted_sessions",
        "missing_sessions",
        "excluded_sessions",
        "analyzed_observations",
        "physical_item_clusters",
    }
    _require_exact_keys(denominators, denominator_keys, "report denominators")
    for key in denominator_keys:
        _require_nonnegative_int(denominators[key], f"report denominators.{key}")
    planned = denominators["planned_sessions"]
    attempted = denominators["attempted_sessions"]
    missing = denominators["missing_sessions"]
    excluded = denominators["excluded_sessions"]
    analyzed = denominators["analyzed_observations"]
    clusters = denominators["physical_item_clusters"]
    if attempted + missing + excluded != planned or attempted > analyzed or clusters > attempted:
        raise StudyValidationError("report denominator sums are incoherent")
    status = document["status"]
    if status == "completed_locked_run":
        if not attempted or not analyzed or not clusters:
            raise StudyValidationError("completed status requires analyzed live evidence")
    elif status in {"protocol_only", "live_pending"}:
        if attempted or analyzed or clusters:
            raise StudyValidationError("pending status cannot contain analyzed live evidence")
    else:
        raise StudyValidationError("unsupported live report status")

    confidence = _require_mapping(document["confidence_method"], "confidence method")
    _require_exact_keys(
        confidence, {"name", "confidence", "seed", "replicates"}, "confidence method"
    )
    if (
        confidence["name"] != "physical-item-cluster-bootstrap-percentile"
        or type(confidence["confidence"]) is not float
        or confidence["confidence"] != 0.95
        or type(confidence["seed"]) is not int
        or confidence["seed"] != 260826
        or type(confidence["replicates"]) is not int
        or not 1 <= confidence["replicates"] <= 10000
    ):
        raise StudyValidationError("confidence method metadata is invalid")
    replicates = confidence["replicates"]

    metric_names = {
        "count_accuracy",
        "false_ready",
        "ready_coverage",
        "ready_precision",
        "required_abstention",
        "guidance_eligibility",
        "localization_success",
        "exactly_one_action",
        "guidance_improvement",
        "unsafe_or_worsening",
    }
    metrics = _require_mapping(document["metrics"], "metrics")
    _require_exact_keys(metrics, metric_names, "metrics")
    for name in metric_names:
        metric = _require_mapping(metrics[name], f"metric {name}")
        _require_exact_keys(
            metric, {"numerator", "denominator", "value", "interval_95"}, f"metric {name}"
        )
        numerator = _require_nonnegative_int(metric["numerator"], f"metric {name} numerator")
        denominator = _require_nonnegative_int(metric["denominator"], f"metric {name} denominator")
        expected = round(numerator / denominator, 6) if denominator else None
        if numerator > denominator or denominator > analyzed or metric["value"] != expected:
            raise StudyValidationError("metric numerator, denominator, and value are inconsistent")
        interval = _require_mapping(metric["interval_95"], f"metric {name} interval")
        _require_exact_keys(
            interval, {"lower", "upper", "usable_replicates"}, f"metric {name} interval"
        )
        usable = _require_nonnegative_int(
            interval["usable_replicates"], f"metric {name} usable replicates"
        )
        if usable > replicates:
            raise StudyValidationError("metric usable replicates exceed configured replicates")
        lower, upper = interval["lower"], interval["upper"]
        if usable < math.ceil(replicates * 0.95):
            if lower is not None or upper is not None:
                raise StudyValidationError("unusable metric interval must be null")
        elif (
            type(lower) not in {int, float}
            or type(upper) not in {int, float}
            or not math.isfinite(lower)
            or not math.isfinite(upper)
            or not 0 <= lower <= upper <= 1
        ):
            raise StudyValidationError("usable metric interval is invalid")

    count_classes = {"none", "one", "multiple", "unknown"}
    confusion = _require_mapping(document["count_confusion"], "count confusion")
    _require_exact_keys(confusion, count_classes, "count confusion")
    confusion_total = 0
    for human_class in count_classes:
        row = _require_mapping(confusion[human_class], "count confusion row")
        _require_exact_keys(row, count_classes, "count confusion row")
        for value in row.values():
            confusion_total += _require_nonnegative_int(value, "count confusion cell")
    if confusion_total != analyzed:
        raise StudyValidationError("count confusion total must equal analyzed observations")
    evaluable_count = sum(sum(confusion[human].values()) for human in count_classes - {"unknown"})
    count_correct = sum(confusion[label][label] for label in count_classes - {"unknown"})
    if (
        metrics["count_accuracy"]["denominator"] != evaluable_count
        or metrics["count_accuracy"]["numerator"] != count_correct
        or metrics["required_abstention"]["denominator"]
        != sum(sum(confusion[human].values()) for human in {"none", "multiple", "unknown"})
        or metrics["exactly_one_action"]["numerator"]
        != metrics["exactly_one_action"]["denominator"]
    ):
        raise StudyValidationError("metric totals are incoherent with aggregate evidence")

    latency = _require_mapping(document["latency_ms"], "latency")
    _require_exact_keys(latency, {"count", "median", "p95", "maximum"}, "latency")
    if _require_nonnegative_int(latency["count"], "latency count") != analyzed:
        raise StudyValidationError("latency count must equal analyzed observations")
    if analyzed:
        median = _require_finite_nonnegative_number(latency["median"], "latency median")
        p95 = _require_finite_nonnegative_number(latency["p95"], "latency p95")
        maximum = _require_finite_nonnegative_number(latency["maximum"], "latency maximum")
        if not median <= p95 <= maximum:
            raise StudyValidationError("latency summaries are out of order")
    elif any(latency[key] is not None for key in ("median", "p95", "maximum")):
        raise StudyValidationError("empty latency summaries must be null")

    transition_names = {"improving", "unchanged", "worsening", "not_evaluable"}
    transitions = _require_mapping(document["guidance_transitions"], "guidance transitions")
    _require_exact_keys(transitions, transition_names, "guidance transitions")
    if (
        sum(
            _require_nonnegative_int(transitions[key], "guidance transition count")
            for key in transition_names
        )
        != analyzed
    ):
        raise StudyValidationError("guidance transition counts must equal analyzed observations")
    transition_evaluable = sum(transitions[key] for key in {"improving", "unchanged", "worsening"})
    if (
        metrics["guidance_improvement"]["denominator"] != transition_evaluable
        or metrics["guidance_improvement"]["numerator"] != transitions["improving"]
        or metrics["unsafe_or_worsening"]["denominator"] != transition_evaluable
        or metrics["unsafe_or_worsening"]["numerator"] < transitions["worsening"]
    ):
        raise StudyValidationError("transition metrics are incoherent")

    subgroups = _require_mapping(document["subgroups"], "subgroups")
    expected_subgroups = {
        "capture_path",
        "barcode_family",
        "scale_distance",
        "angle_skew",
        "blur_motion",
        "crop_margin",
        "glare_exposure",
        "background_clutter",
        "ordinary_appearance",
    }
    if analyzed:
        _require_exact_keys(subgroups, expected_subgroups, "subgroups")
    elif subgroups != {"capture_path": {}}:
        raise StudyValidationError("pending report subgroups must be empty")
    for field, buckets_value in subgroups.items():
        buckets = _require_mapping(buckets_value, f"subgroup {field}")
        field_total = 0
        for label, summary_value in buckets.items():
            if type(label) is not str or not label:
                raise StudyValidationError("subgroup labels must be non-empty strings")
            summary = _require_mapping(summary_value, "subgroup summary")
            _require_exact_keys(
                summary, {"analyzed_observations", "physical_item_families"}, "subgroup summary"
            )
            observations = _require_nonnegative_int(
                summary["analyzed_observations"], "subgroup observations"
            )
            families = _require_nonnegative_int(
                summary["physical_item_families"], "subgroup item families"
            )
            if not observations or not 1 <= families <= min(observations, clusters):
                raise StudyValidationError("subgroup summary is outside report denominators")
            field_total += observations
        if field_total != analyzed:
            raise StudyValidationError("each subgroup field must partition analyzed observations")

    diagnostics = _require_mapping(document["diagnostics"], "diagnostics")
    diagnostic_names = {"false_single_count", "unknown_prediction_count", "veto_violation_count"}
    _require_exact_keys(diagnostics, diagnostic_names, "diagnostics")
    for name in diagnostic_names:
        if _require_nonnegative_int(diagnostics[name], f"diagnostic {name}") > analyzed:
            raise StudyValidationError("diagnostic count exceeds analyzed observations")
    if diagnostics["unknown_prediction_count"] != sum(
        confusion[human]["unknown"] for human in count_classes
    ):
        raise StudyValidationError("unknown prediction diagnostic is incoherent")

    attempts = _require_mapping(document["attempts_to_ready"], "attempts to ready")
    _require_exact_keys(
        attempts,
        {"reached_ready_sessions", "values", "cumulative_sessions_by_attempt"},
        "attempts to ready",
    )
    reached = _require_nonnegative_int(attempts["reached_ready_sessions"], "reached ready sessions")
    values = attempts["values"]
    if (
        type(values) is not list
        or len(values) != reached
        or reached > attempted
        or values != sorted(values)
        or any(type(value) is not int or not 1 <= value <= 6 for value in values)
    ):
        raise StudyValidationError("attempts-to-ready values are invalid")
    cumulative = _require_mapping(
        attempts["cumulative_sessions_by_attempt"], "cumulative sessions by attempt"
    )
    _require_exact_keys(
        cumulative, {str(index) for index in range(1, 7)}, "cumulative sessions by attempt"
    )
    if any(
        cumulative[str(index)] != sum(value <= index for value in values) for index in range(1, 7)
    ):
        raise StudyValidationError("attempts-to-ready cumulative counts are incoherent")

    outcome_names = {
        "ready_shutter",
        "user_exit",
        "unsupported",
        "input_error",
        "resource_error",
        "dependency_error",
        "internal_error",
        "max_observations",
    }
    outcomes = _require_mapping(document["session_outcomes"], "session outcomes")
    if (
        any(key not in outcome_names for key in outcomes)
        or sum(
            _require_nonnegative_int(value, "session outcome count") for value in outcomes.values()
        )
        != attempted
    ):
        raise StudyValidationError("session outcome counts are invalid")
    if (
        any(value == 0 for value in outcomes.values())
        or outcomes.get("ready_shutter", 0) != reached
    ):
        raise StudyValidationError("session outcomes are incoherent with ready evidence")

    groups = document["groups"]
    summaries = document["item_summaries"]
    if type(groups) is not list or type(summaries) is not list:
        raise StudyValidationError("groups and item summaries must be arrays")
    group_ids: set[str] = set()
    session_ids: set[str] = set()
    for group_value in groups:
        group = _require_mapping(group_value, "group")
        _require_exact_keys(group, {"physical_item_id", "session_ids"}, "group")
        item_id, ids = group["physical_item_id"], group["session_ids"]
        if (
            type(item_id) is not str
            or not item_id
            or item_id in group_ids
            or type(ids) is not list
            or not ids
            or ids != sorted(ids)
            or any(type(session_id) is not str or not session_id for session_id in ids)
            or session_ids.intersection(ids)
        ):
            raise StudyValidationError("groups contain invalid or duplicate identities")
        group_ids.add(item_id)
        session_ids.update(ids)
    if len(session_ids) != planned:
        raise StudyValidationError("group session total must equal planned sessions")
    summary_ids: set[str] = set()
    summary_analyzed = 0
    summary_correct = 0
    for summary_value in summaries:
        summary = _require_mapping(summary_value, "item summary")
        _require_exact_keys(
            summary,
            {
                "physical_item_id",
                "analyzed_observations",
                "count_correct",
                "predicted_ready",
                "guidance_decisions",
            },
            "item summary",
        )
        item_id = summary["physical_item_id"]
        if type(item_id) is not str or not item_id or item_id in summary_ids:
            raise StudyValidationError("item summary identity is invalid or duplicated")
        summary_ids.add(item_id)
        observations = _require_nonnegative_int(
            summary["analyzed_observations"], "item analyzed observations"
        )
        correct = _require_nonnegative_int(summary["count_correct"], "item count correct")
        predicted = _require_nonnegative_int(summary["predicted_ready"], "item predicted ready")
        guidance = _require_nonnegative_int(
            summary["guidance_decisions"], "item guidance decisions"
        )
        if max(correct, predicted, guidance) > observations:
            raise StudyValidationError("item summary count exceeds analyzed observations")
        summary_analyzed += observations
        summary_correct += correct
    if summary_ids != group_ids or summary_analyzed != analyzed or summary_correct != count_correct:
        raise StudyValidationError("item summaries are incoherent with groups or metrics")
    if sum(summary["analyzed_observations"] > 0 for summary in summaries) != clusters:
        raise StudyValidationError("item summaries do not match physical item clusters")

    _validate_reason_counts(document["missing_reasons"], "missing reasons", missing)
    _validate_reason_counts(document["exclusion_reasons"], "exclusion reasons", excluded)
    boundary = _require_mapping(document["claim_boundary"], "claim boundary")
    if boundary != {
        "live_and_public_denominators_separate": True,
        "production_validation": False,
        "payload_decode": False,
        "onnx_detector_implemented": False,
    }:
        raise StudyValidationError("report claim boundary is unsafe")
    canonical_json_bytes(document)


def public_supplement_omitted_report() -> dict[str, Any]:
    report = {
        "schema_version": "b26-public-supplement-report-v1",
        "protocol_version": "B26-live-v1.0",
        "study_track": "offline_public_supplement",
        "status": "public_supplement_omitted",
        "scope": "offline-detector-only-no-live-claims",
        "dataset": None,
        "denominators": {"eligible_images": 0, "excluded_images": 0, "missing_images": 0},
        "omission": {
            "reason_code": "dataset_rights_and_provenance_unverified",
            "candidates_audited": 4,
        },
        "claim_boundary": {
            "physical_guidance": False,
            "ready_light": False,
            "camera_lifecycle": False,
            "live_robustness": False,
            "payload_decode": False,
        },
    }
    validate_public_supplement_report(report)
    return report


def validate_public_supplement_report(report: object) -> None:
    document = _require_mapping(report, "public supplement report")
    _require_exact_keys(
        document,
        {
            "schema_version",
            "protocol_version",
            "study_track",
            "status",
            "scope",
            "dataset",
            "denominators",
            "omission",
            "claim_boundary",
        },
        "public supplement report",
    )
    if document["schema_version"] != "b26-public-supplement-report-v1":
        raise StudyValidationError("unsupported public supplement schema_version")
    if document["study_track"] != "offline_public_supplement":
        raise StudyValidationError("public supplement track is invalid")
    if document["status"] != "public_supplement_omitted" or document["dataset"] is not None:
        raise StudyValidationError("omitted public supplement cannot identify a dataset")
    if document["denominators"] != {
        "eligible_images": 0,
        "excluded_images": 0,
        "missing_images": 0,
    }:
        raise StudyValidationError("omitted public supplement denominators must remain zero")
    boundary = _require_mapping(document["claim_boundary"], "public claim boundary")
    if boundary != {
        "physical_guidance": False,
        "ready_light": False,
        "camera_lifecycle": False,
        "live_robustness": False,
        "payload_decode": False,
    }:
        raise StudyValidationError("public supplement claim boundary is unsafe")
    canonical_json_bytes(document)
