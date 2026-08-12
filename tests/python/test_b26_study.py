from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import physical_vision_study as study
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
PATHS = (("desktop-webcam", "desktop_webcam"), ("phone-camera", "phone_camera"))
ITEMS = tuple(f"item-{index:03d}" for index in range(1, 9))
REASONS = ["capture_path_unavailable", "operator_exit"]


@pytest.fixture(autouse=True)
def _fast_private_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    def fast_interval(rows, sessions, predicate, eligible, *, replicates):
        denominator = sum(eligible(row) for row in rows)
        if not denominator:
            return {"lower": None, "upper": None, "usable_replicates": 0}
        value = round(sum(predicate(row) and eligible(row) for row in rows) / denominator, 6)
        return {"lower": value, "upper": value, "usable_replicates": 10000}

    monkeypatch.setattr(study, "_cluster_interval", fast_interval)


def _subgroups(index: int, *, control: bool = False) -> dict[str, str]:
    return {
        "barcode_family": "unknown"
        if control
        else ("ean_upc_like" if index % 2 else "code128_like"),
        "scale_distance": "unknown" if control else "2_to_8_percent",
        "angle_skew": "unknown" if control else "nominal",
        "blur_motion": "unknown" if control else "none",
        "crop_margin": "unknown" if control else "clear",
        "glare_exposure": "unknown" if control else "none",
        "background_clutter": "plain" if index % 2 else "cluttered",
        "ordinary_appearance": "other_unknown" if control else "matte",
    }


def _manifest() -> dict:
    sessions: list[dict] = []
    order = 1
    controls = (
        ("ordinary_zero_code", "none", "hard_negative", "ordinary_zero_code"),
        ("stripe_text_hard_negative", "none", "hard_negative", "stripe_text_hard_negative"),
        ("two_visible_supported_1d", "multiple", "supported_1d", "two_visible_supported_1d"),
        ("qr_only", "2d_only", "unsupported_2d", "qr_only"),
    )
    for path_id, _ in PATHS:
        for index, item_id in enumerate(ITEMS, 1):
            sessions.append(
                {
                    "order": order,
                    "session_id": f"session-{order:03d}",
                    "physical_item_id": item_id,
                    "capture_path_id": path_id,
                    "control_kind": "supported_single",
                    "scene_truth": "one",
                    "target_support": "supported_1d",
                    "assigned_challenge": "nominal" if index % 2 else "angle_skew",
                    "subgroups": _subgroups(index),
                    "max_observations": 6,
                }
            )
            order += 1
        for control_kind, truth, support, challenge in controls:
            sessions.append(
                {
                    "order": order,
                    "session_id": f"session-{order:03d}",
                    "physical_item_id": f"control-{path_id}-{control_kind}",
                    "capture_path_id": path_id,
                    "control_kind": control_kind,
                    "scene_truth": truth,
                    "target_support": support,
                    "assigned_challenge": challenge,
                    "subgroups": _subgroups(order, control=True),
                    "max_observations": 6,
                }
            )
            order += 1
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
            "report_schema": "b26-study-report-v2",
            "opencv": "4.12.0.88",
            "detector_recipe": "barcode-frame-v1",
            "ready_policy": "barcode-ready-v1",
            "guidance_policy": "barcode-guidance-v1",
            "python": "3.11.15",
            "browser": "Chrome-140",
            "os": "Windows-10",
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
                "capture_path_id": path_id,
                "path_role": role,
                "device": f"{path_id}-device",
                "camera": "primary-camera",
                "resolution": [1280, 720],
                "sample_rate_hz": 1.0,
            }
            for path_id, role in PATHS
        ],
        "allowed_reason_codes": REASONS.copy(),
        "sessions": sessions,
    }


def _locked() -> dict:
    return lock_manifest(_manifest(), locked_at="2026-08-12T20:00:00Z", signer_id="operator-a")


def _observation(
    locked: dict, session_id: str, *, index: int = 1, end: str | None = "user_exit"
) -> dict:
    planned = next(row for row in locked["manifest"]["sessions"] if row["session_id"] == session_id)
    truth = planned["scene_truth"]
    human_count = "unknown" if truth == "2d_only" else truth
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
            "target_support": planned["target_support"],
            "ready": "not_ready",
            "guidance_eligible": False,
        },
        "system": {
            "count": human_count,
            "ready": False,
            "guidance_actions": [],
            "localization_success": True if human_count == "one" else None,
        },
        "guidance_transition": None,
        "unsafe": False,
        "latency_ms": 21.0,
        "session_end": end,
    }


