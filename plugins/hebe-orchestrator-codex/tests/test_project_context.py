"""Portable project contract and optional Playwright kit behavior."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "project_context.py"
SPEC = importlib.util.spec_from_file_location("hebe_project_context", SCRIPT)
context_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(context_module)


class ProjectContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve() / "project"
        self.project.mkdir()

    def test_init_preserves_existing_contract_and_reports_missing_bridge(self):
        agents = self.project / "AGENTS.md"
        claude = self.project / "CLAUDE.md"
        agents.write_text("# Existing rules\n", encoding="utf-8")
        claude.write_text("# Claude rules\n", encoding="utf-8")
        first = context_module.initialize(self.project, "Product", True)
        second = context_module.initialize(self.project, "Product", True)
        self.assertEqual(first["actions"]["AGENTS.md"], "preserved")
        self.assertEqual(first["actions"]["CLAUDE.md"], "preserved_import_missing")
        self.assertEqual(second["actions"], first["actions"])
        self.assertEqual(agents.read_text(encoding="utf-8"), "# Existing rules\n")
        self.assertEqual(claude.read_text(encoding="utf-8"), "# Claude rules\n")

    def test_status_lists_applicable_agents_from_ancestors(self):
        (self.project / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
        child = self.project / "app" / "src"
        child.mkdir(parents=True)
        (self.project / "app" / "AGENTS.md").write_text("# App\n", encoding="utf-8")
        result = context_module.status(child)
        self.assertEqual(result["applicable_agents"][-2:],
                         [str(self.project / "AGENTS.md"), str(self.project / "app" / "AGENTS.md")])
        self.assertEqual(result["host_loaded"], "unknown")
        self.assertFalse(result["agents_md"])

    def test_status_rejects_symlinked_contract(self):
        outside = self.project.parent / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        (self.project / "AGENTS.md").symlink_to(outside)
        with self.assertRaises(context_module.ContextError):
            context_module.status(self.project)

    def test_existing_playwright_config_preserves_smoke_location(self):
        (self.project / "package.json").write_text(json.dumps({
            "devDependencies": {"@playwright/test": "1.0.0"},
            "scripts": {"e2e": "playwright test", "build": "vite build"},
        }), encoding="utf-8")
        config = self.project / "playwright.config.mjs"
        config.write_text("export default { testDir: './custom-tests' };\n", encoding="utf-8")
        result = context_module.web_initialize(self.project)
        self.assertEqual(result["actions"]["playwright_config"], "preserved_existing:playwright.config.mjs")
        self.assertEqual(result["actions"]["tests/e2e/smoke.spec.ts"], "not_created_existing_config")
        self.assertFalse((self.project / "tests/e2e/smoke.spec.ts").exists())
        self.assertEqual(context_module.status(self.project)["playwright_dependency"], True)
        self.assertEqual(context_module.status(self.project)["playwright_scripts"], ["e2e"])

    def test_nested_status_uses_nearest_node_and_playwright_ancestor(self):
        (self.project / "package.json").write_text(json.dumps({
            "devDependencies": {"@playwright/test": "1.0.0"},
            "scripts": {"e2e": "playwright test"},
        }), encoding="utf-8")
        config = self.project / "playwright.config.ts"
        config.write_text("export default {};\n", encoding="utf-8")
        nested = self.project / "app"
        nested.mkdir()
        result = context_module.status(nested)
        self.assertEqual(result["playwright_config_path"], str(config))
        self.assertEqual(result["package_json_path"], str(self.project / "package.json"))
        self.assertTrue(result["playwright_dependency"])
        self.assertEqual(result["playwright_scripts"], ["e2e"])
        (nested / "package.json").write_text("{}", encoding="utf-8")
        web_result = context_module.web_initialize(nested)
        self.assertEqual(web_result["actions"]["playwright_config"], "preserved_existing:../playwright.config.ts")
        self.assertEqual(web_result["actions"]["tests/e2e/smoke.spec.ts"], "not_created_existing_config")

    def test_new_playwright_config_and_smoke_are_idempotent(self):
        (self.project / "package.json").write_text("{}", encoding="utf-8")
        first = context_module.web_initialize(self.project)
        self.assertEqual(first["actions"]["playwright_config"], "created")
        self.assertEqual(first["actions"]["tests/e2e/smoke.spec.ts"], "created")
        second = context_module.web_initialize(self.project)
        self.assertEqual(second["actions"]["playwright_config"], "preserved_existing:playwright.config.ts")
        self.assertEqual(second["actions"]["tests/e2e/smoke.spec.ts"], "not_created_existing_config")
        self.assertEqual(context_module.status(self.project)["playwright_dependency"], False)


if __name__ == "__main__":
    unittest.main()
