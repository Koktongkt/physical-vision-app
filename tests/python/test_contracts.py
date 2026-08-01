import json
from pathlib import Path

import physical_vision_contracts
import pytest
from physical_vision_contracts import (
    AnalysisResult,
    Completion,
    ContractValidationError,
    FailureEnvelope,
    PolicyDecision,
    RetainedPhotoLifecycle,
    VisionEvidenceSnapshot,
    validate_document,
)

ROOT = Path(__file__).parents[2]


def test_complete_vision_evidence_snapshot_is_valid() -> None:
    fixture = ROOT / "packages/contracts/fixtures/valid/vision-evidence-snapshot.json"

    validate_document("vision-evidence-snapshot", fixture)


def test_automatic_completion_result_with_full_provenance_is_valid() -> None:
    fixture = ROOT / "packages/contracts/fixtures/valid/automatic-complete-result.json"

    validate_document("analysis-result", fixture)


@pytest.mark.parametrize(
    ("schema_file", "contract_type"),
    [
        ("analysis-result.schema.json", AnalysisResult),
        ("completion.schema.json", Completion),
        ("failure-envelope.schema.json", FailureEnvelope),
        ("policy-decision.schema.json", PolicyDecision),
        ("retained-photo-lifecycle.schema.json", RetainedPhotoLifecycle),
        ("vision-evidence-snapshot.schema.json", VisionEvidenceSnapshot),
    ],
)
def test_python_contract_types_expose_every_schema_required_field(
    schema_file: str,
    contract_type: type,
) -> None:
    schema_path = ROOT / "packages/contracts/schemas/v3.0" / schema_file
    required = set(json.loads(schema_path.read_text(encoding="utf-8"))["required"])

    assert required == contract_type.__required_keys__


@pytest.mark.parametrize(
    ("schema_file", "contract_type_name"),
    [
        ("vision-evidence-snapshot.schema.json", "VisionEvidenceSnapshotV31"),
        ("policy-decision.schema.json", "PolicyDecisionV31"),
    ],
)
def test_python_v31_types_expose_every_schema_required_field(
    schema_file: str, contract_type_name: str
) -> None:
    schema_path = ROOT / "packages/contracts/schemas/v3.1" / schema_file
    required = set(json.loads(schema_path.read_text(encoding="utf-8"))["required"])

    contract_type = getattr(physical_vision_contracts, contract_type_name, None)
    assert contract_type is not None
    assert required == contract_type.__required_keys__


def test_v31_preserves_v30_policy_action_referent_conditionals() -> None:
    v30 = json.loads(
        (ROOT / "packages/contracts/schemas/v3.0/policy-decision.schema.json").read_text(
            encoding="utf-8"
        )
    )
    v31 = json.loads(
        (ROOT / "packages/contracts/schemas/v3.1/policy-decision.schema.json").read_text(
            encoding="utf-8"
        )
    )
    action30 = v30["properties"]["primary_action"]
    action31 = v31["properties"]["primary_action"]
    expected_conditionals = json.loads(json.dumps(action30["allOf"]))
    camera_actions = expected_conditionals[0]["if"]["properties"]["kind"]["enum"]
    camera_actions[2:2] = ["camera_up", "camera_down"]

    assert action31["type"] == action30["type"]
    assert action31["allOf"] == expected_conditionals


@pytest.mark.parametrize(
    ("fixture_name", "raw_string"),
    [
        ("positive-unsupported-no-label-unreadable.json", "SYNTH-31"),
        ("unknown-multiple-labels-ambiguous-ocr.json", ""),
    ],
)
def test_v31_rejects_incoherent_ocr_reason_evidence(fixture_name: str, raw_string: str) -> None:
    fixture = ROOT / "packages/contracts/fixtures/v3.1/valid" / fixture_name
    document = json.loads(fixture.read_text(encoding="utf-8"))
    document["ocr"]["raw_string"] = raw_string
    document["ocr"]["displayed_string"] = raw_string

    with pytest.raises(ContractValidationError, match=r"ocr\.reason"):
        validate_document("vision-evidence-snapshot", document)


def _cases(group: str) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for version, fixture_root in (
        ("v3.0", ROOT / "packages/contracts/fixtures"),
        ("v3.1", ROOT / "packages/contracts/fixtures/v3.1"),
    ):
        manifest_path = fixture_root / group / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases.extend(
            case | {"path": str(fixture_root / group / case["file"]), "version": version}
            for case in manifest
        )
    return cases


@pytest.mark.parametrize(
    "case", _cases("valid"), ids=lambda case: f"{case['version']}/{case['file']}"
)
def test_checked_in_valid_fixtures_conform(case: dict[str, str]) -> None:
    fixture = Path(case["path"])

    validate_document(case["kind"], fixture)


@pytest.mark.parametrize(
    "case", _cases("invalid"), ids=lambda case: f"{case['version']}/{case['file']}"
)
def test_checked_in_invalid_fixtures_fail_for_intended_reason(
    case: dict[str, str],
) -> None:
    fixture = Path(case["path"])

    with pytest.raises(ContractValidationError, match=case["error_contains"]):
        validate_document(case["kind"], fixture)
