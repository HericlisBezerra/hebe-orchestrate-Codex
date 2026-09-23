"""Git/Brain integration with isolated repositories; no network or account use."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class GitEventsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Brain Test")
        self.git("config", "user.email", "brain@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.project = str(uuid.uuid4())

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, path, message):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(message, encoding="utf-8")
        self.git("add", "--", path)
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def collect(self, *args, path=None, project=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "git_events.py"), "--path", str(path or self.repo),
                               "--project", project or self.project, *args], capture_output=True, text=True, timeout=30)

    def test_empty_repository(self):
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_scopes_history_to_literal_subproject(self):
        backend_sha = self.commit("backend/api.py", "API pronta")
        frontend_sha = self.commit("frontend [web]/index.html", "Tela com acentuação")
        result = self.collect(path=self.repo / "frontend [web]")
        self.assertEqual(result.returncode, 0, result.stderr)
        events = json.loads(result.stdout)
        self.assertEqual([e["source_ref"] for e in events], [frontend_sha])
        self.assertNotIn(backend_sha, result.stdout)
        self.assertEqual(events[0]["payload"]["paths"], ["frontend [web]/index.html"])
        self.assertEqual(events[0]["kind"], "commit.created")

    def test_replay_into_brain_does_not_duplicate_commit(self):
        sha = self.commit("app.py", "Entrega local")
        home = self.root / "central"
        def brain(*args, data=None):
            result = subprocess.run([sys.executable, str(SCRIPTS / "brain.py"), "--home", str(home), *args],
                                    input=data, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        brain("init")
        project = brain("register", "--path", str(self.repo), "--name", "Produto")["project_id"]
        events = self.collect(project=project)
        self.assertEqual(events.returncode, 0, events.stderr)
        self.assertEqual(brain("record", data=events.stdout)["inserted"], 1)
        self.assertEqual(brain("record", data=events.stdout)["duplicates"], 1)
        brain("consolidate", "--project", project)
        commits = (self.repo / "vault/04-Engenharia/Commits.md").read_text()
        self.assertIn(sha, commits)
        self.assertIn("não confirma push", commits)
        self.assertEqual(brain("status")["events"], 1)

    def test_limit_and_validation(self):
        self.commit("first", "Primeiro")
        last = self.commit("second", "Segundo")
        result = self.collect("--limit", "1")
        self.assertEqual([e["source_ref"] for e in json.loads(result.stdout)], [last])
        self.assertEqual(self.collect("--limit", "501").returncode, 2)
        self.assertEqual(self.collect("--since", "yesterday").returncode, 2)
        self.assertEqual(self.collect(project="not-a-uuid").returncode, 2)

    def test_before_revision_paginates_scoped_history_without_duplicates(self):
        expected = [self.commit(f"backend/file-{index}.txt", f"Backend {index}") for index in range(5)]
        self.commit("frontend/other.txt", "Frontend")
        first = json.loads(self.collect("--limit", "2", path=self.repo / "backend").stdout)
        self.assertEqual([event["source_ref"] for event in first], expected[-2:])
        cursor = first[0]["source_ref"]
        second_result = self.collect("--limit", "2", "--before-revision", cursor, path=self.repo / "backend")
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        second = json.loads(second_result.stdout)
        self.assertEqual([event["source_ref"] for event in second], expected[1:3])
        third = json.loads(self.collect("--limit", "2", "--before-revision", second[0]["source_ref"],
                                       path=self.repo / "backend").stdout)
        self.assertEqual([event["source_ref"] for event in third], expected[:1])
        self.assertEqual(self.collect("--before-revision", "f" * 40, path=self.repo / "backend").returncode, 2)

    def test_secret_subject_is_not_printed(self):
        token = "ghp_" + "a" * 32
        self.commit("file", "Chave indevida " + token)
        result = self.collect()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
