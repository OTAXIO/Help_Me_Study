#!/usr/bin/env python3
"""Local-only workspace, outline receipt and Notion map tools (Python 3.10+)."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlparse, unquote
import uuid


MANIFEST = ".help-me-study-task.json"
SCHEMA = 1


class StateError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateError(f"Cannot read valid JSON: {path}") from exc


@contextmanager
def locked(path):
    lock = Path(str(path) + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise StateError(f"State is locked: {lock}; inspect the owning process before recovery") from exc
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def atomic_json(path, data):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".help-me-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def workspace_manifest(workspace):
    root = Path(workspace).resolve(strict=True)
    path = root / MANIFEST
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA or not value.get("task_id"):
        raise StateError("Unsupported or invalid workspace manifest")
    return root, path, value


def init_workspace(task_dir, resume=None):
    task = Path(task_dir).resolve(strict=True)
    if not task.is_dir():
        raise StateError("task-dir must be an existing directory")
    if resume is not None:
        root, _, value = workspace_manifest(resume)
        if root.parent != task or Path(value.get("task_dir", "")).resolve() != task:
            raise StateError("Resume workspace must belong directly to this task directory")
        for name in ("code", "report", "submit"):
            child = root / name
            if not child.is_dir() or child.is_symlink():
                raise StateError(f"Resume directory is missing or unsafe: {name}")
        return {"workspace": str(root), "resumed": True, "task_id": value["task_id"],
                "packaging_performed": False, "note": "No files were packaged or submitted by this invocation"}
    suffix = 0
    while True:
        name = "work" if suffix == 0 else "work_codex" if suffix == 1 else f"work_codex_{suffix}"
        root = task / name
        try:
            root.mkdir()
            break
        except FileExistsError:
            suffix += 1
    for name in ("code", "report", "submit"):
        (root / name).mkdir()
    value = {"schema_version": SCHEMA, "task_id": uuid.uuid4().hex,
             "task_dir": str(task), "created_at": now(), "outline": None}
    atomic_json(root / MANIFEST, value)
    return {"workspace": str(root), "resumed": False, "task_id": value["task_id"],
            "packaging_performed": False, "note": "No files were packaged or submitted by this invocation"}


def outline_file(root, relative):
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise StateError("Outline must be a regular file within the workspace")
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_outline(workspace, file):
    root, path, _ = workspace_manifest(workspace)
    source = outline_file(root, file)
    with locked(path):
        value = read_json(path)
        value["outline"] = {"file": source.relative_to(root).as_posix(), "sha256": digest(source),
                            "registered_at": now(), "approved_sha256": None,
                            "user_confirmed_at": None}
        atomic_json(path, value)
    return outline_status(workspace)


def outline_status(workspace):
    root, _, value = workspace_manifest(workspace)
    receipt = value.get("outline")
    if receipt is None:
        return {"status": "missing", "approved": False}
    if not isinstance(receipt, dict) or not isinstance(receipt.get("file"), str):
        raise StateError("Invalid outline receipt")
    try:
        current = digest(outline_file(root, receipt["file"]))
    except (OSError, StateError):
        return {"status": "missing-file", "approved": False, "file": receipt["file"]}
    matches = current == receipt.get("sha256")
    approved = matches and receipt.get("approved_sha256") == current and bool(receipt.get("user_confirmed_at"))
    return {"status": "approved" if approved else "pending" if matches else "changed",
            "approved": approved, "file": receipt["file"], "sha256": current,
            "user_confirmed_at": receipt.get("user_confirmed_at"),
            "note": "A local receipt records a claimed human confirmation; it cannot create consent"}


def approve_outline(workspace, sha256, user_confirmed=False):
    if not user_confirmed:
        raise StateError("Record approval only after explicit human confirmation; supply --user-confirmed")
    root, path, _ = workspace_manifest(workspace)
    with locked(path):
        value = read_json(path)
        receipt = value.get("outline")
        if not isinstance(receipt, dict):
            raise StateError("Register an outline first")
        current = digest(outline_file(root, receipt["file"]))
        if sha256 != current or receipt.get("sha256") != current:
            raise StateError("Outline changed or confirmation hash does not match; present the current outline")
        receipt.update(approved_sha256=current, user_confirmed_at=now())
        atomic_json(path, value)
    return outline_status(workspace)


def page_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise StateError("Notion page_id must be 32 hex digits or a UUID")
    return value.replace("-", "").lower()


def text_field(value, key):
    content = value.get(key)
    if not isinstance(content, str) or not content.strip():
        raise StateError(f"Non-empty text required: {key}")
    return content.strip()


def validate_node(node, child=False):
    if not isinstance(node, dict):
        raise StateError("Page must be an object")
    expected = {"title", "page_id", "url"} | ({"parent_id"} if child else set())
    if set(node) != expected:
        raise StateError(f"Page fields must be exactly: {', '.join(sorted(expected))}")
    result = {"title": text_field(node, "title"), "page_id": page_id(node["page_id"]),
              "url": text_field(node, "url")}
    parsed = urlparse(result["url"])
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise StateError("Page URL must be a credential-free HTTPS Notion URL")
    if hostname not in ("notion.so", "www.notion.so", "notion.site") and not hostname.endswith(".notion.site"):
        raise StateError("Page URL must use notion.so or notion.site")
    found = re.search(r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$", unquote(parsed.path).rstrip("/"))
    if found is None or page_id(found.group(1)) != result["page_id"]:
        raise StateError("Page URL path must end in the same page_id; resolve short/custom links first")
    if child:
        result["parent_id"] = page_id(node["parent_id"])
    return result


def validate_entry(entry):
    if not isinstance(entry, dict):
        raise StateError("Mapping must be an object")
    allowed = {"course", "term", "canvas_course_id", "parent", "pages", "materials_path", "verified_at"}
    if set(entry) - allowed:
        raise StateError("Unexpected mapping fields; credentials and private extras are not accepted")
    result = {"course": text_field(entry, "course"), "term": text_field(entry, "term"),
              "parent": validate_node(entry.get("parent"))}
    canvas = entry.get("canvas_course_id")
    if canvas is not None and (isinstance(canvas, bool) or not re.fullmatch(r"[1-9][0-9]*", str(canvas))):
        raise StateError("canvas_course_id must be positive digits or null")
    result["canvas_course_id"] = str(canvas) if canvas is not None else None
    if not isinstance(entry.get("pages", []), list):
        raise StateError("pages must be a list")
    result["pages"] = [validate_node(node, child=True) for node in entry.get("pages", [])]
    root = result["parent"]["page_id"]
    parents = {}
    for node in result["pages"]:
        node_id = node["page_id"]
        if node_id == root or node_id in parents:
            raise StateError("Duplicate page_id")
        parents[node_id] = node["parent_id"]
    for start in parents:
        visited = set()
        current = start
        while current != root:
            if current in visited or current not in parents:
                raise StateError("Page hierarchy must be acyclic and connected to the course parent")
            visited.add(current)
            current = parents[current]
    materials = entry.get("materials_path")
    if materials is not None and not isinstance(materials, str):
        raise StateError("materials_path must be text or null")
    result["materials_path"] = materials
    timestamp = entry.get("verified_at")
    if timestamp is not None:
        if not isinstance(timestamp, str):
            raise StateError("verified_at must be an ISO timestamp")
        try:
            parsed_time = datetime.fromisoformat(timestamp)
            if parsed_time.tzinfo is None:
                raise ValueError()
        except ValueError as exc:
            raise StateError("verified_at must include an ISO timezone") from exc
    result["verified_at"] = timestamp
    return result


def state_directory(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    configured = os.environ.get("HELP_ME_STUDY_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return (base / "HelpMeStudy").resolve()


def load_registry(directory):
    path = state_directory(directory) / "notion-map.json"
    if not path.exists():
        return {"schema_version": SCHEMA, "courses": []}
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {"schema_version", "courses"} or value["schema_version"] != SCHEMA or not isinstance(value["courses"], list):
        raise StateError("Unsupported or invalid registry; preserve the file and inspect it")
    courses = [validate_entry(entry) for entry in value["courses"]]
    keys = [(entry["course"], entry["term"]) for entry in courses]
    if len(keys) != len(set(keys)):
        raise StateError("Duplicate course/term keys in registry")
    return {"schema_version": SCHEMA, "courses": courses}


def put_mapping(directory, entry, verified=False, replace_parent=False):
    if not verified:
        raise StateError("Read the live pages first; --verified records that check, it does not perform it")
    item = validate_entry(entry)
    item["verified_at"] = now()
    target = state_directory(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "notion-map.json"
    with locked(path):
        registry = load_registry(target)
        key = (item["course"], item["term"])
        old = next((value for value in registry["courses"] if (value["course"], value["term"]) == key), None)
        if old and old["parent"]["page_id"] != item["parent"]["page_id"] and not replace_parent:
            raise StateError("Parent changed; verify user intent before using --replace-parent")
        registry["courses"] = [value for value in registry["courses"] if (value["course"], value["term"]) != key] + [item]
        atomic_json(path, registry)
    return {"course": item["course"], "term": item["term"], "verified_at": item["verified_at"],
            "note": "Stored locally; no Notion request or host memory update was made"}


def get_mapping(directory, course, term=None):
    candidates = [entry for entry in load_registry(directory)["courses"] if entry["course"] == course and (term is None or entry["term"] == term)]
    if not candidates:
        raise StateError("No matching course mapping; resolve the actual page first")
    if len(candidates) > 1:
        raise StateError("Ambiguous course; specify term: " + ", ".join(entry["term"] for entry in candidates))
    return {"mapping": candidates[0], "must_read_live_pages": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    workspace = commands.add_parser("workspace").add_subparsers(dest="action", required=True)
    init = workspace.add_parser("init")
    init.add_argument("--task-dir", required=True)
    init.add_argument("--resume")
    outline = commands.add_parser("outline").add_subparsers(dest="action", required=True)
    for name in ("set", "status", "approve"):
        child = outline.add_parser(name)
        child.add_argument("--workspace", required=True)
        if name == "set":
            child.add_argument("--file", required=True)
        if name == "approve":
            child.add_argument("--sha256", required=True)
            child.add_argument("--user-confirmed", action="store_true")
    notion = commands.add_parser("notion").add_subparsers(dest="action", required=True)
    for name in ("list", "get", "put"):
        child = notion.add_parser(name)
        child.add_argument("--state-dir")
        if name == "get":
            child.add_argument("--course", required=True)
            child.add_argument("--term")
        if name == "put":
            child.add_argument("--file", required=True)
            child.add_argument("--verified", action="store_true")
            child.add_argument("--replace-parent", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "workspace":
            result = init_workspace(args.task_dir, args.resume)
        elif args.command == "outline":
            if args.action == "set":
                result = set_outline(args.workspace, args.file)
            elif args.action == "approve":
                result = approve_outline(args.workspace, args.sha256, args.user_confirmed)
            else:
                result = outline_status(args.workspace)
        elif args.action == "put":
            result = put_mapping(args.state_dir, read_json(args.file), args.verified, args.replace_parent)
        elif args.action == "get":
            result = get_mapping(args.state_dir, args.course, args.term)
        else:
            result = load_registry(args.state_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (StateError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
