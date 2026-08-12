from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from physical_vision_study import (
    StudyValidationError,
    aggregate_live_report,
    canonical_json_bytes,
    lock_manifest,
    validate_manifest,
    validate_public_supplement_report,
    validate_report,
    verify_manifest_lock,
)

ROOT = Path(__file__).parents[2]


def _manifest() -> dict:
    return {
        "schema_version": "b26-study-manifest-v1",
        "protocol_version": "B26-live-v1.0",
        "study_track": "live_physical",
        "run_kind": "locked",
        "repository": {
            "commit": "af0541ea8f69bcf665aac9135017b6600906fb50",
            "clean": True,
            "app_build": "stage8-af0541e",
        },
        "versions": {
            "report_schema": "b26-study-report-v1",
            "opencv": "4.12.0.88",
            "detector_recipe": "barcode-frame-v1",
            "ready_policy": "barcode-ready-v1",
            "guidance_policy": "barcode-guidance-v1",
            "python": "3.11.15",
            "browser": "Chrome 140.0",
            "os": "Windows 10",
        },
        "configuration": {
            "decode_payload": False,
            "learned_detector": False,
            "max_observations_per_session": 6,
            "bootstrap_seed": 260826,
            "bootstrap_replicates": 10000,
            "ready_thresholds": {"minimum_area_ratio": 0.02},
            "measurement_tolerances": {"area_ratio": 0.001},
            "resource_limits": {"max_in_flight": 1},
        },
        "operator": {"operator_id": "operator-a", "labeler_id": "labeler-a"},
        "capture_paths": [
            {
                "capture_path_id": "desktop-webcam",
                "device": "integrated-webcam",
                "camera": "front-camera",
                "resolution": [1280, 720],
                "sample_rate_hz": 1.0,
            }
        ],
        "allowed_reason_codes": ["capture_path_unavailable", "operator_exit"],
        "sessions": [
            {
                "order": 1,
                "session_id": "session-001",
                "physical_item_id": "item-001",
                "capture_path_id": "desktop-webcam",
                "scene_truth": "one",
                "target_support": "supported_1d",
                "assigned_challenge": "nominal",
                "subgroups": {
                    "barcode_family": "ean_upc_like",
                    "scale_distance": "2_to_8_percent",
                    "angle_skew": "nominal",
                    "blur_motion": "none",
                    "crop_margin": "clear",
                    "glare_exposure": "none",
                    "background_clutter": "plain",
                    "ordinary_appearance": "matte",
                },
                "max_observations": 6,
            },
            {
                "order": 2,
                "session_id": "session-002",
                "physical_item_id": "control-zero-001",
                "capture_path_id": "desktop-webcam",
                "scene_truth": "none",
                "target_support": "hard_negative",
                "assigned_challenge": "background_clutter",
                "subgroups": {
                    "barcode_family": "unknown",
                    "scale_distance": "unknown",
                    "angle_skew": "severe_unknown",
                    "blur_motion": "unknown",
                    "crop_margin": "unknown",
                    "glare_exposure": "unknown",
                    "background_clutter": "cluttered_stripe_text",
                    "ordinary_appearance": "other_unknown",
                },
                "max_observations": 6,
            },
        ],
    }


