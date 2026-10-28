#!/usr/bin/env python3
"""Read-only note structure audit; optional HTML preview, never auto-repair or sync."""

from __future__ import annotations

import argparse
from collections import Counter
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


class AuditError(ValueError):
    pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"Cannot read valid JSON: {path}") from exc


def parser(profile):
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise AuditError("Install the optional requirements-format.txt dependency; no regex-only fallback is used") from exc
    md = MarkdownIt("commonmark", {"html": False, "typographer": False})
    if profile == "notes":
        md.enable(["table", "strikethrough"])
    elif profile != "commonmark":
        raise AuditError("Unknown Markdown profile")
    return md


def text_of(tokens):
    return "".join("\n" if token.type in ("softbreak", "hardbreak") else token.content
                   for token in tokens if not token.type.endswith(("_open", "_close")))


def paired_text(tokens, start, opening, closing):
    depth = 1
    for end in range(start + 1, len(tokens)):
        if tokens[end].type == opening:
            depth += 1
        elif tokens[end].type == closing:
            depth -= 1
            if depth == 0:
                return text_of(tokens[start + 1:end])
    return ""


def warn_text(text, warnings, line=None):
    # Only suppress warnings in obvious balanced math candidates. This is NOT a math parser.
    checked = re.sub(r"\$\$[\s\S]*?\$\$|(?<!\\)\$[^$\n]+(?<!\\)\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]", "", text)
    for marker in ("**", "~~", "]("):
        if marker in checked:
            warnings.append({"code": "literal_marker_review", "line": line, "marker": marker,
                             "message": "Literal formatting marker in text; inspect intent, escaping and target support"})
    if "\ufffd" in checked:
        warnings.append({"code": "replacement_character", "line": line})
    if re.search(r"</?[A-Za-z][^>]*>", checked):
        warnings.append({"code": "literal_html_review", "line": line})


def inspect_markdown(source, profile="notes", base_dir=None):
    tokens = parser(profile).parse(source)
    elements, tables, errors, warnings = [], [], [], []
    lines = source.splitlines()
    heading = None
    previous_heading = None
    table = None
    row = None
    for token in tokens:
        line = token.map[0] + 1 if token.map else None
        if token.type == "heading_open":
            heading = int(token.tag[1:])
            if previous_heading is not None and heading > previous_heading + 1:
                warnings.append({"code": "heading_level_jump", "line": line})
            previous_heading = heading
        elif token.type == "heading_close":
            heading = None
        elif token.type in ("fence", "code_block"):
            elements.append({"kind": "code_block", "text": token.content, "language": token.info.strip()})
            if token.type == "fence":
                end = token.map[1]
                last = lines[end - 1] if end and end <= len(lines) else ""
                closing = r" {0,3}" + re.escape(token.markup[0]) + "{" + str(len(token.markup)) + r",}\s*"
                if end <= token.map[0] + 1 or not re.fullmatch(closing, last):
                    errors.append({"code": "unclosed_fence", "line": line,
                                   "message": "Notes convention requires an explicit closing fence"})
        elif token.type == "bullet_list_open":
            elements.append({"kind": "bullet_list"})
        elif token.type == "ordered_list_open":
            start = token.attrGet("start")
            elements.append({"kind": "ordered_list", "start": int(start) if start is not None else 1})
        elif token.type == "list_item_open":
            elements.append({"kind": "list_item"})
        elif token.type == "blockquote_open":
            elements.append({"kind": "quote"})
        elif token.type == "hr":
            elements.append({"kind": "separator"})
        elif token.type == "table_open":
            table = []
            elements.append({"kind": "table"})
        elif token.type == "tr_open" and table is not None:
            row = []
        elif token.type == "tr_close" and table is not None:
            table.append(row)
            row = None
        elif token.type == "table_close":
            tables.append(table)
            table = None
        elif token.type == "inline":
            children = token.children or []
            # Inspect token boundaries to protect literal code examples.
            for index, child in enumerate(children):
                if (child.type == "code_inline" and index > 0 and index + 1 < len(children)
                        and children[index - 1].type == "text"
                        and children[index - 1].content.endswith("$")
                        and not children[index - 1].content.endswith("\\$")
                        and children[index + 1].type == "text"
                        and children[index + 1].content.startswith("$")):
                    warnings.append({"code": "legacy_math_backtick_wrapper", "line": line,
                                     "message": "Check current target contract: use $formula$ for Notion math, without backticks"})
            if re.match(r"^\[[ xX]\]\s|^\[![A-Z]+\]", token.content):
                warnings.append({"code": "target_extension_review", "line": line,
                                 "message": "Task items/callouts need the target's native or supported extension mapping"})
            content = text_of(children)
            if row is not None:
                row.append(content)
            elif heading is not None:
                elements.append({"kind": "heading", "level": heading, "text": content})
            else:
                elements.append({"kind": "paragraph", "text": content})
            for index, child in enumerate(children):
                if child.type in ("strong_open", "em_open", "s_open", "link_open"):
                    kind = {"strong_open": "strong", "em_open": "emphasis", "s_open": "strike", "link_open": "link"}[child.type]
                    item = {"kind": kind, "text": paired_text(children, index, child.type, child.type.replace("_open", "_close"))}
                    if kind == "link":
                        item["href"] = child.attrGet("href")
                    elements.append(item)
                elif child.type == "code_inline":
                    elements.append({"kind": "code_inline", "text": child.content})
                elif child.type == "image":
                    src = child.attrGet("src") or ""
                    elements.append({"kind": "image", "text": child.content, "src": src})
                    parsed = urlsplit(src)
                    if base_dir is not None and not parsed.scheme and not parsed.netloc and parsed.path:
                        if not (Path(base_dir) / unquote(parsed.path)).is_file():
                            errors.append({"code": "missing_local_image", "line": line, "src": src})
            # Inspect text only: fenced/inline code is not treated as markup leakage.
            prose = "".join(child.content if child.type == "text" else "\n" for child in children)
            warn_text(prose, warnings, line)
    return {"elements": elements, "tables": tables, "errors": errors, "warnings": warnings,
            "profile": profile, "manual_checks": ["math validity/typesetting", "target-specific extensions",
            "remote resources, anchors and page access", "final Notion/Word/PDF visual rendering"]}


