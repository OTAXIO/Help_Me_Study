from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "help-me-shared" / "scripts" / "format_audit.py"
SPEC = importlib.util.spec_from_file_location("format_audit", TOOL)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class FormatTests(unittest.TestCase):
    def check(self, source, expected=None, profile="notes", base_dir=None):
        return audit.apply_expectations(audit.inspect_markdown(source, profile, base_dir), expected, source)

    def test_whitespace_bold_failure_is_detected_by_structure(self):
        source = "**标签： **说明\n"
        report = self.check(source, {"elements": [{"kind": "strong", "text": "标签："}]})
        self.assertFalse(report["checks_passed"])
        self.assertEqual(report["counts"].get("strong", 0), 0)
        self.assertTrue(report["requires_review"])

    def test_correct_bold_and_explanation_remain_distinct(self):
        source = "- **标签：** 普通说明\n"
        report = self.check(source, {"elements": [{"kind": "strong", "text": "标签："}, {"kind": "list_item"}]})
        self.assertTrue(report["checks_passed"])
        rendered = audit.preview(source, ROOT)
        self.assertIn("<strong>标签：</strong> 普通说明", rendered)

    def test_double_escaped_marks_do_not_count_as_bold(self):
        report = self.check(r"\*\*标签：\*\* 说明", {"elements": [{"kind": "strong", "text": "标签："}]})
        self.assertFalse(report["checks_passed"])

    def test_full_fixture_semantics_and_table_cells(self):
        path = ROOT / "qa" / "cases" / "format-good.md"
        expected = audit.read_json(path.with_suffix(".expect.json"))
        report = self.check(path.read_text(encoding="utf-8"), expected, base_dir=path.parent)
        self.assertTrue(report["checks_passed"], report)
        self.assertFalse(report["requires_review"], report)
        self.assertFalse(report["visual_verified"])

    def test_nested_styles_preserve_text(self):
        report = self.check("**粗*斜*体**", {"elements": [{"kind": "strong", "text": "粗斜体"}, {"kind": "emphasis", "text": "斜"}]})
        self.assertTrue(report["checks_passed"])

    def test_heading_jump_is_reviewed_without_forcing_first_h1(self):
        report = self.check("## 章节\n\n#### 子节\n")
        self.assertEqual([item["code"] for item in report["warnings"]], ["heading_level_jump"])
        self.assertFalse(self.check("## 章节\n")["warnings"])

    def test_paragraph_merge_breaks_expected_structure(self):
        expected = {"elements": [{"kind": "paragraph", "count": 2}]}
        self.assertFalse(self.check("第一段\n第二段\n", expected)["checks_passed"])
        self.assertTrue(self.check("第一段\n\n第二段\n", expected)["checks_passed"])

    def test_nested_lists_and_nondefault_start(self):
        source = "3. 主项\n   - 子项\n4. 下一项\n"
        expected = {"elements": [{"kind": "ordered_list", "start": 3}, {"kind": "bullet_list"}, {"kind": "list_item", "count": 3}]}
        self.assertTrue(self.check(source, expected)["checks_passed"])
        self.assertTrue(self.check("0. 项目\n", {"elements": [{"kind": "ordered_list", "start": 0}]})["checks_passed"])

    def test_unclosed_fence_and_accidental_whole_note_wrapper(self):
        self.assertIn("unclosed_fence", [item["code"] for item in self.check("```python\nprint(1)\n")["errors"]])
        report = self.check("```markdown\n# 标题\n正文\n```\n", {"elements": [{"kind": "heading", "level": 1, "text": "标题"}]})
        self.assertFalse(report["checks_passed"])

    def test_code_and_math_candidates_are_not_globally_cleaned(self):
        source = '`x**2` `*.png` `C:\\work\\notes`\n\n```python\nx**2\ntext="**example**"\n```\n\n$x**2$\n'
        report = self.check(source, {"source_contains": ['`x**2`', '"**example**"', '$x**2$'],
                                      "elements": [{"kind": "code_inline", "text": "x**2"}]})
        self.assertTrue(report["checks_passed"])
        self.assertFalse(report["warnings"])
        self.assertIn("math validity/typesetting", report["manual_checks"])

    def test_literal_syntax_example_in_code_stays_literal(self):
        report = self.check('`**标签：**`\n', {"elements": [{"kind": "code_inline", "text": "**标签：**"}, {"kind": "strong", "count": 0}]})
        self.assertTrue(report["checks_passed"])
        self.assertFalse(report["warnings"])

    def test_legacy_math_wrapper_requires_review(self):
        report = self.check("公式 $`x[n]`$ 和 $`X''`$。")
        self.assertEqual([w["code"] for w in report["warnings"]],
                         ["legacy_math_backtick_wrapper"] * 2)
        self.assertTrue(report["requires_review"])

    def test_math_quotes_and_code_examples_are_preserved(self):
        source = "公式 $X''$ 与 $x[n]$。示例 ``$`x[n]`$``。\n\n```text\n$`x[n]`$\n```\n"
        report = self.check(source)
        self.assertFalse(report["warnings"], report)

    def test_table_data_loss_is_caught_against_intended_cells(self):
        source = "|A|B|\n|---|---|\n|1|2|lost|\n"
        report = self.check(source, {"tables": [[["A", "B"], ["1", "2", "lost"]]]})
        self.assertFalse(report["checks_passed"])

    def test_profile_mismatch_cannot_claim_table_or_strike(self):
        source = "~~删除~~\n\n|A|B|\n|---|---|\n|1|2|\n"
        report = self.check(source, {"elements": [{"kind": "strike", "text": "删除"}, {"kind": "table"}]}, profile="commonmark")
        self.assertFalse(report["checks_passed"])

    def test_task_and_callout_require_target_mapping(self):
        report = self.check("- [ ] 任务\n\n> [!NOTE]\n> 提示\n")
        self.assertEqual(sum(item["code"] == "target_extension_review" for item in report["warnings"]), 2)

    def test_missing_local_image_is_an_error_without_network_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.check("![图](missing.png)\n", base_dir=directory)
            self.assertFalse(report["checks_passed"])
        rendered = audit.preview("![远程](https://example.invalid/image.png)", ROOT)
        self.assertIn("远程图片未加载", rendered)
        self.assertNotIn('<img src="https://', rendered)

    def test_preview_escapes_html_and_keeps_code_content(self):
        rendered = audit.preview('<script>alert(1)</script>\n\n```python\nx**2\n```', ROOT)
        tree = Tags()
        tree.feed(rendered)
        self.assertNotIn("script", [tag for tag, _ in tree.tags])
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("x**2", rendered)

    def test_source_audit_and_preview_cli_never_modify_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "note.md"
            original = b"# Heading\n\n`x**2`\n"
            source.write_bytes(original)
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            for command in (["audit", str(source)], ["preview", str(source), "--output", str(root / "preview.html")]):
                result = subprocess.run([sys.executable, str(TOOL), *command], env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(source.read_bytes(), original)
            rejected = subprocess.run([sys.executable, str(TOOL), "preview", str(source), "--output", str(source)], env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(source.read_bytes(), original)

    def test_existing_output_and_expectation_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.txt"
            path.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                audit.write_new(path, "new", [])
            with self.assertRaises(audit.AuditError):
                audit.write_new(path, "new", [path])
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_native_bold_is_verified_by_annotations_not_asterisks(self):
        plain = {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "**标签：**"}}]}}
        expected = {"elements": [{"kind": "strong", "text": "标签："}]}
        self.assertFalse(audit.apply_expectations(audit.inspect_notion([plain]), expected)["checks_passed"])
        native = {"type": "paragraph", "paragraph": {"rich_text": [
            {"text": {"content": "标签"}, "annotations": {"bold": True}},
            {"text": {"content": "："}, "annotations": {"bold": True}},
            {"text": {"content": "说明"}, "annotations": {"bold": False}}
        ]}}
        report = audit.apply_expectations(audit.inspect_notion([native]), expected)
        self.assertTrue(report["checks_passed"])
        self.assertFalse(report["visual_verified"])

    def test_native_code_equation_and_table_remain_structured(self):
        text = lambda value: [{"type": "text", "text": {"content": value}}]
        snapshot = {"results": [
            {"type": "code", "code": {"rich_text": text("x**2"), "language": "python"}},
            {"type": "equation", "equation": {"expression": r"\frac{a}{b}"}},
            {"type": "table", "table": {"table_width": 2}, "children": [
                {"type": "table_row", "table_row": {"cells": [text("A"), text("B")]}},
                {"type": "table_row", "table_row": {"cells": [text("1"), text("2")]}}
            ]}
        ], "has_more": False}
        expected = {"elements": [{"kind": "code_block", "text": "x**2", "language": "python"}, {"kind": "math", "text": r"\frac{a}{b}"}],
                    "tables": [[["A", "B"], ["1", "2"]]]}
        report = audit.apply_expectations(audit.inspect_notion(snapshot), expected)
        self.assertTrue(report["checks_passed"])
        self.assertFalse(report["warnings"])

    def test_native_pagination_and_missing_children_limit_coverage(self):
        self.assertFalse(audit.apply_expectations(audit.inspect_notion({"results": [], "has_more": True}))["checks_passed"])
        report = audit.inspect_notion([{"type": "paragraph", "paragraph": {"rich_text": []}, "has_children": True}])
        self.assertIn("children_not_in_snapshot", [item["code"] for item in report["warnings"]])
        with self.assertRaises(audit.AuditError):
            audit.inspect_notion({"markdown": "**标签：**"})

    def test_invalid_expectation_schema_is_not_silently_ignored(self):
        with self.assertRaises(audit.AuditError):
            self.check("正文", {"elementz": []})


if __name__ == "__main__":
    unittest.main()