def test_manifest_validation_and_lock_detect_post_lock_mutation() -> None:
    manifest = _manifest()

    validate_manifest(manifest)
    locked = lock_manifest(manifest, locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")

    assert locked["manifest"] == manifest
    assert locked["lock"]["algorithm"] == "sha256"
    assert (
        locked["lock"]["fingerprint"]
        == lock_manifest(
            copy.deepcopy(manifest),
            locked_at="2026-08-12T20:00:00Z",
            signer_id="operator-a",
        )["lock"]["fingerprint"]
    )
    assert canonical_json_bytes(manifest).endswith(b"\n")
    verify_manifest_lock(locked)

    locked["manifest"]["sessions"][0]["assigned_challenge"] = "blur_motion"
    with pytest.raises(StudyValidationError, match="fingerprint"):
        verify_manifest_lock(locked)


def test_manifest_validation_rejects_dry_run_rows_in_locked_track() -> None:
    manifest = _manifest()
    manifest["sessions"][0]["run_kind"] = "dry_run"

    with pytest.raises(StudyValidationError, match="run_kind"):
        validate_manifest(manifest)


def test_manifest_validation_requires_all_frozen_version_and_operator_fields() -> None:
    manifest = _manifest()
    del manifest["versions"]["browser"]

    with pytest.raises(StudyValidationError, match="versions"):
        validate_manifest(manifest)

    manifest = _manifest()
    manifest["operator"]["private_name"] = "not-allowed"
    with pytest.raises(StudyValidationError, match="operator"):
        validate_manifest(manifest)


def _observation(
    locked: dict,
    *,
    session_id: str,
    index: int,
    human_count: str,
    predicted_count: str,
    human_ready: str,
    predicted_ready: bool,
    guidance_actions: list[str],
    localization_success: bool | None,
    transition: str | None = None,
    session_end: str | None = None,
) -> dict:
    return {
        "schema_version": "b26-study-observation-v1",
        "manifest_fingerprint": locked["lock"]["fingerprint"],
        "study_track": "live_physical",
        "run_kind": "locked",
        "session_id": session_id,
        "observation_index": index,
        "disposition": "analyzed",
        "reason_code": None,
        "human": {
            "count": human_count,
            "target_support": "supported_1d" if human_count == "one" else "hard_negative",
            "ready": human_ready,
            "guidance_eligible": bool(guidance_actions),
        },
        "system": {
            "count": predicted_count,
            "ready": predicted_ready,
            "guidance_actions": guidance_actions,
            "localization_success": localization_success,
        },
        "guidance_transition": transition,
        "unsafe": False,
        "latency_ms": 20.0 + index,
        "session_end": session_end
        if session_end is not None
        else ("ready_shutter" if predicted_ready else "user_exit"),
    }


def test_live_aggregation_is_deterministic_grouped_and_reports_full_denominators() -> None:
    manifest = _manifest()
    manifest["sessions"].append(
        {
            **manifest["sessions"][0],
            "order": 3,
            "session_id": "session-003",
            "capture_path_id": "desktop-webcam",
        }
    )
    locked = lock_manifest(manifest, locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")
    observations = [
        _observation(
            locked,
            session_id="session-001",
            index=1,
            human_count="one",
            predicted_count="one",
            human_ready="not_ready",
            predicted_ready=False,
            guidance_actions=["camera_closer"],
            localization_success=True,
            transition="improving",
        ),
        _observation(
            locked,
            session_id="session-002",
            index=1,
            human_count="none",
            predicted_count="one",
            human_ready="not_ready",
            predicted_ready=True,
            guidance_actions=[],
            localization_success=None,
        ),
        {
            "schema_version": "b26-study-observation-v1",
            "manifest_fingerprint": locked["lock"]["fingerprint"],
            "study_track": "live_physical",
            "run_kind": "locked",
            "session_id": "session-003",
            "observation_index": 1,
            "disposition": "missing",
            "reason_code": "capture_path_unavailable",
        },
    ]

    first = aggregate_live_report(locked, list(reversed(observations)), bootstrap_replicates=200)
    second = aggregate_live_report(locked, observations, bootstrap_replicates=200)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    validate_report(first)
    assert first["status"] == "completed_locked_run"
    assert first["scope"] == "bounded-live-physical-mini-study-not-validation"
    assert first["denominators"] == {
        "planned_sessions": 3,
        "attempted_sessions": 2,
        "missing_sessions": 1,
        "excluded_sessions": 0,
        "analyzed_observations": 2,
        "physical_item_clusters": 2,
    }
    assert first["metrics"]["count_accuracy"]["numerator"] == 1
    assert first["metrics"]["count_accuracy"]["denominator"] == 2
    assert first["metrics"]["false_ready"]["numerator"] == 1
    assert first["metrics"]["false_ready"]["denominator"] == 2
    assert first["metrics"]["localization_success"]["denominator"] == 1
    assert first["metrics"]["exactly_one_action"]["numerator"] == 1
    assert first["metrics"]["guidance_improvement"]["denominator"] == 1
    assert first["metrics"]["required_abstention"]["denominator"] == 1
    assert first["metrics"]["required_abstention"]["numerator"] == 0
    assert first["metrics"]["ready_precision"]["denominator"] == 1
    assert first["metrics"]["guidance_eligibility"]["numerator"] == 2
    assert first["metrics"]["guidance_eligibility"]["denominator"] == 2
    assert first["diagnostics"] == {
        "false_single_count": 1,
        "unknown_prediction_count": 0,
        "veto_violation_count": 0,
    }
    assert first["attempts_to_ready"] == {
        "reached_ready_sessions": 1,
        "values": [1],
        "cumulative_sessions_by_attempt": {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1},
    }
    assert first["session_outcomes"] == {"ready_shutter": 1, "user_exit": 1}
    assert first["count_confusion"] == {
        "none": {"none": 0, "one": 1, "multiple": 0, "unknown": 0},
        "one": {"none": 0, "one": 1, "multiple": 0, "unknown": 0},
        "multiple": {"none": 0, "one": 0, "multiple": 0, "unknown": 0},
        "unknown": {"none": 0, "one": 0, "multiple": 0, "unknown": 0},
    }
    assert first["latency_ms"] == {"count": 2, "median": 21.0, "p95": 21.0, "maximum": 21.0}
    assert first["guidance_transitions"] == {
        "improving": 1,
        "unchanged": 0,
        "worsening": 0,
        "not_evaluable": 1,
    }
    assert first["subgroups"]["capture_path"] == {
        "desktop-webcam": {"analyzed_observations": 2, "physical_item_families": 2}
    }
    assert first["subgroups"]["ordinary_appearance"] == {
        "matte": {"analyzed_observations": 1, "physical_item_families": 1},
        "other_unknown": {"analyzed_observations": 1, "physical_item_families": 1},
    }
    assert first["item_summaries"] == [
        {
            "physical_item_id": "control-zero-001",
            "analyzed_observations": 1,
            "count_correct": 0,
            "predicted_ready": 1,
            "guidance_decisions": 0,
        },
        {
            "physical_item_id": "item-001",
            "analyzed_observations": 1,
            "count_correct": 1,
            "predicted_ready": 0,
            "guidance_decisions": 1,
        },
    ]
    assert first["confidence_method"] == {
        "name": "physical-item-cluster-bootstrap-percentile",
        "confidence": 0.95,
        "seed": 260826,
        "replicates": 200,
    }
    assert first["missing_reasons"] == {"capture_path_unavailable": 1}
    assert first["groups"] == [
        {"physical_item_id": "control-zero-001", "session_ids": ["session-002"]},
        {"physical_item_id": "item-001", "session_ids": ["session-001", "session-003"]},
    ]


def test_aggregation_refuses_manifest_mismatch_and_public_observation() -> None:
    locked = lock_manifest(_manifest(), locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")
    observation = _observation(
        locked,
        session_id="session-001",
        index=1,
        human_count="one",
        predicted_count="one",
        human_ready="ready",
        predicted_ready=True,
        guidance_actions=[],
        localization_success=True,
    )
    observation["study_track"] = "offline_public_supplement"

    with pytest.raises(StudyValidationError, match="live_physical"):
        aggregate_live_report(locked, [observation], bootstrap_replicates=20)

    observation["study_track"] = "live_physical"
    observation["manifest_fingerprint"] = "0" * 64
    with pytest.raises(StudyValidationError, match="fingerprint"):
        aggregate_live_report(locked, [observation], bootstrap_replicates=20)


@pytest.mark.parametrize(
    "field,value",
    [
        ("physical_item_id", "0123456789012"),
        ("physical_item_id", "C:/Users/Private/frame.jpg"),
        ("device", "http://attacker.invalid:5173"),
        ("camera", "data:image/png;base64,AAAA"),
        ("app_build", "RuntimeError: private analyzer detail"),
    ],
)
def test_manifest_privacy_canaries_are_rejected_content_free(field: str, value: str) -> None:
    manifest = _manifest()
    if field in manifest["repository"]:
        manifest["repository"][field] = value
    elif field in manifest["capture_paths"][0]:
        manifest["capture_paths"][0][field] = value
    else:
        manifest["sessions"][0][field] = value

    with pytest.raises(StudyValidationError) as raised:
        validate_manifest(manifest)

    assert value not in str(raised.value)
    assert str(raised.value) == "document contains prohibited sensitive content"


def test_public_supplement_omitted_cli_produces_valid_content_free_report(tmp_path: Path) -> None:
    output = tmp_path / "public-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_b26_study.py",
            "public-supplement",
            "--decision",
            "omitted",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "public supplement report: public_supplement_omitted\n"
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report == {
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


def test_all_missing_locked_sessions_remain_live_pending() -> None:
    locked = lock_manifest(_manifest(), locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")
    observations = [
        {
            "schema_version": "b26-study-observation-v1",
            "manifest_fingerprint": locked["lock"]["fingerprint"],
            "study_track": "live_physical",
            "run_kind": "locked",
            "session_id": session_id,
            "observation_index": 1,
            "disposition": "missing",
            "reason_code": "capture_path_unavailable",
        }
        for session_id in ("session-001", "session-002")
    ]

    report = aggregate_live_report(locked, observations, bootstrap_replicates=20)

    assert report["status"] == "live_pending"
    assert report["denominators"]["analyzed_observations"] == 0


def test_report_validation_rejects_inconsistent_status_and_metric_shape() -> None:
    locked = lock_manifest(_manifest(), locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")
    missing = [
        {
            "schema_version": "b26-study-observation-v1",
            "manifest_fingerprint": locked["lock"]["fingerprint"],
            "study_track": "live_physical",
            "run_kind": "locked",
            "session_id": session_id,
            "observation_index": 1,
            "disposition": "missing",
            "reason_code": "capture_path_unavailable",
        }
        for session_id in ("session-001", "session-002")
    ]
    report = aggregate_live_report(locked, missing, bootstrap_replicates=20)
    report["status"] = "completed_locked_run"

    with pytest.raises(StudyValidationError, match="status"):
        validate_report(report)

    report["status"] = "live_pending"
    report["metrics"]["count_accuracy"]["numerator"] = 1
    with pytest.raises(StudyValidationError, match="metric"):
        validate_report(report)


def test_public_report_validation_rejects_unsafe_or_incomplete_claim_boundary() -> None:
    report = json.loads((ROOT / "docs/B26_PUBLIC_SUPPLEMENT_REPORT.json").read_text())
    report["claim_boundary"].pop("ready_light")

    with pytest.raises(StudyValidationError, match="claim boundary"):
        validate_public_supplement_report(report)


def test_observation_privacy_canary_is_rejected_without_echo() -> None:
    locked = lock_manifest(_manifest(), locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")
    observation = _observation(
        locked,
        session_id="session-001",
        index=1,
        human_count="one",
        predicted_count="one",
        human_ready="not_ready",
        predicted_ready=False,
        guidance_actions=["C:/Users/Private/frame.jpg"],
        localization_success=True,
    )

    with pytest.raises(StudyValidationError) as raised:
        aggregate_live_report(locked, [observation], bootstrap_replicates=20)

    assert "C:/Users/Private/frame.jpg" not in str(raised.value)
    assert str(raised.value) == "document contains prohibited sensitive content"


def _locked() -> dict:
    return lock_manifest(_manifest(), locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")


def _analyzed_pair(locked: dict) -> list[dict]:
    first = _observation(
        locked,
        session_id="session-001",
        index=1,
        human_count="one",
        predicted_count="one",
        human_ready="not_ready",
        predicted_ready=False,
        guidance_actions=["camera_closer"],
        localization_success=True,
        transition="not_evaluable",
        session_end=None,
    )
    first["session_end"] = None
    second = _observation(
        locked,
        session_id="session-001",
        index=2,
        human_count="one",
        predicted_count="one",
        human_ready="ready",
        predicted_ready=True,
        guidance_actions=[],
        localization_success=True,
        transition="improving",
        session_end="ready_shutter",
    )
    missing = {
        "schema_version": "b26-study-observation-v1",
        "manifest_fingerprint": locked["lock"]["fingerprint"],
        "study_track": "live_physical",
        "run_kind": "locked",
        "session_id": "session-002",
        "observation_index": 1,
        "disposition": "missing",
        "reason_code": "capture_path_unavailable",
    }
    return [first, second, missing]


@pytest.mark.parametrize(
    "action",
    [
        "camera_closer",
        "camera_farther",
        "camera_left",
        "camera_right",
        "camera_up",
        "camera_down",
        "camera_steady",
        "reduce_glare",
    ],
)
def test_observation_accepts_each_product_guidance_action(action: str) -> None:
    locked = _locked()
    rows = _analyzed_pair(locked)
    rows[0]["system"]["guidance_actions"] = [action]
    aggregate_live_report(locked, rows, bootstrap_replicates=20)


@pytest.mark.parametrize("actions", [["move_closer"], ["tilt"], ["camera_left", "camera_up"]])
def test_observation_rejects_fictional_or_multiple_guidance_actions(actions: list[str]) -> None:
    locked = _locked()
    rows = _analyzed_pair(locked)
    rows[0]["system"]["guidance_actions"] = actions
    with pytest.raises(StudyValidationError, match="guidance"):
        aggregate_live_report(locked, rows, bootstrap_replicates=20)


@pytest.mark.parametrize(
    "mutation",
    [
        "starts_at_two",
        "gap",
        "missing_terminal",
        "terminal_not_last",
        "row_after_terminal",
        "early_max_observations",
    ],
)
def test_analyzed_session_sequence_fails_closed(mutation: str) -> None:
    locked = _locked()
    rows = _analyzed_pair(locked)
    if mutation == "starts_at_two":
        rows[0]["observation_index"] = 2
        rows[1]["observation_index"] = 3
    elif mutation == "gap":
        rows[1]["observation_index"] = 3
    elif mutation == "missing_terminal":
        rows[1]["session_end"] = None
    elif mutation == "terminal_not_last":
        rows[0]["session_end"] = "user_exit"
    elif mutation == "row_after_terminal":
        rows[0]["session_end"] = "user_exit"
        rows[1]["session_end"] = "ready_shutter"
    elif mutation == "early_max_observations":
        rows[1]["session_end"] = "max_observations"
    with pytest.raises(StudyValidationError, match="session|terminal|contiguous|max_observations"):
        aggregate_live_report(locked, rows, bootstrap_replicates=20)


def test_exclusion_reasons_are_aggregated_separately() -> None:
    locked = _locked()
    rows = [_analyzed_pair(locked)[0]]
    rows[0]["session_end"] = "user_exit"
    rows.append(
        {
            "schema_version": "b26-study-observation-v1",
            "manifest_fingerprint": locked["lock"]["fingerprint"],
            "study_track": "live_physical",
            "run_kind": "locked",
            "session_id": "session-002",
            "observation_index": 1,
            "disposition": "excluded",
            "reason_code": "operator_exit",
        }
    )
    report = aggregate_live_report(locked, rows, bootstrap_replicates=20)
    assert report["missing_reasons"] == {}
    assert report["exclusion_reasons"] == {"operator_exit": 1}


def _completed_report() -> dict:
    locked = _locked()
    return aggregate_live_report(locked, _analyzed_pair(locked), bootstrap_replicates=20)


def _set_path(document: dict, path: tuple[str | int, ...], value: object) -> None:
    target: object = document
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("protocol_version",), "wrong"),
        (("scope",), "validation"),
        (("denominators", "planned_sessions"), -1),
        (("denominators", "attempted_sessions"), 3),
        (("confidence_method", "confidence"), 1.5),
        (("confidence_method", "seed"), True),
        (("metrics", "count_accuracy", "interval_95", "lower"), -0.1),
        (("metrics", "count_accuracy", "interval_95", "usable_replicates"), 21),
        (("count_confusion", "one", "one"), 99),
        (("latency_ms", "count"), 99),
        (("latency_ms", "median"), -1.0),
        (("guidance_transitions", "improving"), 99),
        (("subgroups", "capture_path", "desktop-webcam", "analyzed_observations"), 99),
        (("diagnostics", "false_single_count"), 99),
        (("attempts_to_ready", "reached_ready_sessions"), 99),
        (("attempts_to_ready", "values"), [0]),
        (("session_outcomes", "ready_shutter"), 99),
        (("item_summaries", 0, "analyzed_observations"), 99),
        (("missing_reasons", "capture_path_unavailable"), 2),
        (("exclusion_reasons", "operator_exit"), 1),
        (("groups", 0, "session_ids"), []),
    ],
)
def test_versioned_report_adversarial_mutations_fail_closed(
    path: tuple[str | int, ...], value: object
) -> None:
    report = _completed_report()
    _set_path(report, path, value)
    with pytest.raises(StudyValidationError):
        validate_report(report)


def test_versioned_report_rejects_nested_extra_or_wrong_type() -> None:
    report = _completed_report()
    report["latency_ms"]["extra"] = 0
    with pytest.raises(StudyValidationError):
        validate_report(report)

    report = _completed_report()
    report["groups"] = "not-a-list"
    with pytest.raises(StudyValidationError):
        validate_report(report)
