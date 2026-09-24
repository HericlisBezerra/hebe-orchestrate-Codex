"""Observed model catalog: persistence, recommendation and hostile input."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import model_registry as registry


def model(model_id, version, *, quality=.8, family="synthetic", capabilities=None):
    return {"id": model_id, "family": family, "version": version,
            "capabilities": capabilities or ["engineering"], "efforts": ["low", "high"],
            "max_parallel": 3,
            "metadata": {"quality": quality, "latency_ms": 200, "cost_per_million": 2}}


class RegistryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "user"
        self.home.mkdir(mode=0o700)
        self.env = {**os.environ, "HOME": str(self.home)}

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "model_registry.py"), *args],
                              env=self.env, text=True, capture_output=True, timeout=30)

    def snapshot(self, models, time="2026-09-23T12:00:00Z"):
        return {"source": "host.synthetic", "observed_at": time, "models": models}

    def input(self, data):
        path = self.root / "snapshot.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_import_private_diff_and_recommendation(self):
        first = self.cli("import", "--file", self.input(self.snapshot([model("model-a", "1")])))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["changes"], [{"kind": "new_model", "model": "model-a"}])
        target = self.home / ".config/hebe-brain/model-catalog.json"
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
        second = self.cli("import", "--file", self.input(self.snapshot(
            [model("model-a", "1"), model("model-b", "2", quality=.95)], "2026-09-24T12:00:00Z")))
        self.assertEqual(second.returncode, 0, second.stderr)
        events = json.loads(second.stdout)["changes"]
        self.assertIn({"kind": "new_model", "model": "model-b"}, events)
        self.assertIn({"kind": "higher_version", "model": "model-b", "family": "synthetic", "version": "2"}, events)
        policy = self.root / "policy.json"
        policy.write_text(json.dumps({"quality_weight": 1, "latency_weight": 0, "cost_weight": 0,
                                      "min_quality": .9}))
        ranked = self.cli("recommend", "--capability", "engineering", "--effort", "high",
                          "--policy-file", str(policy))
        self.assertEqual(ranked.returncode, 0, ranked.stderr)
        self.assertEqual([item["id"] for item in json.loads(ranked.stdout)["candidates"]], ["model-b"])
        repeated = self.cli("import", "--file", str(self.root / "snapshot.json"))
        self.assertEqual(json.loads(repeated.stdout)["changes"], [])
        removed = self.cli("remove", "--source", "host.synthetic")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(json.loads(removed.stdout), {"source": "host.synthetic", "removed": True})
        self.assertEqual(json.loads(self.cli("list").stdout)["sources"], {})
        self.assertEqual(json.loads(self.cli("remove", "--source", "host.synthetic").stdout)["removed"], False)

    def test_invalid_old_duplicate_secret_and_symlink_are_rejected(self):
        valid = self.snapshot([model("a", "1")])
        self.assertEqual(self.cli("import", "--file", self.input(valid)).returncode, 0)
        older = self.snapshot([model("b", "2")], "2026-09-22T00:00:00Z")
        self.assertNotEqual(self.cli("import", "--file", self.input(older)).returncode, 0)
        duplicate = self.snapshot([model("a", "1"), model("a", "2")])
        self.assertNotEqual(self.cli("import", "--file", self.input(duplicate)).returncode, 0)
        secret = self.snapshot([model("a", "1")])
        secret["models"][0]["metadata"]["api_key"] = "synthetic-secret-value"
        result = self.cli("import", "--file", self.input(secret))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("synthetic-secret-value", result.stderr)
        duplicate_json = self.root / "duplicate.json"
        duplicate_json.write_text('{"source":"a","source":"b","observed_at":"2026-09-23T12:00:00Z","models":[]}')
        self.assertNotEqual(self.cli("import", "--file", str(duplicate_json)).returncode, 0)
        link = self.root / "link.json"
        link.symlink_to(self.root / "snapshot.json")
        self.assertNotEqual(self.cli("import", "--file", str(link)).returncode, 0)
        directory_link = self.root / "linked-parent"
        directory_link.symlink_to(self.root, target_is_directory=True)
        self.assertNotEqual(self.cli("import", "--file", str(directory_link / "snapshot.json")).returncode, 0)
        target = self.home / ".config/hebe-brain/model-catalog.json"
        target.unlink()
        target.symlink_to(self.root / "outside.json")
        self.assertNotEqual(self.cli("list").returncode, 0)
        self.assertFalse((self.root / "outside.json").exists())

    def test_metric_bounds_and_version_validation(self):
        bad = model("a", "latest")
        with self.assertRaises(registry.RegistryError):
            registry.validate_snapshot(self.snapshot([bad]))
        bad = model("a", "1")
        bad["metadata"]["quality"] = 2
        with self.assertRaises(registry.RegistryError):
            registry.validate_snapshot(self.snapshot([bad]))
        with self.assertRaises(registry.RegistryError):
            registry.validate_policy({"cost_weight": -1})
        unknown = model("unmeasured", "1")
        unknown["metadata"] = {}
        catalog = {"sources": {"host.synthetic": self.snapshot([unknown])}}
        self.assertEqual(len(registry.recommend(["engineering"], catalog=catalog)["candidates"]), 1)
        self.assertEqual(registry.recommend(["engineering"], policy={"cost_weight": 1},
                                            catalog=catalog)["candidates"], [])

    def test_large_invalid_input_does_not_block_secret_scanning(self):
        path = self.root / "untrusted.json"
        path.write_text(json.dumps({"untrusted": "a" * 262144}))
        result = subprocess.run([sys.executable, str(SCRIPTS / "model_registry.py"),
                                 "import", "--file", str(path)], env=self.env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stderr))
        self.assertNotIn("Traceback", result.stderr)

    def test_deep_json_and_huge_numeric_metrics_fail_with_static_errors(self):
        for payload in (b"[" * 80 + b"0" + b"]" * 80, b"[1e999]"):
            with self.assertRaises(registry.RegistryError):
                registry.parse_json(payload)
        huge = 10 ** 1000
        with self.assertRaises(registry.RegistryError):
            registry.metadata({"latency_ms": huge})
        with self.assertRaises(registry.RegistryError):
            registry.validate_policy({"max_latency_ms": huge})

    def test_codex_model_list_normalization_uses_observed_slots_and_upgrade(self):
        response = {"data": [
            {"id": "future-code", "hidden": False, "isDefault": True,
             "inputModalities": ["text", "image"], "modelSpecialty": "software engineering",
             "multiAgentVersion": "v2",
             "supportedReasoningEfforts": [{"reasoningEffort": "high", "description": ""}],
             "upgradeInfo": {"model": "future-code-next"}, "unrecognizedFutureField": True},
            {"id": "hidden-model", "hidden": True, "supportedReasoningEfforts": []}
        ], "nextCursor": None}
        snapshot = registry.codex_snapshot(response, "2026-09-23T12:00:00Z", 7)
        self.assertEqual(snapshot["source"], "codex.app-server")
        self.assertEqual([item["id"] for item in snapshot["models"]], ["future-code"])
        item = snapshot["models"][0]
        self.assertEqual(item["max_parallel"], 7)
        self.assertEqual(item["upgrade_to"], "future-code-next")
        self.assertIn("specialty.software-engineering", item["capabilities"])


if __name__ == "__main__":
    unittest.main()
