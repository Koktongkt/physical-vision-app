from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".tif",
    ".tiff",
    ".onnx",
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".p12",
    ".pfx",
    ".pem",
    ".key",
}
FORBIDDEN_NAMES = {".env", ".env.local", ".env.production"}
SECRET_PATTERN = re.compile(
    rb"(?:BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
    rb"|gh[pousr]_[A-Za-z0-9]{20,}"
    rb"|AKIA[0-9A-Z]{16}"
    rb"|AIza[0-9A-Za-z_-]{35}"
    rb"|xox[baprs]-[0-9A-Za-z-]{20,}"
    rb"|sk-[0-9A-Za-z_-]{32,}"
    rb"|eyJ[0-9A-Za-z_-]{20,}\.[0-9A-Za-z_-]{20,}\.[0-9A-Za-z_-]{20,})"
)


def tracked_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    )
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def main() -> None:
    violations: list[str] = []
    files = tracked_files()
    for filename in files:
        path = PurePosixPath(filename)
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"forbidden tracked file: {filename}")
            continue
        try:
            content = Path(filename).read_bytes()
        except OSError as exc:
            violations.append(f"cannot inspect {filename}: {exc}")
            continue
        if SECRET_PATTERN.search(content):
            violations.append(f"credential-like content in tracked file: {filename}")
    if violations:
        raise SystemExit("\n".join(violations))
    print(f"sensitive-file check passed for {len(files)} tracked files")


if __name__ == "__main__":
    main()