def _all_analyzed(locked: dict) -> list[dict]:
    return [_observation(locked, row["session_id"]) for row in locked["manifest"]["sessions"]]


def _accounting(locked: dict, disposition: str = "missing") -> list[dict]:
    return [
        {
            "schema_version": "b26-study-observation-v1",
            "manifest_fingerprint": locked["lock"]["fingerprint"],
            "study_track": "live_physical",
            "run_kind": "locked",
            "session_id": row["session_id"],
            "observation_index": 1,
            "disposition": disposition,
            "reason_code": REASONS[0 if disposition == "missing" else 1],
        }
        for row in locked["manifest"]["sessions"]
    ]


def _completed_report() -> dict:
    locked = _locked()
    return aggregate_live_report(locked, _all_analyzed(locked))


def _set_path(document: dict, path: tuple[str | int, ...], value: object) -> None:
    target: object = document
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]


def test_exact_manifest_locks_and_detects_mutation() -> None:
    manifest = _manifest()
    validate_manifest(manifest)
    assert [path["path_role"] for path in manifest["capture_paths"]] == [
        "desktop_webcam",
        "phone_camera",
    ]
    assert len(manifest["sessions"]) == 24
    supported = [row for row in manifest["sessions"] if row["control_kind"] == "supported_single"]
    assert len({row["physical_item_id"] for row in supported}) == 8
    assert all(
        sum(row["physical_item_id"] == item and row["capture_path_id"] == path for row in supported)
        == 1
        for item in ITEMS
        for path, _ in PATHS
    )
    controls = [row for row in manifest["sessions"] if row["control_kind"] != "supported_single"]
    assert all(sum(row["capture_path_id"] == path for row in controls) == 4 for path, _ in PATHS)
    locked = _locked()
    verify_manifest_lock(locked)
    assert locked["manifest"] == manifest
    assert canonical_json_bytes(manifest).endswith(b"\n")
    locked["manifest"]["sessions"][0]["assigned_challenge"] = "blur_motion"
    with pytest.raises(StudyValidationError, match="fingerprint"):
        verify_manifest_lock(locked)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("one_path", "capture path"),
        ("wrong_path_role", "path role"),
        ("duplicate_path_role", "path role"),
        ("twenty_three_sessions", "24"),
        ("noncontiguous_order", "contiguous"),
        ("duplicate_session", "unique"),
        ("seven_items", "eight|each supported"),
        ("item_missing_path", "eight|each supported"),
        ("duplicate_item_path", "each supported"),
        ("three_controls", "controls|supported"),
        ("control_kind", "control"),
        ("control_truth", "control"),
        ("control_support", "control"),
        ("supported_kind", "control|supported"),
        ("reason_extra", "reason"),
        ("reason_order", "reason"),
        ("resolution_shape", "resolution"),
        ("resolution_bool", "resolution"),
        ("resolution_zero", "resolution"),
        ("resolution_large", "resolution"),
        ("sample_rate_zero", "sample rate"),
        ("sample_rate_bool", "sample rate"),
        ("sample_rate_large", "sample rate"),
        ("unsafe_id", "bounded safe|safe bounded"),
        ("long_text", "bounded safe|safe bounded"),
        ("bad_subgroup", "subgroup"),
        ("extra_subgroup", "subgroup"),
        ("max_five", "six"),
    ],
)
def test_manifest_mutations_fail_closed(mutation: str, match: str) -> None:
    manifest = _manifest()
    if mutation == "one_path":
        manifest["capture_paths"].pop()
    elif mutation == "wrong_path_role":
        manifest["capture_paths"][0]["path_role"] = "webcam"
    elif mutation == "duplicate_path_role":
        manifest["capture_paths"][1]["path_role"] = "desktop_webcam"
    elif mutation == "twenty_three_sessions":
        manifest["sessions"].pop()
    elif mutation == "noncontiguous_order":
        manifest["sessions"][1]["order"] = 3
    elif mutation == "duplicate_session":
        manifest["sessions"][1]["session_id"] = manifest["sessions"][0]["session_id"]
    elif mutation == "seven_items":
        manifest["sessions"][7]["physical_item_id"] = ITEMS[0]
    elif mutation == "item_missing_path":
        manifest["sessions"][12]["physical_item_id"] = "item-009"
    elif mutation == "duplicate_item_path":
        manifest["sessions"][13]["physical_item_id"] = ITEMS[0]
    elif mutation == "three_controls":
        manifest["sessions"][11]["control_kind"] = "supported_single"
    elif mutation == "control_kind":
        manifest["sessions"][8]["control_kind"] = "bogus"
    elif mutation == "control_truth":
        manifest["sessions"][8]["scene_truth"] = "one"
    elif mutation == "control_support":
        manifest["sessions"][10]["target_support"] = "hard_negative"
    elif mutation == "supported_kind":
        manifest["sessions"][0]["control_kind"] = "ordinary_zero"
    elif mutation == "reason_extra":
        manifest["allowed_reason_codes"].append("other")
    elif mutation == "reason_order":
        manifest["allowed_reason_codes"].reverse()
    elif mutation == "resolution_shape":
        manifest["capture_paths"][0]["resolution"] = [1280]
    elif mutation == "resolution_bool":
        manifest["capture_paths"][0]["resolution"] = [True, 720]
    elif mutation == "resolution_zero":
        manifest["capture_paths"][0]["resolution"] = [0, 720]
    elif mutation == "resolution_large":
        manifest["capture_paths"][0]["resolution"] = [20000, 720]
    elif mutation == "sample_rate_zero":
        manifest["capture_paths"][0]["sample_rate_hz"] = 0
    elif mutation == "sample_rate_bool":
        manifest["capture_paths"][0]["sample_rate_hz"] = True
    elif mutation == "sample_rate_large":
        manifest["capture_paths"][0]["sample_rate_hz"] = 121
    elif mutation == "unsafe_id":
        manifest["operator"]["operator_id"] = "not safe!"
    elif mutation == "long_text":
        manifest["capture_paths"][0]["device"] = "a" * 65
    elif mutation == "bad_subgroup":
        manifest["sessions"][0]["subgroups"]["angle_skew"] = "invented"
    elif mutation == "extra_subgroup":
        manifest["sessions"][0]["subgroups"]["extra"] = "value"
    else:
        manifest["sessions"][0]["max_observations"] = 5
    with pytest.raises(StudyValidationError, match=match):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("locked_at", "signer"),
    [
        ("2026-02-30T20:00:00Z", "operator-a"),
        ("2026-08-12T20:00:00+00:00", "operator-a"),
        ("2026-08-12 20:00:00Z", "operator-a"),
        ("2026-08-12T20:00:00z", "operator-a"),
        ("2026-08-12T20:00:00Z", ""),
        ("2026-08-12T20:00:00Z", "private signer!"),
        ("2026-08-12T20:00:00Z", "a" * 65),
        ("2026-08-12T20:00:00Z", "C:/Users/private"),
    ],
)
def test_lock_metadata_fails_closed(locked_at: str, signer: str) -> None:
    with pytest.raises(StudyValidationError, match="lock metadata"):
        lock_manifest(_manifest(), locked_at=locked_at, signer_id=signer)


