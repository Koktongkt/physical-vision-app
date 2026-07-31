import json
from pathlib import Path

import pytest
from physical_vision_contracts import ContractValidationError, validate_document

ROOT = Path(__file__).parents[2]


def test_complete_vision_evidence_snapshot_is_valid() -> None:
    fixture = ROOT / "packages/contracts/fixtures/valid/vision-evidence-snapshot.json"

    validate_document("vision-evidence-snapshot", fixture)


def test_automatic_completion_result_with_full_provenance_is_valid() -> None:
    fixture = ROOT / "packages/contracts/fixtures/valid/automatic-complete-result.json"

    validate_document("analysis-result", fixture)


def _manifest(group: str) -> list[dict[str, str]]:
    path = ROOT / f"packages/contracts/fixtures/{group}/manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _manifest("valid"), ids=lambda case: case["file"])
def test_checked_in_valid_fixtures_conform(case: dict[str, str]) -> None:
    fixture = ROOT / "packages/contracts/fixtures/valid" / case["file"]

    validate_document(case["kind"], fixture)


@pytest.mark.parametrize("case", _manifest("invalid"), ids=lambda case: case["file"])
def test_checked_in_invalid_fixtures_fail_for_intended_reason(
    case: dict[str, str],
) -> None:
    fixture = ROOT / "packages/contracts/fixtures/invalid" / case["file"]

    with pytest.raises(ContractValidationError, match=case["error_contains"]):
        validate_document(case["kind"], fixture)
