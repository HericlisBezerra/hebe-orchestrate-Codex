"""DAG, limits, retries and scale for the planning-only scheduler."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import batch_scheduler as scheduler


def task(task_id, model="m", deps=(), **fields):
    return {"id": task_id, "model": model, "depends_on": list(deps), **fields}


def document(tasks, global_slots=2, models=None, retry=None):
    result = {"limits": {"source": "observed.session", "observed_at": "2026-09-23T12:00:00Z",
                         "global_slots": global_slots, "model_slots": models or {"m": 2}},
              "tasks": tasks}
    if retry is not None:
        result["retry_policy"] = retry
    return result


class SchedulerTests(unittest.TestCase):
    def test_deterministic_waves_respect_dependencies_and_limits(self):
        tasks = [task("z", deps=["a", "b"]), task("b"), task("a"), task("c", "n")]
        source = document(tasks, 2, {"m": 1, "n": 1})
        plan = scheduler.plan(source)
        self.assertEqual([[item["id"] for item in wave] for wave in plan["waves"]],
                         [["a", "c"], ["b"], ["z"]])
        source["tasks"].reverse()
        self.assertEqual(plan, scheduler.plan(source))
        self.assertEqual(plan["summary"]["planned"], 4)
        self.assertEqual(plan["execution"], "planning_only; replan after each observed wave")

    def test_failures_cancellation_retry_and_conditional_descendants(self):
        policy = {"max_attempts": 3, "retry_failed": True, "retry_cancelled": False}
        source = document([task("failed", status="failed", attempts=1),
                           task("child", deps=["failed"]),
                           task("cancelled", status="cancelled"),
                           task("blocked", deps=["cancelled"]), task("done", status="succeeded")], retry=policy)
        planned = scheduler.plan(source)
        self.assertEqual([[item["id"] for item in wave] for wave in planned["waves"]],
                         [["failed"], ["child"]])
        self.assertEqual(planned["waves"][0][0]["attempt"], 2)
        self.assertTrue(planned["waves"][1][0]["conditional"])
        self.assertEqual(planned["completed"], ["done"])
        self.assertEqual({item["id"] for item in planned["blocked"]}, {"cancelled", "blocked"})
        source["tasks"][0]["attempts"] = 3
        exhausted = scheduler.plan(source)
        self.assertEqual(exhausted["summary"]["blocked"], 4)

    def test_cycles_unknown_deps_invalid_limits_and_forbidden_fields(self):
        for source in (
            document([task("a", deps=["b"]), task("b", deps=["a"])]),
            document([task("a", deps=["missing"])]),
            document([task("a", command="echo unsafe")]),
            document([task("a", status=[])]),
            document([task("a", status={})]),
            document([task("a")], 1, {"m": 2}),
        ):
            with self.assertRaises(scheduler.ScheduleError):
                scheduler.plan(source)

    def test_registry_bound_prevents_model_oversubscription(self):
        source = document([task("a")], 2, {"m": 2})
        source["limits"]["registry_source"] = "host.synthetic"
        catalog = {"sources": {"host.synthetic": {"models": [{"id": "m", "max_parallel": 1}]}}}
        with self.assertRaises(scheduler.ScheduleError):
            scheduler.plan(source, catalog=catalog)
        source["limits"]["model_slots"]["m"] = 1
        self.assertEqual(scheduler.plan(source, catalog=catalog)["summary"]["planned"], 1)

    def test_thousands_of_tasks_are_complete_and_deterministic(self):
        tasks = [task(f"t{i:05d}", deps=[f"t{i-1:05d}"] if i % 25 else [])
                 for i in range(5000)]
        source = document(tasks, 8, {"m": 4})
        first = scheduler.plan(source)
        self.assertEqual(first["summary"]["planned"], 5000)
        self.assertEqual(len({item["id"] for wave in first["waves"] for item in wave}), 5000)
        self.assertTrue(all(len(wave) <= 4 for wave in first["waves"]))
        self.assertEqual(first, scheduler.plan(source))

    def test_many_models_with_one_global_slot(self):
        models = {f"m{i:04d}": 1 for i in range(1500)}
        tasks = [task(f"t{i:04d}", f"m{i:04d}") for i in range(1500)]
        planned = scheduler.plan(document(tasks, 1, models))
        self.assertEqual(planned["summary"]["waves"], 1500)
        self.assertEqual(planned["waves"][0][0]["id"], "t0000")
        self.assertEqual(planned["waves"][-1][0]["id"], "t1499")

    def test_cli_json_and_input_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve() / "plan.json"
            path.write_text(json.dumps(document([task("a")])))
            cmd = [sys.executable, str(SCRIPTS / "batch_scheduler.py"), "--file", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["waves"][0][0]["id"], "a")
            link = Path(root) / "link.json"
            link.symlink_to(path)
            cmd[-1] = str(link)
            rejected = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("error", json.loads(rejected.stderr))


if __name__ == "__main__":
    unittest.main()
