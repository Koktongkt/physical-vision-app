import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/check_sensitive_files.py"
SPEC = importlib.util.spec_from_file_location("check_sensitive_files", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "candidate",
    [
        "AKIA" + "A" * 16,
        "AIza" + "A" * 35,
        "xoxb-" + "A" * 12 + "-" + "B" * 24,
        "sk-" + "A" * 32,
        "eyJ" + "A" * 24 + "." + "B" * 24 + "." + "C" * 24,
    ],
)
def test_common_credential_shapes_are_detected(candidate: str) -> None:
    assert MODULE.SECRET_PATTERN.search(candidate.encode())


def test_environment_override_filename_is_forbidden() -> None:
    assert ".env.production" in MODULE.FORBIDDEN_NAMES