def rich_text(spans):
    if not isinstance(spans, list):
        raise AuditError("Native rich_text must be an array")
    return "".join(span.get("plain_text", span.get("text", {}).get("content", "")) for span in spans)


def inspect_notion(snapshot):
    elements, tables, errors, warnings = [], [], [], []
    manual = ["snapshot is not a network request or current access proof", "final Notion visual rendering"]

    def blocks(container):
        if isinstance(container, list):
            return container
        if isinstance(container, dict) and isinstance(container.get("results"), list):
            if container.get("has_more"):
                errors.append({"code": "incomplete_snapshot", "message": "Read remaining pagination before claiming coverage"})
            return container["results"]
        raise AuditError("Expected native Notion block array or paginated results, not Markdown export JSON")

    def visit(container):
        for block in blocks(container):
            if not isinstance(block, dict) or not isinstance(block.get("type"), str):
                raise AuditError("Invalid native block")
            kind = block["type"]
            body = block.get(kind, {})
            spans = body.get("rich_text", [])
            content = rich_text(spans)
            if kind.startswith("heading_") and kind[-1:] in ("1", "2", "3"):
                elements.append({"kind": "heading", "level": int(kind[-1]), "text": content})
            elif kind == "code":
                elements.append({"kind": "code_block", "text": content, "language": body.get("language", "")})
            elif kind == "equation":
                elements.append({"kind": "math", "text": body.get("expression", "")})
                manual.append("native equation exists; mathematical validity/typesetting not checked")
            elif kind == "image":
                image_type = body.get("type")
                elements.append({"kind": "image", "src": body.get(image_type, {}).get("url", "")})
            elif kind in ("paragraph", "quote", "callout", "bulleted_list_item", "numbered_list_item", "to_do"):
                mapped = {"bulleted_list_item": "bullet_item", "numbered_list_item": "numbered_item"}.get(kind, kind)
                elements.append({"kind": mapped, "text": content})
            elif kind == "table":
                elements.append({"kind": "table"})
            elif kind == "divider":
                elements.append({"kind": "separator"})
            elif kind != "table_row":
                warnings.append({"code": "native_type_manual", "type": kind})
            if kind not in ("code", "equation"):
                for annotation, output_kind in (("bold", "strong"), ("italic", "emphasis"), ("strikethrough", "strike"), ("code", "code_inline")):
                    active = ""
                    for span in spans + [{}]:
                        if span.get("annotations", {}).get(annotation):
                            active += rich_text([span])
                        elif active:
                            elements.append({"kind": output_kind, "text": active})
                            active = ""
                for span in spans:
                    if span.get("href"):
                        elements.append({"kind": "link", "text": rich_text([span]), "href": span["href"]})
                    if not span.get("annotations", {}).get("code"):
                        warn_text(rich_text([span]), warnings)
            children = block.get("children", body.get("children"))
            if kind == "table" and children is not None:
                rows = [child.get("table_row", {}).get("cells", []) for child in blocks(children) if child.get("type") == "table_row"]
                values = [[rich_text(cell) for cell in row] for row in rows]
                width = body.get("table_width")
                if width is not None and any(len(row) != width for row in rows):
                    errors.append({"code": "native_table_width"})
                tables.append(values)
            if children is not None:
                visit(children)
            elif block.get("has_children"):
                warnings.append({"code": "children_not_in_snapshot", "type": kind})

    visit(snapshot)
    return {"elements": elements, "tables": tables, "errors": errors, "warnings": warnings,
            "profile": "native-notion-snapshot", "manual_checks": sorted(set(manual))}


