#!/usr/bin/env python3
"""Check new geolocator changes for secrets, caches, weights, and large binaries."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".tif", ".tiff", ".pt", ".pth", ".ckpt", ".onnx", ".npy", ".npz", ".env"}
FORBIDDEN_PARTS = {".geolocator-cache", "models", "__pycache__", "node_modules"}
MAX_NEW_FILE_BYTES = 5_000_000
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?im)^\s*(?:USGS_M2M_TOKEN|USGS_M2M_APP_TOKEN|IMAGERY_PROVIDER_TOKEN)\s*=\s*[^\s#]+"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
]


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files() -> list[Path]:
    candidates: set[str] = set(git_lines("ls-files", "--others", "--exclude-standard"))
    bases = ["origin/main", "main"]
    for base in bases:
        if subprocess.run(["git", "rev-parse", "--verify", base], cwd=ROOT, capture_output=True).returncode == 0:
            merge_base = git_lines("merge-base", base, "HEAD")
            if merge_base:
                candidates.update(git_lines("diff", "--name-only", "--diff-filter=ACMR", f"{merge_base[0]}...HEAD"))
                candidates.update(git_lines("diff", "--name-only", "--diff-filter=ACMR"))
                break
    return sorted((ROOT / name).resolve() for name in candidates if (ROOT / name).is_file())


def merge_base_files() -> set[str]:
    """Return paths already tracked at the branch merge base.

    Large and binary generated atlas artifacts predate the geolocator branch and
    are intentionally regenerated in place.  The evidence gate must still reject
    a newly introduced binary or oversized file, while not misclassifying a
    modification to one of those existing tracked outputs as new evidence.
    """
    for base in ("origin/main", "main"):
        if subprocess.run(
            ["git", "rev-parse", "--verify", base],
            cwd=ROOT,
            capture_output=True,
        ).returncode != 0:
            continue
        merge_base = git_lines("merge-base", base, "HEAD")
        if merge_base:
            return set(git_lines("ls-tree", "-r", "--name-only", merge_base[0]))
    return set()


def main() -> int:
    failures: list[str] = []
    files = changed_files()
    baseline_files = merge_base_files()
    for path in files:
        relative = path.relative_to(ROOT)
        is_new = relative.as_posix() not in baseline_files
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or any(part in FORBIDDEN_PARTS for part in relative.parts):
            failures.append(f"forbidden artifact: {relative}")
        if is_new and path.stat().st_size > MAX_NEW_FILE_BYTES:
            failures.append(f"new file exceeds {MAX_NEW_FILE_BYTES} bytes: {relative}")
        if is_new and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".zip", ".kmz", ".pdf", ".xlsx"}:
            failures.append(f"new binary evidence must remain external: {relative}")
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".zip", ".kmz", ".pdf", ".xlsx"}:
            continue
        if path.name == ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"possible credential/private key in {relative}: {pattern.pattern}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"PASS checked_new_files={len(files)} no_credentials_large_images_weights_or_caches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
