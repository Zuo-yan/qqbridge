#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


RUNTIME_NAMES = {
    "config.toml",
    "owner.txt",
    "manager.sqlite3",
    "appearance.sqlite3",
}


def copy_tree(source: Path, destination: Path, preserve_runtime: bool, preserve_existing: bool = False) -> None:
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            if item.name in {"__pycache__", ".git", ".update_backups", ".update_tmp"}:
                continue
            target.mkdir(parents=True, exist_ok=True)
            copy_tree(item, target, preserve_runtime)
            continue
        if preserve_runtime and target.exists() and (
            item.name in RUNTIME_NAMES
            or item.suffix in {".db", ".sqlite3", ".pyc"}
        ):
            continue
        if preserve_existing and target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--instance", required=True)
    args = parser.parse_args()
    package = Path(args.package)
    instance = Path(args.instance)
    copy_tree(package / "payload" / "plugins", instance / "plugins", preserve_runtime=True)
    for name in ("emoji", "emoji_personas", "prompt_imgs", "emoji_thumbnails"):
        source = package / "payload" / "data" / name
        if source.exists():
            copy_tree(source, instance / "data" / name, preserve_runtime=False, preserve_existing=True)
    legacy = package / "payload" / "personas" / "legacy-dafeiyu.md"
    target = instance / "personas" / "legacy-dafeiyu.md"
    if legacy.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)


if __name__ == "__main__":
    main()