def test_verify_revalidates_lock_metadata_exact_shape_and_type() -> None:
    for mutation in ("time", "signer", "extra", "fingerprint_type"):
        locked = _locked()
        if mutation == "time":
            locked["lock"]["locked_at"] = "2026-02-30T20:00:00Z"
        elif mutation == "signer":
            locked["lock"]["signer_id"] = True
        elif mutation == "extra":
            locked["lock"]["extra"] = None
        else:
            locked["lock"]["fingerprint"] = 1
        with pytest.raises(StudyValidationError):
            verify_manifest_lock(locked)


def test_public_aggregation_api_has_no_replicate_override_and_reports_locked_10000() -> None:
    locked = _locked()
    with pytest.raises(TypeError):
        aggregate_live_report(locked, _all_analyzed(locked), bootstrap_replicates=20)  # type: ignore[call-arg]
    report = aggregate_live_report(locked, _all_analyzed(locked))
    assert report["confidence_method"]["seed"] == 260826
    assert report["confidence_method"]["replicates"] == 10000
    validate_report(report)
    report["confidence_method"]["replicates"] = 20
    with pytest.raises(StudyValidationError, match="confidence"):
        validate_report(report)


def test_completed_requires_full_24_session_coverage() -> None:
    locked = _locked()
    report = aggregate_live_report(locked, _all_analyzed(locked))
    assert report["status"] == "completed_locked_run"
    assert report["denominators"]["attempted_sessions"] == 24
    assert report["denominators"]["missing_sessions"] == 0
    assert report["denominators"]["excluded_sessions"] == 0


@pytest.mark.parametrize("partial", ["missing", "excluded", "unaccounted"])
def test_partial_analyzed_evidence_fails_closed(partial: str) -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    rows.pop()
    if partial != "unaccounted":
        accounting = _accounting(locked, partial)[-1]
        rows.append(accounting)
    with pytest.raises(
        StudyValidationError, match="partial|completed|every planned|accounting row"
    ):
        aggregate_live_report(locked, rows)


