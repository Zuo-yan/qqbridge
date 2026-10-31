#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--get")
    group.add_argument("--json", nargs="+")
    args = parser.parse_args()
    values = load_env(Path(args.instance) / ".env")
    if args.get:
        print(values.get(args.get, ""))
    else:
        print(json.dumps({key: values.get(key, "") for key in args.json}, ensure_ascii=False))


if __name__ == "__main__":
    main()
