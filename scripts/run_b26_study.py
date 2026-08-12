from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "packages/study/python"))
sys.path.insert(0, str(ROOT / "packages/vision/python"))

from physical_vision_study import (  # noqa: E402
    aggregate_live_report,
    canonical_json_bytes,
    lock_manifest,
    public_supplement_omitted_report,
    validate_manifest,
    validate_report,
    verify_manifest_lock,
)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, document: object) -> None:
    path.write_bytes(canonical_json_bytes(document))


def _write_pretty_json(path: Path, document: object) -> None:
    serialized = json.dumps(document, indent=2, ensure_ascii=True, sort_keys=True)
    path.write_bytes(f"{serialized}\n".encode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic B26 study harness operations")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--kind", choices=("manifest", "lock", "report"), required=True)
    validate.add_argument("--input", type=Path, required=True)

    lock = commands.add_parser("lock-manifest")
    lock.add_argument("--input", type=Path, required=True)
    lock.add_argument("--locked-at", required=True)
    lock.add_argument("--signer-id", required=True)
    lock.add_argument("--output", type=Path, required=True)

    aggregate = commands.add_parser("aggregate-live")
    aggregate.add_argument("--locked-manifest", type=Path, required=True)
    aggregate.add_argument("--observations", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)

    public = commands.add_parser("public-supplement")
    public.add_argument("--decision", choices=("omitted",), required=True)
    public.add_argument("--output", type=Path, required=True)

    arguments = parser.parse_args()
    if arguments.command == "validate":
        document = _read_json(arguments.input)
        validators = {
            "manifest": validate_manifest,
            "lock": verify_manifest_lock,
            "report": validate_report,
        }
        validators[arguments.kind](document)
        print(f"valid {arguments.kind}")
    elif arguments.command == "lock-manifest":
        locked = lock_manifest(
            _read_json(arguments.input),
            locked_at=arguments.locked_at,
            signer_id=arguments.signer_id,
        )
        _write_json(arguments.output, locked)
        print(f"locked manifest: {locked['lock']['fingerprint']}")
    elif arguments.command == "aggregate-live":
        observations = _read_json(arguments.observations)
        if type(observations) is not list:
            raise ValueError("observations input must be a JSON array")
        report = aggregate_live_report(_read_json(arguments.locked_manifest), observations)
        _write_json(arguments.output, report)
        print(f"live report: {report['status']}")
    else:
        report = public_supplement_omitted_report()
        _write_pretty_json(arguments.output, report)
        print(f"public supplement report: {report['status']}")


if __name__ == "__main__":
    main()