def test_zero_evidence_all_accounted_remains_pending() -> None:
    locked = _locked()
    report = aggregate_live_report(locked, _accounting(locked))
    assert report["status"] == "live_pending"
    assert report["denominators"]["planned_sessions"] == 24
    assert report["denominators"]["analyzed_observations"] == 0


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
def test_each_product_action_is_accepted(action: str) -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    rows[0]["system"]["guidance_actions"] = [action]
    rows[0]["human"]["guidance_eligible"] = True
    aggregate_live_report(locked, rows)


@pytest.mark.parametrize("actions", [["move_closer"], ["tilt"], ["camera_left", "camera_up"]])
def test_fictional_or_multiple_actions_fail(actions: list[str]) -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    rows[0]["system"]["guidance_actions"] = actions
    with pytest.raises(StudyValidationError, match="guidance"):
        aggregate_live_report(locked, rows)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("human", "target_support"), "supported"),
        (("human", "target_support"), True),
        (("human", "count"), True),
        (("system", "count"), True),
        (("system", "localization_success"), 1),
        (("system", "localization_success"), "true"),
        (("latency_ms",), -0.001),
        (("latency_ms",), True),
        (("latency_ms",), float("inf")),
        (("latency_ms",), float("nan")),
    ],
)
def test_observation_exact_types_and_latency_fail_closed(
    path: tuple[str, ...], value: object
) -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    _set_path(rows[0], path, value)
    with pytest.raises(StudyValidationError):
        aggregate_live_report(locked, rows)


@pytest.mark.parametrize(
    "mutation",
    [
        "none_supported",
        "one_hard_negative",
        "unknown_supported",
        "human_ready_guidance_eligible",
        "system_nonone_ready",
        "system_nonone_guidance",
        "system_nonone_localized",
        "system_one_localization_null",
        "system_ready_localization_false",
        "system_guidance_localization_false",
        "guidance_human_count_veto",
        "guidance_human_support_veto",
    ],
)
def test_observation_count_support_decision_coherence_fails_closed(mutation: str) -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    row = rows[0]
    if mutation == "none_supported":
        row["human"]["count"] = "none"
    elif mutation == "one_hard_negative":
        row["human"]["target_support"] = "hard_negative"
    elif mutation == "unknown_supported":
        row["human"]["count"] = "unknown"
        row["system"]["count"] = "unknown"
        row["system"]["localization_success"] = None
    elif mutation == "human_ready_guidance_eligible":
        row["human"]["ready"] = "ready"
        row["human"]["guidance_eligible"] = True
    elif mutation == "system_nonone_ready":
        row["system"].update(count="none", ready=True, localization_success=None)
    elif mutation == "system_nonone_guidance":
        row["system"].update(
            count="none", guidance_actions=["camera_closer"], localization_success=None
        )
    elif mutation == "system_nonone_localized":
        row["system"].update(count="none", localization_success=True)
    elif mutation == "system_one_localization_null":
        row["system"]["localization_success"] = None
    elif mutation == "system_ready_localization_false":
        row["system"].update(ready=True, localization_success=False)
    elif mutation == "system_guidance_localization_false":
        row["system"].update(guidance_actions=["camera_closer"], localization_success=False)
    elif mutation == "guidance_human_count_veto":
        row["human"].update(count="none", target_support="hard_negative")
        row["system"]["guidance_actions"] = ["camera_closer"]
    else:
        row["human"]["target_support"] = "unsupported_2d"
        row["system"]["guidance_actions"] = ["camera_closer"]
    with pytest.raises(
        StudyValidationError, match="count|support|ready|guidance|localization|veto"
    ):
        aggregate_live_report(locked, rows)


def test_unsafe_not_evaluable_is_included_in_safety_metric() -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    rows[0]["unsafe"] = True
    rows[0]["guidance_transition"] = "not_evaluable"
    report = aggregate_live_report(locked, rows)
    assert report["metrics"]["unsafe_or_worsening"]["numerator"] == 1
    assert report["metrics"]["unsafe_or_worsening"]["denominator"] == 1


def test_live_report_metrics_are_cross_bound_to_independent_evidence() -> None:
    report = _completed_report()
    assert set(report["metric_evidence"]) == {
        "count_evaluable",
        "count_correct",
        "human_not_ready",
        "false_ready",
        "ready_evaluable",
        "predicted_ready",
        "ready_correct",
        "abstention_required",
        "system_abstained",
        "guidance_eligibility_evaluable",
        "guidance_eligibility_correct",
        "localization_eligible",
        "localization_succeeded",
        "guidance_displayed",
        "exactly_one_action",
        "transition_evaluable",
        "transition_improving",
        "safety_evaluable",
        "unsafe_or_worsening",
    }
    for metric_name in report["metrics"]:
        forged = copy.deepcopy(report)
        metric = forged["metrics"][metric_name]
        metric["denominator"] += 1
        metric["value"] = round(metric["numerator"] / metric["denominator"], 6)
        with pytest.raises(StudyValidationError, match="metric|evidence|incoherent"):
            validate_report(forged)


