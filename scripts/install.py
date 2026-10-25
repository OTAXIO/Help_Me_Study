#!/usr/bin/env python3
"""Install the sibling suite, or update known unmodified files with backups."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("help_me_install_state", ROOT / "skills" / "help-me-shared" / "scripts" / "study_state.py")
STATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(destination, relative):
    path = destination / relative
    if not path.resolve().is_relative_to(destination):
        raise ValueError(f"Target escapes installation: {relative}")
    for part in (path, *path.parents):
        if part == destination:
            break
        if part.is_symlink() or (getattr(part, "is_junction", lambda: False)()):
            raise ValueError(f"Refusing linked installation path: {relative}")
    return path


def source_files(names):
    result = {}
    for name in names:
        folder = ROOT / "skills" / name
        if not folder.is_dir():
            raise ValueError(f"Missing source: {name}")
        for path in sorted(folder.rglob("*")):
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            if path.is_symlink():
                raise ValueError(f"Linked source is not supported: {path}")
            if path.is_file():
                result[path.relative_to(ROOT / "skills").as_posix()] = path
    return result


def baseline(receipt, destination):
    if receipt.exists():
        value = STATE.read_json(receipt)
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("target") != str(destination) or not isinstance(value.get("files"), dict)):
            raise ValueError("Invalid installation receipt; preserve it and inspect before updating")
        return value["files"]
    # v1.0.0 did not create receipts. Only exact known legacy hashes may be replaced.
    legacy = STATE.read_json(ROOT / "manifests" / "1.0.0.json")
    return legacy["files"]


def changes(destination, sources, known):
    added, replaced, unchanged, conflicts = [], [], [], []
    for relative, source in sources.items():
        path = safe_path(destination, relative)
        if not os.path.lexists(path):
            added.append(relative)
        elif not path.is_file():
            conflicts.append(relative)
        else:
            current = sha(path)
            if current == sha(source):
                unchanged.append(relative)
            elif current == known.get(relative):
                replaced.append(relative)
            else:
                conflicts.append(relative)
    if conflicts:
        raise ValueError("Local modifications or unknown files conflict; nothing was changed: " + ", ".join(conflicts))
    return added, replaced, unchanged


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".help-me-copy-", dir=destination.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(target=None, dry_run=False, update=False, state_dir=None):
    manifest = json.loads((ROOT / "suite.json").read_text(encoding="utf-8"))
    names = manifest["skills"] + [manifest["shared"]]
    destination = Path(target).expanduser().resolve() if target else (Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills").resolve()
    if destination.exists() and not destination.is_dir():
        raise ValueError("Installation target must be a directory")
    if len(names) != len(set(names)) or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names):
        raise ValueError("Invalid suite folder names")
    for name in names:
        if not update and os.path.lexists(destination / name):
            raise ValueError(f"Refusing to overwrite existing installation: {destination / name}")
        if os.path.lexists(destination / name) and not (destination / name).is_dir():
            raise ValueError(f"Installation folder is occupied by a file: {name}")
        safe_path(destination, name)
    sources = source_files(names)
    target_key = hashlib.sha256(os.path.normcase(str(destination)).encode("utf-8")).hexdigest()[:20]
    private = STATE.state_directory(state_dir) / "installations" / target_key
    if private.is_relative_to(ROOT.resolve()) or private.is_relative_to(destination):
        raise ValueError("Installation state must stay outside the source repository and skills target")
    receipt = private / "receipt.json"
    known = baseline(receipt, destination) if update else {}
    added, replaced, unchanged = changes(destination, sources, known)
    plan = {"target": str(destination), "version": manifest["version"], "folders": names,
            "dry_run": dry_run, "update": update, "added": added, "replaced": replaced,
            "unchanged": len(unchanged), "notion_state_modified": False,
            "installation_state_modified": False, "backup": None}
    if dry_run:
        return plan
    private.mkdir(parents=True, exist_ok=True)
    with STATE.locked(receipt):
        # Repeat all preflight checks under the suite lock before changing installed files.
        if not update and any(os.path.lexists(destination / name) for name in names):
            raise ValueError("Installation appeared during preflight; refusing to overwrite")
        known = baseline(receipt, destination) if update else {}
        added, replaced, unchanged = changes(destination, sources, known)
        plan.update(added=added, replaced=replaced, unchanged=len(unchanged))
        previous_hashes = {relative: sha(safe_path(destination, relative)) for relative in replaced}
        if replaced:
            backup = private / "backups" / (STATE.now().replace(":", "-") + "-" + uuid.uuid4().hex[:8])
            backup.mkdir(parents=True)
            for relative in replaced:
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(safe_path(destination, relative), saved)
                if sha(saved) != previous_hashes[relative]:
                    raise ValueError("File changed while backing up; installation stopped")
            STATE.atomic_json(backup / "backup-manifest.json", {"target": str(destination), "files": previous_hashes})
            plan["backup"] = str(backup)
        try:
            for relative in added + replaced:
                path = safe_path(destination, relative)
                if relative in added and os.path.lexists(path):
                    raise ValueError(f"New target appeared: {relative}")
                if relative in replaced and (not path.is_file() or sha(path) != previous_hashes[relative]):
                    raise ValueError(f"Target changed during update: {relative}")
                atomic_copy(sources[relative], path)
            expected = {relative: sha(source) for relative, source in sources.items()}
            if any(sha(safe_path(destination, relative)) != digest for relative, digest in expected.items()):
                raise ValueError("Installed content verification failed")
            value = {"schema_version": 1, "suite_version": manifest["version"],
                     "target": str(destination), "files": expected}
            if not receipt.exists() or STATE.read_json(receipt) != value:
                STATE.atomic_json(receipt, value)
                plan["installation_state_modified"] = True
        except Exception as exc:
            raise ValueError(f"Installation stopped; inspect files and backup {plan['backup']} before retrying: {exc}") from exc
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", help="Skills parent directory; default CODEX_HOME/skills or ~/.codex/skills")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update", action="store_true", help="Replace only files matching a known baseline; preserve local edits")
    parser.add_argument("--state-dir", help="Private installation receipts/backups parent; default HelpMeStudy user state")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(install(args.target, args.dry_run, args.update, args.state_dir), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