def apply_expectations(report, expectations=None, source=None):
    if expectations is not None:
        if not isinstance(expectations, dict) or set(expectations) - {"elements", "tables", "source_contains"}:
            raise AuditError("Unknown expectation schema")
        for expected in expectations.get("elements", []):
            if not isinstance(expected, dict) or "kind" not in expected:
                raise AuditError("Each element expectation requires kind")
            count = expected.get("count", 1)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise AuditError("Expected count must be a non-negative integer")
            fields = {key: value for key, value in expected.items() if key != "count"}
            found = sum(all(item.get(key) == value for key, value in fields.items()) for item in report["elements"])
            if found != count:
                report["errors"].append({"code": "element_mismatch", "expected": expected, "actual_count": found})
        if "tables" in expectations and report["tables"] != expectations["tables"]:
            report["errors"].append({"code": "table_mismatch", "expected": expectations["tables"], "actual": report["tables"]})
        for literal in expectations.get("source_contains", []):
            if source is None or literal not in source:
                report["errors"].append({"code": "protected_source_missing", "literal": literal})
    report.update(checks_passed=not report["errors"], expected_semantics_checked=expectations is not None,
                  requires_review=bool(report["warnings"]), visual_verified=False,
                  counts=dict(Counter(item["kind"] for item in report["elements"])),
                  scope="Only supplied structures and selected expectations; not full format, math or live-page verification")
    return report


def preview(source, base_dir, profile="notes"):
    md = parser(profile)

    def image_rule(tokens, index, options, env):
        token = tokens[index]
        src = token.attrGet("src") or ""
        parsed = urlsplit(src)
        if parsed.scheme or parsed.netloc:
            return '<span class="image-note">[远程图片未加载：' + html.escape(token.content) + "]</span>"
        token.attrSet("src", (Path(base_dir) / unquote(parsed.path)).resolve().as_uri())
        token.attrSet("alt", token.content)
        return md.renderer.renderToken(tokens, index, options, env)

    md.renderer.rules["image"] = image_rule
    body = md.render(source)
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>笔记格式预览</title><style>' + \
        'body{max-width:960px;margin:auto;padding:28px;font:17px/1.75 "Segoe UI","Microsoft YaHei",sans-serif;color:#20252d}' + \
        'h1,h2,h3{line-height:1.35;margin:1.1em 0 .6em}p{margin:.7em 0}strong{font-weight:700}' + \
        'pre{padding:14px;overflow:auto;background:#f2f4f7;border-radius:6px}code{font-family:Consolas,monospace}' + \
        'table{border-collapse:collapse;width:100%}th,td{border:1px solid #b8c1cc;padding:8px;text-align:left}' + \
        'blockquote{border-left:4px solid #8196b2;margin-left:0;padding-left:18px;color:#465368}' + \
        'img{max-width:100%;height:auto}.notice{padding:10px;background:#edf3fa;font-size:14px}.image-note{color:#666}' + \
        '</style><p class="notice">本地 CommonMark 预览；公式、平台扩展及最终 Notion/Word/PDF 显示须另行核验。远程图片不加载。</p>' + body + '</html>\n'


def write_new(path, content, inputs):
    target = Path(path).resolve()
    if target in {Path(item).resolve() for item in inputs if item is not None}:
        raise AuditError("Output cannot overwrite an input or expectation file")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="command", required=True)
    for command in ("audit", "audit-notion", "preview"):
        sub = subs.add_parser(command)
        sub.add_argument("input")
        sub.add_argument("--expect")
        sub.add_argument("--output", required=command == "preview")
        if command != "audit-notion":
            sub.add_argument("--profile", choices=("commonmark", "notes"), default="notes")
    args = cli.parse_args(argv)
    try:
        source = None if args.command == "audit-notion" else Path(args.input).read_text(encoding="utf-8")
        if args.command == "preview":
            if args.expect:
                raise AuditError("Use audit --expect separately before preview")
            write_new(args.output, preview(source, Path(args.input).resolve().parent, args.profile), [args.input])
            print(json.dumps({"preview": str(Path(args.output).resolve()), "source_modified": False, "visual_verified": False}))
            return 0
        report = inspect_notion(read_json(args.input)) if args.command == "audit-notion" else inspect_markdown(source, args.profile, Path(args.input).resolve().parent)
        apply_expectations(report, read_json(args.expect) if args.expect else None, source)
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            write_new(args.output, output, [args.input, args.expect])
        print(output, end="")
        return 0 if report["checks_passed"] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
