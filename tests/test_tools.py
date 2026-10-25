from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "help-me-shared" / "scripts" / "study_state.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load("study_state", TOOL)
installer = load("install_suite", ROOT / "scripts" / "install.py")
validator = load("validate_suite", ROOT / "scripts" / "validate_suite.py")


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="help-me-study-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.task = self.base / "课程与作业"
        self.task.mkdir()
        self.directory = self.base / "private-state"
        self.example = json.loads((ROOT / "skills" / "help-me-shared" / "templates" / "notion-map.example.json").read_text(encoding="utf-8"))

    def workspace(self):
        return Path(state.init_workspace(self.task)["workspace"])

    def run_cli(self, *args, tool=TOOL, expected=0):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", HELP_ME_STUDY_STATE_DIR=str(self.directory))
        result = subprocess.run([sys.executable, str(tool), *map(str, args)], cwd=self.base,
                                capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_workspace_creates_expected_uncompressed_tree(self):
        root = self.workspace()
        self.assertEqual(root.name, "work")
        self.assertEqual({p.name for p in root.iterdir()}, {"code", "report", "submit", state.MANIFEST})
        self.assertFalse(any(root.rglob("*.zip")))
        self.assertFalse(any(root.rglob("*.tar")))

    def test_collision_preserves_directory_and_file(self):
        (self.task / "work").mkdir()
        marker = self.task / "work" / "原文件.txt"
        marker.write_text("原内容", encoding="utf-8")
        (self.task / "work_codex").write_text("occupied", encoding="utf-8")
        root = self.workspace()
        self.assertEqual(root.name, "work_codex_2")
        self.assertEqual(marker.read_text(encoding="utf-8"), "原内容")
        self.assertEqual((self.task / "work_codex").read_text(encoding="utf-8"), "occupied")

    def test_explicit_resume_preserves_manifest_and_files(self):
        root = self.workspace()
        before = (root / state.MANIFEST).read_bytes()
        (root / "code" / "solution.py").write_text("print(1)\n", encoding="utf-8")
        result = state.init_workspace(self.task, root)
        self.assertTrue(result["resumed"])
        self.assertEqual((root / state.MANIFEST).read_bytes(), before)
        self.assertTrue((root / "code" / "solution.py").exists())

    def test_resume_rejects_unrelated_directory(self):
        root = self.workspace()
        other = self.base / "other-task"
        other.mkdir()
        with self.assertRaises(state.StateError):
            state.init_workspace(other, root)

    def test_resume_rejects_plain_work_without_manifest(self):
        root = self.task / "work"
        root.mkdir()
        with self.assertRaises(state.StateError):
            state.init_workspace(self.task, root)

    def test_outline_cannot_be_approved_without_human_receipt(self):
        root = self.workspace()
        (root / "outline.md").write_text("# 大纲\n第一章\n", encoding="utf-8")
        result = state.set_outline(root, "outline.md")
        self.assertEqual(result["status"], "pending")
        with self.assertRaises(state.StateError):
            state.approve_outline(root, result["sha256"])
        self.assertFalse(state.outline_status(root)["approved"])

    def test_outline_change_invalidates_previous_receipt(self):
        root = self.workspace()
        outline = root / "outline.md"
        outline.write_text("# 原大纲\n", encoding="utf-8")
        receipt = state.set_outline(root, "outline.md")
        self.assertTrue(state.approve_outline(root, receipt["sha256"], True)["approved"])
        outline.write_text("# 已改变整体结构\n", encoding="utf-8")
        result = state.outline_status(root)
        self.assertEqual(result["status"], "changed")
        self.assertFalse(result["approved"])
        with self.assertRaises(state.StateError):
            state.approve_outline(root, receipt["sha256"], True)

    def test_outline_cannot_escape_workspace(self):
        root = self.workspace()
        (root.parent / "outside.md").write_text("outside", encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.set_outline(root, "../outside.md")

    def test_missing_outline_is_not_approved(self):
        self.assertEqual(state.outline_status(self.workspace())["status"], "missing")

    def test_deleted_outline_is_not_approved(self):
        root = self.workspace()
        source = root / "outline.md"
        source.write_text("plan", encoding="utf-8")
        state.set_outline(root, "outline.md")
        source.unlink()
        self.assertEqual(state.outline_status(root)["status"], "missing-file")

    def test_registry_read_does_not_create_state(self):
        self.assertEqual(state.load_registry(self.directory)["courses"], [])
        self.assertFalse(self.directory.exists())

    def test_put_requires_actual_remote_check_claim(self):
        with self.assertRaises(state.StateError):
            state.put_mapping(self.directory, self.example)
        self.assertFalse(self.directory.exists())

    def test_mapping_survives_a_fresh_process(self):
        state.put_mapping(self.directory, self.example, True)
        process = self.run_cli("notion", "get", "--course", self.example["course"], "--term", self.example["term"])
        result = json.loads(process.stdout)
        self.assertTrue(result["must_read_live_pages"])
        self.assertEqual(len(result["mapping"]["pages"]), 2)
        self.assertEqual(result["mapping"]["pages"][1]["parent_id"], "2" * 32)

    def test_multiple_terms_require_selection(self):
        state.put_mapping(self.directory, self.example, True)
        another = deepcopy(self.example)
        another["term"] = "第二个合成学期"
        state.put_mapping(self.directory, another, True)
        with self.assertRaisesRegex(state.StateError, "Ambiguous"):
            state.get_mapping(self.directory, self.example["course"])
        self.assertEqual(state.get_mapping(self.directory, self.example["course"], another["term"])["mapping"]["term"], another["term"])

    def test_parent_change_needs_explicit_intent(self):
        state.put_mapping(self.directory, self.example, True)
        new = deepcopy(self.example)
        new["parent"]["page_id"] = "4" * 32
        new["parent"]["url"] = "https://www.notion.so/" + "4" * 32
        new["pages"][0]["parent_id"] = "4" * 32
        with self.assertRaisesRegex(state.StateError, "Parent changed"):
            state.put_mapping(self.directory, new, True)
        self.assertEqual(state.get_mapping(self.directory, new["course"], new["term"])["mapping"]["parent"]["page_id"], "1" * 32)
        state.put_mapping(self.directory, new, True, True)
        self.assertEqual(state.get_mapping(self.directory, new["course"], new["term"])["mapping"]["parent"]["page_id"], "4" * 32)

    def test_updates_do_not_duplicate_course(self):
        state.put_mapping(self.directory, self.example, True)
        self.example["pages"][0]["title"] = "更新标题"
        state.put_mapping(self.directory, self.example, True)
        courses = state.load_registry(self.directory)["courses"]
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["pages"][0]["title"], "更新标题")

    def test_corrupt_registry_is_preserved(self):
        self.directory.mkdir()
        path = self.directory / "notion-map.json"
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.put_mapping(self.directory, self.example, True)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_existing_lock_stops_update_and_remains(self):
        self.directory.mkdir()
        lock = self.directory / "notion-map.json.lock"
        lock.write_text("active", encoding="utf-8")
        with self.assertRaisesRegex(state.StateError, "locked"):
            state.put_mapping(self.directory, self.example, True)
        self.assertEqual(lock.read_text(encoding="utf-8"), "active")
        self.assertFalse((self.directory / "notion-map.json").exists())

    def test_cycles_and_orphans_rejected_before_state_write(self):
        for parent in ("3" * 32, "9" * 32):
            with self.subTest(parent=parent):
                entry = deepcopy(self.example)
                entry["pages"][0]["parent_id"] = parent
                with self.assertRaises(state.StateError):
                    state.put_mapping(self.directory, entry, True)
        self.assertFalse(self.directory.exists())

    def test_url_and_id_mismatch_rejected(self):
        self.example["parent"]["url"] = "https://www.notion.so/" + "9" * 32
        with self.assertRaisesRegex(state.StateError, "same page_id"):
            state.validate_entry(self.example)

    def test_credential_fields_and_non_notion_urls_rejected(self):
        entry = deepcopy(self.example)
        entry["TOKEN"] = "synthetic-test-value"
        with self.assertRaises(state.StateError):
            state.validate_entry(entry)
        entry = deepcopy(self.example)
        entry["parent"]["url"] = "https://example.invalid/" + "1" * 32
        with self.assertRaises(state.StateError):
            state.validate_entry(entry)

    def test_uuids_normalize_and_null_canvas_is_allowed(self):
        entry = deepcopy(self.example)
        entry["parent"]["page_id"] = "11111111-1111-1111-1111-111111111111"
        entry["parent"]["url"] = "https://www.notion.so/11111111-1111-1111-1111-111111111111"
        self.assertEqual(state.validate_entry(entry)["parent"]["page_id"], "1" * 32)

    def test_duplicate_pages_rejected(self):
        self.example["pages"].append(deepcopy(self.example["pages"][0]))
        with self.assertRaisesRegex(state.StateError, "Duplicate"):
            state.validate_entry(self.example)

    def test_canvas_id_must_be_positive_digits(self):
        for bad in (True, 0, -2, "unknown"):
            with self.subTest(bad=bad):
                self.example["canvas_course_id"] = bad
                with self.assertRaises(state.StateError):
                    state.validate_entry(self.example)

    def test_dry_run_installs_nothing(self):
        target = self.base / "not-created" / "skills"
        plan = installer.install(target, True)
        self.assertTrue(plan["dry_run"])
        self.assertFalse(target.exists())

    def test_installed_suite_links_and_cold_start_tool_work(self):
        target = self.base / "installed-skills"
        installer.install(target)
        report = validator.validate(target)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["skills"], 5)
        installed = target / "help-me-shared" / "scripts" / "study_state.py"
        result = self.run_cli("workspace", "init", "--task-dir", self.task, tool=installed)
        self.assertEqual(Path(json.loads(result.stdout)["workspace"]).name, "work")

    def test_existing_install_is_not_overwritten(self):
        target = self.base / "installed-skills"
        (target / "help-me-notes").mkdir(parents=True)
        marker = target / "help-me-notes" / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            installer.install(target)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertFalse((target / "help-me-study").exists())

    def test_validator_detects_missing_installed_resource(self):
        target = self.base / "installed-skills"
        installer.install(target)
        (target / "help-me-shared" / "references" / "core.md").unlink()
        self.assertFalse(validator.validate(target)["passed"])

    def test_cli_failure_has_nonzero_status_without_creating_mapping(self):
        result = self.run_cli("notion", "get", "--course", "missing", expected=2)
        self.assertIn("No matching", json.loads(result.stderr)["error"])
        self.assertFalse(self.directory.exists())


if __name__ == "__main__":
    unittest.main()
