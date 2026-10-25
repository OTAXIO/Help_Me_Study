#!/usr/bin/env python3
"""Check metadata and resource references; this is not a model behavior evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate(skills_root=None):
    import yaml

    directory = Path(skills_root).resolve() if skills_root else ROOT / "skills"
    manifest = json.loads((ROOT / "suite.json").read_text(encoding="utf-8"))
    issues = []
    links = 0
    for name in manifest["skills"]:
        path = directory / name / "SKILL.md"
        if not path.exists():
            issues.append(f"Missing {path}")
            continue
        content = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", content, re.S)
        try:
            metadata = yaml.safe_load(match.group(1)) if match else None
            if not isinstance(metadata, dict) or metadata.get("name") != name or not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
                raise ValueError("Invalid name/description")
            if set(metadata) - {"name", "description", "metadata", "license", "allowed-tools"}:
                raise ValueError("Unsupported frontmatter fields")
            ui = yaml.safe_load((directory / name / "agents" / "openai.yaml").read_text(encoding="utf-8"))
            interface = ui["interface"]
            if not 25 <= len(interface["short_description"]) <= 64:
                raise ValueError("UI short_description must be 25-64 characters")
            if "$" + name not in interface["default_prompt"]:
                raise ValueError("Default prompt must name the skill")
            if ui.get("policy", {}).get("allow_implicit_invocation", True) is not True:
                raise ValueError("Automatic discovery must remain enabled")
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
            issues.append(f"{name}: {exc}")
    shared = directory / manifest["shared"]
    if not shared.is_dir() or (shared / "SKILL.md").exists():
        issues.append("Shared resources must exist without a callable SKILL.md")
    folders = manifest["skills"] + [manifest["shared"]]
    for name in folders:
        folder = directory / name
        if not folder.exists():
            continue
        for path in folder.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", content):
                target = target.strip().split("#", 1)[0]
                if not target or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                    continue
                resolved = (path.parent / target).resolve()
                links += 1
                if not resolved.is_relative_to(directory) or not resolved.exists():
                    issues.append(f"Broken/outside skill reference: {path.relative_to(directory)} -> {target}")
    return {"skills": len(manifest["skills"]), "local_references_checked": links,
            "issues": issues, "passed": not issues,
            "scope": "metadata and local resource paths only; no live service or model behavior proof"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", help="Validate an installed sibling suite")
    args = parser.parse_args(argv)
    try:
        result = validate(args.skills_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
