#!/usr/bin/env python3
"""Install all five skills and shared resources together without overwriting."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def install(target=None, dry_run=False):
    manifest = json.loads((ROOT / "suite.json").read_text(encoding="utf-8"))
    names = manifest["skills"] + [manifest["shared"]]
    destination = Path(target).expanduser().resolve() if target else (Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills").resolve()
    if destination.exists() and not destination.is_dir():
        raise ValueError("Installation target must be a directory")
    if len(names) != len(set(names)) or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names):
        raise ValueError("Invalid suite folder names")
    for name in names:
        if not (ROOT / "skills" / name).is_dir():
            raise ValueError(f"Missing source: {name}")
        if os.path.lexists(destination / name):
            raise ValueError(f"Refusing to overwrite existing installation: {destination / name}")
    plan = {"target": str(destination), "folders": names, "dry_run": dry_run,
            "overwrites": False, "state_modified": False}
    if dry_run:
        return plan
    destination.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".help-me-study-install-", dir=destination))
    try:
        for name in names:
            shutil.copytree(ROOT / "skills" / name, stage / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        for name in names:
            # Re-check after staging; never merge with or overwrite an existing folder.
            if os.path.lexists(destination / name):
                raise ValueError(f"Target appeared during installation: {destination / name}")
            (stage / name).rename(destination / name)
        stage.rmdir()
    except Exception as exc:
        raise ValueError(f"Installation stopped: {exc}. Inspect staged files at {stage}; no old folders were overwritten") from exc
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", help="Skills parent directory; default CODEX_HOME/skills or ~/.codex/skills")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(install(args.target, args.dry_run), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