def test_live_report_metric_evidence_mutations_fail_closed() -> None:
    report = _completed_report()
    for counter in report["metric_evidence"]:
        forged = copy.deepcopy(report)
        forged["metric_evidence"][counter] += 1
        with pytest.raises(StudyValidationError):
            validate_report(forged)


@pytest.mark.parametrize(
    "mutation",
    [
        "starts_at_two",
        "gap",
        "missing_terminal",
        "terminal_not_last",
        "row_after_terminal",
        "early_max",
    ],
)
def test_session_sequence_fails_closed(mutation: str) -> None:
    locked = _locked()
    rows = _all_analyzed(locked)
    first = rows.pop(0)
    first["session_end"] = None
    second = copy.deepcopy(first)
    second["observation_index"] = 2
    second["session_end"] = "user_exit"
    rows.extend([first, second])
    if mutation == "starts_at_two":
        first["observation_index"], second["observation_index"] = 2, 3
    elif mutation == "gap":
        second["observation_index"] = 3
    elif mutation == "missing_terminal":
        second["session_end"] = None
    elif mutation == "terminal_not_last":
        first["session_end"] = "user_exit"
        second["session_end"] = None
    elif mutation == "row_after_terminal":
        first["session_end"] = "user_exit"
    else:
        second["session_end"] = "max_observations"
    with pytest.raises(StudyValidationError, match="session|terminal|contiguous|max_observations"):
        aggregate_live_report(locked, rows)


def test_public_report_is_strict_and_content_free() -> None:
    base = json.loads((ROOT / "docs/B26_PUBLIC_SUPPLEMENT_REPORT.json").read_text())
    validate_public_supplement_report(base)
    mutations = [
        (("protocol_version",), "wrong"),
        (("scope",), "live"),
        (("denominators", "eligible_images"), True),
        (("denominators", "excluded_images"), 1),
        (("omission", "reason_code"), "other"),
        (("omission", "candidates_audited"), -1),
        (("omission", "candidates_audited"), True),
        (("omission", "candidates_audited"), 1000001),
        (("claim_boundary", "ready_light"), True),
    ]
    for path, value in mutations:
        report = copy.deepcopy(base)
        _set_path(report, path, value)
        with pytest.raises(StudyValidationError):
            validate_public_supplement_report(report)
    unsafe = copy.deepcopy(base)
    unsafe["omission"]["private_path"] = "C:/Users/Private/frame.jpg"
    with pytest.raises(StudyValidationError) as raised:
        validate_public_supplement_report(unsafe)
    assert str(raised.value) == "document contains prohibited sensitive content"
    assert "Private" not in str(raised.value)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("protocol_version",), "wrong"),
        (("scope",), "validation"),
        (("denominators", "planned_sessions"), 23),
        (("denominators", "missing_sessions"), 1),
        (("confidence_method", "confidence"), 1.5),
        (("confidence_method", "seed"), True),
        (("confidence_method", "replicates"), 20),
        (("metrics", "count_accuracy", "interval_95", "usable_replicates"), 10001),
        (("count_confusion", "one", "one"), 99),
        (("latency_ms", "count"), 99),
        (("guidance_transitions", "improving"), 99),
        (("diagnostics", "false_single_count"), 99),
        (("attempts_to_ready", "reached_ready_sessions"), 99),
        (("session_outcomes", "user_exit"), 99),
        (("item_summaries", 0, "analyzed_observations"), 99),
        (("groups", 0, "session_ids"), []),
    ],
)
def test_versioned_report_mutations_fail_closed(path: tuple[str | int, ...], value: object) -> None:
    report = _completed_report()
    _set_path(report, path, value)
    with pytest.raises(StudyValidationError):
        validate_report(report)


def test_public_supplement_cli_preserves_omitted_report(tmp_path: Path) -> None:
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
    validate_public_supplement_report(json.loads(output.read_text()))

    validated = subprocess.run(
        [
            sys.executable,
            "scripts/run_b26_study.py",
            "validate",
            "--kind",
            "public-report",
            "--input",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr
    assert validated.stdout == "valid public-report\n"
