#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


EXCLUDED_ROOTS = {".git", ".github", "_staging", "backups"}
EXCLUDED_NAMES = {"manifest.json"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_runtime_artifact(path: Path) -> bool:
    return (
        "__pycache__" in path.parts
        or path.suffix in {".pyc", ".log", ".db", ".sqlite3", ".zip", ".sha256"}
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        fail(f"manifest.json is missing under {root}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if manifest.get("package") not in {"qqbridge", "qqbridge-windows"}:
        fail("manifest package name is not recognized")
    if manifest.get("package_version") != version:
        fail("manifest and VERSION disagree")
    files = manifest.get("files")
    if not isinstance(files, dict):
        fail("manifest files map is missing")

    actual = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if (
            relative.parts[0] in EXCLUDED_ROOTS
            or relative.as_posix() in EXCLUDED_NAMES
            or is_runtime_artifact(path)
        ):
            continue
        actual.add(relative.as_posix())

    expected = set(files)
    missing = sorted(actual - expected)
    absent = sorted(expected - actual)
    if missing:
        fail("unmanifested files: " + ", ".join(missing[:10]))
    if absent:
        fail("manifested files are missing: " + ", ".join(absent[:10]))

    for relative, metadata in files.items():
        path = root / relative
        if not path.is_file():
            fail(f"file is missing: {relative}")
        data = path.read_bytes()
        if len(data) != metadata.get("size"):
            fail(f"size mismatch: {relative}")
        if hashlib.sha256(data).hexdigest() != metadata.get("sha256"):
            fail(f"hash mismatch: {relative}")

    plugins = manifest.get("plugins")
    patches = manifest.get("patches")
    if not isinstance(plugins, list) or len(plugins) != 17:
        fail("manifest must list exactly 17 plugins")
    if not isinstance(patches, list) or len(patches) != 14:
        fail("manifest must list exactly 14 patches")
    plugin_dirs = [
        path
        for path in (root / "payload" / "plugins").iterdir()
        if path.is_dir()
    ]
    if {path.name for path in plugin_dirs} != {item["name"] for item in plugins}:
        fail("plugin directories and manifest disagree")

    patch_dir = root / "image" / "patches"
    patch_names = {path.name for path in patch_dir.iterdir() if path.is_file()}
    if patch_names != {item["name"] for item in patches}:
        fail("patch files and manifest disagree")
    for item in patches:
        path = patch_dir / item["name"]
        if sha256_file(path) != item["sha256"]:
            fail(f"patch hash mismatch: {item['name']}")

    print(
        f"PASS package integrity: {len(files)} files, "
        f"{len(plugins)} plugins, {len(patches)} patches"
    )


if __name__ == "__main__":
    main()
