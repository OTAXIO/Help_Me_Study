from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest
from unittest import mock

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
        environment = mock.patch.dict(os.environ, {"HELP_ME_STUDY_STATE_DIR": str(self.directory)})
        environment.start()
        self.addCleanup(environment.stop)
        self.example = json.loads((ROOT / "skills" / "help-me-shared" / "templates" / "notion-map.example.json").read_text(encoding="utf-8"))

    def workspace(self):
        return Path(state.init_workspace(self.task, "claude")["workspace"])

    def run_cli(self, *args, tool=TOOL, expected=0):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", HELP_ME_STUDY_STATE_DIR=str(self.directory))
        result = subprocess.run([sys.executable, str(tool), *map(str, args)], cwd=self.base,
                                capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_workspace_creates_expected_uncompressed_tree(self):
        root = self.workspace()
        self.assertEqual(root.name, "work_claude")
        self.assertEqual({p.name for p in root.iterdir()}, {"code", "report", "submit", state.MANIFEST})
        self.assertFalse(any(root.rglob("*.zip")))
        self.assertFalse(any(root.rglob("*.tar")))

    def test_collision_preserves_directory_and_file(self):
        (self.task / "work_claude").mkdir()
        marker = self.task / "work_claude" / "原文件.txt"
        marker.write_text("原内容", encoding="utf-8")
        (self.task / "work_claude_2").write_text("occupied", encoding="utf-8")
        root = self.workspace()
        self.assertEqual(root.name, "work_claude_3")
        self.assertEqual(marker.read_text(encoding="utf-8"), "原内容")
        self.assertEqual((self.task / "work_claude_2").read_text(encoding="utf-8"), "occupied")

    def test_agents_get_separate_directories(self):
        self.assertEqual(self.workspace().name, "work_claude")
        self.assertEqual(Path(state.init_workspace(self.task, "codex")["workspace"]).name, "work_codex")
        self.assertFalse((self.task / "work").exists())

    def test_workspace_requires_valid_agent_name(self):
        for agent in (None, "", "Claude", "work/x", "a_b"):
            with self.assertRaises(state.StateError):
                state.init_workspace(self.task, agent)

    def test_explicit_resume_preserves_manifest_and_files(self):
        root = self.workspace()
        before = (root / state.MANIFEST).read_bytes()
        (root / "code" / "solution.py").write_text("print(1)\n", encoding="utf-8")
        result = state.init_workspace(self.task, resume=root)
        self.assertTrue(result["resumed"])
        self.assertEqual((root / state.MANIFEST).read_bytes(), before)
        self.assertTrue((root / "code" / "solution.py").exists())

    def test_resume_rejects_unrelated_directory(self):
        root = self.workspace()
        other = self.base / "other-task"
        other.mkdir()
        with self.assertRaises(state.StateError):
            state.init_workspace(other, resume=root)

    def test_resume_rejects_plain_work_without_manifest(self):
        root = self.task / "work"
        root.mkdir()
        with self.assertRaises(state.StateError):
            state.init_workspace(self.task, resume=root)

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
        self.assertEqual(report["skills"], len(json.loads((ROOT / 'suite.json').read_text(encoding='utf-8'))['skills']))
        installed = target / "help-me-shared" / "scripts" / "study_state.py"
        result = self.run_cli("workspace", "init", "--task-dir", self.task, "--agent", "claude", tool=installed)
        self.assertEqual(Path(json.loads(result.stdout)["workspace"]).name, "work_claude")

    def test_existing_install_is_not_overwritten(self):
        target = self.base / "installed-skills"
        (target / "help-me-class-learning-note").mkdir(parents=True)
        marker = target / "help-me-class-learning-note" / "keep.txt"
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

    def test_validator_detects_retired_callable_skill(self):
        target = self.base / "installed-skills"
        installer.install(target)
        manifest = json.loads((ROOT / "suite.json").read_text(encoding="utf-8"))
        legacy = json.loads((ROOT / "manifests" / "1.0.0.json").read_text(encoding="utf-8"))
        retired = next(name for name in {key.split("/")[0] for key in legacy["files"]}
                       if name not in manifest["skills"] + [manifest["shared"]])
        extra = target / retired
        extra.mkdir()
        (extra / "SKILL.md").write_text("unexpected", encoding="utf-8")
        report = validator.validate(target)
        self.assertFalse(report["passed"])
        self.assertTrue(any(retired in issue for issue in report["issues"]))

    def test_cli_failure_has_nonzero_status_without_creating_mapping(self):
        result = self.run_cli("notion", "get", "--course", "missing", expected=2)
        self.assertIn("No matching", json.loads(result.stderr)["error"])
        self.assertFalse(self.directory.exists())

    def fake_release(self):
        release = Path(tempfile.mkdtemp(prefix="next-release-", dir=self.base))
        shutil.copytree(ROOT / "skills", release / "skills", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(ROOT / "manifests", release / "manifests")
        manifest = json.loads((ROOT / "suite.json").read_text(encoding="utf-8"))
        manifest["version"] = "synthetic-next-version"
        (release / "suite.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = release / "skills" / "help-me-shared" / "references" / "report.md"
        report.write_text(report.read_text(encoding="utf-8") + "\nSynthetic next-release change.\n", encoding="utf-8")
        return release

    def test_update_backs_up_known_files_and_preserves_notion_and_extra(self):
        target = self.base / "installed-skills"
        installer.install(target)
        report = target / "help-me-shared" / "references" / "report.md"
        original = report.read_bytes()
        extra = target / "help-me-class-learning-note" / "personal-extra.md"
        extra.write_text("local preference", encoding="utf-8")
        state.put_mapping(self.directory, self.example, True)
        mapping_before = (self.directory / "notion-map.json").read_bytes()
        release = self.fake_release()
        with mock.patch.object(installer, "ROOT", release):
            plan = installer.install(target, update=True)
        self.assertEqual(plan["replaced"], ["help-me-shared/references/report.md"])
        self.assertEqual((Path(plan["backup"]) / "help-me-shared" / "references" / "report.md").read_bytes(), original)
        self.assertIn(b"Synthetic next-release change", report.read_bytes())
        self.assertEqual(extra.read_text(encoding="utf-8"), "local preference")
        self.assertEqual((self.directory / "notion-map.json").read_bytes(), mapping_before)

    def test_update_refuses_local_modification_before_mutating_other_files(self):
        target = self.base / "installed-skills"
        installer.install(target)
        report = target / "help-me-shared" / "references" / "report.md"
        report.write_text("user replaced this report guidance", encoding="utf-8")
        before = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in target.rglob("*") if p.is_file()}
        release = self.fake_release()
        with mock.patch.object(installer, "ROOT", release):
            with self.assertRaisesRegex(ValueError, "Local modifications"):
                installer.install(target, update=True)
        after = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_update_dry_run_does_not_write_files_or_backups(self):
        target = self.base / "installed-skills"
        installer.install(target)
        before = {p.relative_to(self.base).as_posix(): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        release = self.fake_release()
        with mock.patch.object(installer, "ROOT", release):
            plan = installer.install(target, dry_run=True, update=True)
        self.assertEqual(len(plan["replaced"]), 1)
        self.assertIsNone(plan["backup"])
        for name, content in before.items():
            self.assertEqual((self.base / name).read_bytes(), content)
        self.assertFalse(any(self.directory.rglob("backup-manifest.json")))

    def test_update_uses_legacy_hashes_without_receipt(self):
        target = self.base / "legacy-install"
        old_report = target / "help-me-shared" / "references" / "report.md"
        old_report.parent.mkdir(parents=True)
        legacy_text = (ROOT / "tests" / "fixtures" / "report-v1.0.0.txt").read_bytes().replace(b"\r\n", b"\n")
        old_report.write_bytes(legacy_text)
        baseline = json.loads((ROOT / "manifests" / "1.0.0.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(hashlib.sha256(legacy_text).hexdigest(), baseline["help-me-shared/references/report.md"])
        plan = installer.install(target, update=True)
        self.assertEqual(plan["replaced"], ["help-me-shared/references/report.md"])
        self.assertEqual((Path(plan["backup"]) / "help-me-shared/references/report.md").read_bytes(), legacy_text)
        self.assertTrue(validator.validate(target)["passed"])

    def retired_release(self):
        target = self.base / "retirement-target"
        installer.install(target)
        release = self.fake_release()
        manifest_path = release / "suite.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = "help-me-speech"
        manifest["skills"].remove(name)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return target, release, name

    def test_retired_skill_is_moved_to_verified_backup(self):
        target, release, name = self.retired_release()
        before = {p.relative_to(target / name).as_posix(): p.read_bytes()
                  for p in (target / name).rglob("*") if p.is_file()}
        with mock.patch.object(installer, "ROOT", release):
            plan = installer.install(target, update=True)
            again = installer.install(target, update=True)
        self.assertEqual(plan["removed"], [name])
        self.assertFalse((target / name).exists())
        for relative, data in before.items():
            self.assertEqual((Path(plan["backup"]) / name / relative).read_bytes(), data)
        self.assertEqual(again["removed"], [])
        receipt = json.loads(next(self.directory.rglob("receipt.json")).read_text(encoding="utf-8"))
        self.assertFalse(any(key.startswith(name + "/") for key in receipt["files"]))

    def test_retired_skill_changes_block_entire_update(self):
        for kind in ("edit", "extra", "missing", "empty-directory"):
            with self.subTest(kind=kind):
                # Each case uses a separate installation and receipt.
                target = self.base / ("retired-" + kind)
                installer.install(target)
                release = self.fake_release()
                manifest_path = release / "suite.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                name = "help-me-speech"
                manifest["skills"].remove(name)
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                entry = target / name / "SKILL.md"
                if kind == "edit":
                    entry.write_text("personal instructions", encoding="utf-8")
                elif kind == "extra":
                    (target / name / "personal.txt").write_text("keep", encoding="utf-8")
                elif kind == "missing":
                    entry.unlink()
                else:
                    (target / name / "personal-empty").mkdir()
                before = {p.relative_to(target).as_posix(): p.read_bytes()
                          for p in target.rglob("*") if p.is_file()}
                receipts = {p: p.read_bytes() for p in self.directory.rglob("receipt.json")}
                with mock.patch.object(installer, "ROOT", release):
                    with self.assertRaisesRegex(ValueError, "Retired.*" + name):
                        installer.install(target, update=True)
                self.assertEqual(before, {p.relative_to(target).as_posix(): p.read_bytes()
                                         for p in target.rglob("*") if p.is_file()})
                self.assertTrue((target / name).is_dir())
                for path, data in receipts.items():
                    self.assertEqual(path.read_bytes(), data)

    def test_retired_skill_dry_run_preserves_directory_and_state(self):
        target, release, name = self.retired_release()
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with mock.patch.object(installer, "ROOT", release):
            plan = installer.install(target, update=True, dry_run=True)
        self.assertEqual(plan["removed"], [name])
        self.assertIsNone(plan["backup"])
        self.assertTrue((target / name).is_dir())
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_retired_skill_only_update_still_creates_backup(self):
        target, release, name = self.retired_release()
        report = Path("help-me-shared/references/report.md")
        (release / "skills" / report).write_bytes((target / report).read_bytes())
        with mock.patch.object(installer, "ROOT", release):
            plan = installer.install(target, update=True)
        self.assertEqual(plan["replaced"], [])
        self.assertEqual(plan["added"], [])
        self.assertEqual(plan["removed"], [name])
        self.assertTrue((Path(plan["backup"]) / name / "SKILL.md").is_file())

    def test_retired_skill_without_receipt_uses_known_baseline(self):
        target, release, name = self.retired_release()
        receipt = next(self.directory.rglob("receipt.json"))
        known = json.loads(receipt.read_text(encoding="utf-8"))
        # Synthetic release baseline, without changing the repository's history.
        (release / "manifests" / "1.0.0.json").write_text(json.dumps(known), encoding="utf-8")
        receipt.unlink()
        unrelated = target / "unrelated-user-skill"
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text("keep", encoding="utf-8")
        with mock.patch.object(installer, "ROOT", release):
            plan = installer.install(target, update=True)
        self.assertEqual(plan["removed"], [name])
        self.assertFalse((target / name).exists())
        self.assertEqual((unrelated / "SKILL.md").read_text(encoding="utf-8"), "keep")

    def test_retired_skill_link_is_preserved_and_update_stops(self):
        target, release, name = self.retired_release()
        external = self.base / "external"
        external.mkdir()
        secret = external / "private.txt"
        secret.write_text("private", encoding="utf-8")
        entry = target / name / "linked-assets"
        try:
            entry.symlink_to(external, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                raise
            # A Windows directory junction needs no symlink privilege.
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(entry), str(external)],
                                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stderr)
        receipt = next(self.directory.rglob("receipt.json"))
        before = receipt.read_bytes()
        with mock.patch.object(installer, "ROOT", release):
            with self.assertRaisesRegex(ValueError, "escapes|linked"):
                installer.install(target, update=True)
        self.assertTrue(os.path.lexists(entry))
        self.assertEqual((entry / "private.txt").read_text(encoding="utf-8"), "private")
        self.assertEqual(secret.read_text(encoding="utf-8"), "private")
        self.assertEqual(receipt.read_bytes(), before)

    def test_update_is_idempotent_and_receipt_survives(self):
        target = self.base / "installed-skills"
        installer.install(target)
        receipts = list(self.directory.rglob("receipt.json"))
        self.assertEqual(len(receipts), 1)
        before = receipts[0].read_bytes()
        plan = installer.install(target, update=True)
        self.assertEqual(plan["added"], [])
        self.assertEqual(plan["replaced"], [])
        self.assertFalse(plan["installation_state_modified"])
        self.assertEqual(receipts[0].read_bytes(), before)

    def test_update_rejects_folder_occupied_by_file_before_writes(self):
        target = self.base / "installed-skills"
        target.mkdir()
        (target / "help-me-speech").write_text("occupied", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "occupied by a file"):
            installer.install(target, update=True)
        self.assertFalse((target / "help-me-study").exists())


if __name__ == "__main__":
    unittest.main()
