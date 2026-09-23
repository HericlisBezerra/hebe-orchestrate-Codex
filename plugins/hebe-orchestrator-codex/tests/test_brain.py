"""Behavioral coverage for the local Brain; all state lives in temporary folders."""

import concurrent.futures
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "brain.py"
SPEC = importlib.util.spec_from_file_location("hebe_brain", SCRIPT)
brain_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(brain_module)
Brain = brain_module.Brain
BrainError = brain_module.BrainError


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "central"
        self.brain = Brain(self.home)
        self.brain.init()
        self.project = self.root / "Produto"
        self.project.mkdir()
        self.registered = self.brain.register(self.project, "Produto São Paulo")
        self.project_id = self.registered["project_id"]

    def event(self, event_id="evt:1", kind="note.recorded", project_id=None, **payload):
        return {"event_id": event_id, "project_id": project_id or self.project_id,
                "kind": kind, "occurred_at": "2026-09-23T10:00:00-03:00",
                "source": "manual", "source_ref": "conversa:exemplo",
                "payload": {"title": "Decisão de integração", "body": "Ação útil para São Paulo.", **payload}}

    def cli(self, *arguments, data=None, home=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--home", str(home or self.home), *arguments],
                              input=None if data is None else json.dumps(data, ensure_ascii=False),
                              text=True, capture_output=True, timeout=20)

    def test_status_and_list_never_create_missing_home(self):
        absent = self.root / "not-created"
        result = self.cli("status", home=absent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["initialized"])
        self.assertFalse(absent.exists())
        self.assertEqual(Brain(absent).list(), [])
        self.assertFalse(absent.exists())

    def test_empty_event_batch_is_a_noop_even_before_init(self):
        absent = self.root / "empty-batch"
        result = self.cli("record", home=absent, data=[])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"inserted": 0, "duplicates": 0, "event_ids": []})
        self.assertFalse(absent.exists())
        before = self.brain.status()
        self.assertEqual(self.brain.record([]), {"inserted": 0, "duplicates": 0, "event_ids": []})
        self.assertEqual(self.brain.status(), before)

    def test_init_preserves_ignore_rules_and_keeps_state_ignored(self):
        home = self.root / "existing-home"
        home.mkdir()
        original = "# Regras humanas\nnode_modules/\n/.state/\n!/.state/"
        ignore = home / ".gitignore"
        ignore.write_text(original, encoding="utf-8")
        Brain(home).init()
        updated = ignore.read_text()
        self.assertTrue(updated.startswith(original + "\n"))
        self.assertTrue(updated.endswith("/.state/\n"))
        Brain(home).init()
        self.assertEqual(ignore.read_text(), updated)

    def test_home_is_required_and_register_does_not_create_project(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        absent = self.root / "not-a-project"
        with self.assertRaises(BrainError):
            self.brain.register(absent, "Ausente")
        self.assertFalse(absent.exists())

    def test_registration_is_stable_and_nested_project_wins(self):
        repeated = self.brain.register(self.project, "Produto atualizado")
        self.assertEqual(repeated["project_id"], self.project_id)
        child = self.project / "apps" / "nested"
        child.mkdir(parents=True)
        nested = self.brain.register(child, "Produto filho")
        context = self.brain.context(child / "src")
        self.assertEqual(context["project"]["project_id"], nested["project_id"])
        self.assertEqual(context["parents"], [])  # A path ancestor is not automatically a logical parent.
        nested = self.brain.register(child, "Produto filho", self.project_id)
        context = self.brain.context(child / "src")
        self.assertEqual([p["project_id"] for p in context["parents"]], [self.project_id])
        self.assertEqual(self.brain.context(self.project)["project"]["project_id"], self.project_id)
        with self.assertRaises(BrainError):
            self.brain.register(self.project, "Ciclo", nested["project_id"])

    def test_names_and_git_metadata_do_not_merge_distinct_projects(self):
        other = self.root / "another" / "Produto"
        other.mkdir(parents=True)
        registered = self.brain.register(other, "Produto São Paulo")
        self.assertNotEqual(registered["project_id"], self.project_id)
        self.assertEqual(len(self.brain.list()), 2)
        self.assertEqual(self.brain.context(other)["project"]["project_id"], registered["project_id"])
        with self.assertRaises(BrainError):
            self.brain.context(self.root)

    def test_existing_prose_survives_registration_and_consolidation(self):
        existing = self.root / "Existing"
        decisions = existing / "vault" / "03-Decisoes" / "Registro-de-Decisoes.md"
        decisions.parent.mkdir(parents=True)
        original_brain = "# Meu cérebro\n\nContexto humano com acentuação.\n"
        original_decisions = "# Decisões históricas\n\n| 2026-01-01 | Algo decidido | Contexto |\n"
        (existing / "Brain.md").write_text(original_brain, encoding="utf-8")
        decisions.write_text(original_decisions, encoding="utf-8")
        project_id = self.brain.register(existing, "Existing")["project_id"]
        self.brain.record(self.event(kind="decision.accepted", project_id=project_id))
        self.brain.consolidate(project_id)
        self.assertTrue((existing / "Brain.md").read_text().startswith(original_brain))
        self.assertTrue(decisions.read_text().startswith(original_decisions))
        with decisions.open("a", encoding="utf-8") as stream:
            stream.write("\nAnotação manual depois da seção.\n")
        self.brain.consolidate(project_id)
        self.assertTrue(decisions.read_text().endswith("\nAnotação manual depois da seção.\n"))

    def test_adopts_existing_brain_index_without_new_entry(self):
        existing = self.root / "Legacy"
        index = existing / "brain" / "INDEX.md"
        index.parent.mkdir(parents=True)
        index.write_text("# Índice legado\n", encoding="utf-8")
        registered = self.brain.register(existing, "Legacy")
        self.assertEqual(registered["brain_path"], str(index))
        self.assertFalse((existing / "Brain.md").exists())
        self.assertFalse((existing / "vault").exists())
        self.assertTrue(index.read_text().startswith("# Índice legado\n"))

    def test_replay_and_repeat_consolidation_are_idempotent(self):
        event = self.event()
        self.assertEqual(self.brain.record(event)["inserted"], 1)
        self.assertEqual(self.brain.record(event)["duplicates"], 1)
        self.assertEqual(self.brain.status()["pending_events"], 1)
        self.brain.consolidate()
        files = list(self.project.rglob("*.md"))
        snapshots = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
        self.brain.consolidate()
        self.assertEqual(snapshots, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files})
        self.assertEqual(self.brain.status()["events"], 1)
        self.assertEqual(self.brain.status()["pending_events"], 0)
        self.assertEqual(len(list((self.project / "vault/98-HeBe-Events").glob("*.md"))), 1)
        with self.assertRaises(BrainError):
            self.brain.record(self.event(body="Conteúdo conflitante."))
        self.assertEqual(self.brain.status()["events"], 1)

    def test_proposals_and_implementation_never_become_accepted_decisions(self):
        self.brain.record([
            self.event("proposal", "decision.proposed", title="Ideia ainda em discussão"),
            self.event("implemented", "implementation.completed", title="Alteração implementada"),
            self.event("accepted", "decision.accepted", title="Escolha aprovada"),
            self.event("replacement", "decision.accepted", title="Nova escolha aprovada"),
            self.event("superseded", "decision.superseded", title="Escolha alterada", supersedes="accepted", replacement="replacement"),
        ])
        self.brain.consolidate()
        decisions = Path(self.registered["decisions_path"]).read_text()
        self.assertIn("Escolha aprovada", decisions)
        self.assertIn("substituída", decisions)
        self.assertIn("substituída por [Nova escolha aprovada]", decisions)
        self.assertNotIn("Ideia ainda em discussão", decisions)
        self.assertNotIn("Alteração implementada", decisions)
        self.assertNotIn("Escolha alterada", decisions)

    def test_superseding_another_projects_decision_is_rejected(self):
        second = self.root / "second"
        second.mkdir()
        other_id = self.brain.register(second, "Outro")["project_id"]
        self.brain.record(self.event("accepted", "decision.accepted"))
        self.brain.record(self.event("replacement", "decision.accepted", title="Nova decisão"))
        with self.assertRaises(BrainError):
            self.brain.record(self.event("superseded", "decision.superseded", project_id=other_id,
                                         supersedes="accepted", replacement="replacement"))
        self.assertEqual(self.brain.status()["events"], 2)

    def test_replacement_must_be_preexisting_accepted_decision(self):
        self.brain.record(self.event("old", "decision.accepted"))
        missing = self.event("superseded", "decision.superseded", supersedes="old", replacement="new")
        with self.assertRaises(BrainError):
            self.brain.record([self.event("new", "decision.proposed"), missing])
        self.assertEqual(self.brain.status()["events"], 1)
        with self.assertRaises(BrainError):
            self.brain.record(self.event("same", "decision.superseded", supersedes="old", replacement="old"))
        self.brain.record(self.event("new", "decision.accepted", title="Substituta"))
        self.assertEqual(self.brain.record(missing)["inserted"], 1)
        self.assertEqual(self.brain.record(missing)["duplicates"], 1)
        with self.assertRaises(BrainError):
            self.brain.record(self.event("again", "decision.superseded", supersedes="old", replacement="new"))
        with self.assertRaises(BrainError):
            self.brain.record(self.event("cycle", "decision.superseded", supersedes="new", replacement="old"))

    def test_legacy_supersession_is_preserved_without_inventing_replacement(self):
        self.brain.record([
            self.event("old", "decision.accepted", title="Decisão histórica"),
            self.event("new", "decision.accepted", title="Possível decisão nova"),
            self.event("superseded", "decision.superseded", supersedes="old", replacement="new"),
        ])
        with self.brain.connection() as conn:
            payload = json.loads(conn.execute("SELECT payload_json FROM events WHERE event_id='superseded'").fetchone()[0])
            payload.pop("replacement")
            conn.execute("UPDATE events SET payload_json=? WHERE event_id='superseded'", (json.dumps(payload),))
        self.brain.consolidate()
        decisions = Path(self.registered["decisions_path"]).read_text()
        self.assertIn("substituição legada sem decisão vigente vinculada", decisions)
        self.assertNotIn("substituída por [Possível decisão nova]", decisions)

        repaired = self.event("superseded-repair", "decision.superseded",
                              supersedes="old", replacement="new")
        self.brain.record(repaired)
        self.brain.consolidate(self.project_id)
        decisions = Path(self.registered["decisions_path"]).read_text()
        self.assertIn("substituída por [Possível decisão nova]", decisions)

    def test_push_and_publication_have_distinct_evidence_and_history(self):
        with self.assertRaises(BrainError):
            self.brain.record(self.event("bad-push", "push.completed", remote="origin"))
        with self.assertRaises(BrainError):
            self.brain.record(self.event("bad-publication", "publication.completed",
                                         url="file:///tmp/result", revision="abc123"))
        pushed = self.event("push:1", "push.completed", remote="origin/main", revision="abc123")
        pushed["source"] = "grok"
        published = self.event("publish:1", "publication.completed", url="https://example.invalid/app", revision="abc123")
        self.brain.record([pushed, published])
        self.brain.consolidate()
        history = (self.project / "vault/04-Engenharia/Entregas.md").read_text()
        self.assertIn("origin/main", history)
        self.assertIn("https://example.invalid/app", history)
        self.assertIn("push.completed", history)
        self.assertIn("publication.completed", history)
        self.assertFalse((self.project / "vault/04-Engenharia/Commits.md").exists())

    def test_batches_rollback_on_unknown_project_and_invalid_payload(self):
        with self.assertRaises(BrainError):
            self.brain.record([self.event("first"), self.event("second", project_id=str(uuid.uuid4()))])
        self.assertEqual(self.brain.status()["events"], 0)
        with self.assertRaises(BrainError):
            self.brain.record([self.event("first"), self.event("second", body="" , title="")])
        self.assertEqual(self.brain.status()["events"], 0)

    def test_utf8_search_context_and_cli_stdin_list(self):
        result = self.cli("record", "--file", "-", data=[self.event("utf8")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["inserted"], 1)
        result = self.cli("search", "AÇÃO", "--project", self.project_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["event_id"], "utf8")
        result = self.cli("context", "--path", str(self.project))
        self.assertEqual(json.loads(result.stdout)["project"]["name"], "Produto São Paulo")
        self.assertEqual(json.loads(result.stdout)["recent_events"][0]["source_ref"], "conversa:exemplo")

    def test_commits_are_local_with_provenance(self):
        event = self.event("git:1", "commit.created", title="Implementar busca", sha="abc123", paths=["src/search.py"])
        event.update(source="git", source_ref="abc123")
        self.brain.record(event)
        self.brain.consolidate()
        text = (self.project / "vault/04-Engenharia/Commits.md").read_text()
        self.assertIn("abc123", text)
        self.assertIn("não confirma push", text)
        note = next((self.project / "vault/98-HeBe-Events").glob("*.md")).read_text()
        self.assertIn("src/search.py", note)
        self.assertIn("Origem: `git`", note)

    def test_traversal_and_symlinks_are_rejected_before_writes(self):
        for relative in ("../escape.md", "/tmp/escape.md"):
            with self.subTest(relative=relative), self.assertRaises(BrainError):
                brain_module.safe_path(self.project, relative)
        outside = self.root / "outside"
        outside.mkdir()
        malicious = self.root / "malicious"
        malicious.mkdir()
        (malicious / "vault").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BrainError):
            self.brain.register(malicious, "Malicious")
        self.assertEqual(list(outside.iterdir()), [])
        self.brain.record(self.event())
        (self.project / "vault/98-HeBe-Events").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BrainError):
            self.brain.consolidate()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.brain.status()["pending_events"], 1)

    def test_brain_file_and_state_symlinks_are_rejected(self):
        outside = self.root / "outside.md"
        outside.write_text("Intocado", encoding="utf-8")
        malicious = self.root / "linked-brain"
        malicious.mkdir()
        (malicious / "Brain.md").symlink_to(outside)
        with self.assertRaises(BrainError):
            self.brain.register(malicious, "Linked")
        self.assertEqual(outside.read_text(), "Intocado")
        home = self.root / "linked-state"
        home.mkdir()
        (home / ".state").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(BrainError):
            Brain(home).init()
        journal = self.home / ".state/brain.sqlite3-journal"
        journal.symlink_to(outside)
        with self.assertRaises(BrainError):
            self.brain.record(self.event())
        self.assertEqual(outside.read_text(), "Intocado")

    def test_replaced_project_ancestor_cannot_redirect_consolidation(self):
        workspace = self.root / "workspace"
        backend = workspace / "backend"
        backend.mkdir(parents=True)
        project_id = self.brain.register(backend, "Backend")["project_id"]
        self.brain.record(self.event("ancestor", project_id=project_id))
        moved = self.root / "original-workspace"
        workspace.rename(moved)
        outside = self.root / "outside-workspace"
        (outside / "backend").mkdir(parents=True)
        workspace.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BrainError):
            self.brain.consolidate(project_id)
        with self.assertRaises(BrainError):
            self.brain.context(project_id=project_id)
        self.assertEqual(list((outside / "backend").iterdir()), [])
        self.assertEqual(self.brain.status()["pending_events"], 1)
        self.assertFalse((moved / "backend/vault/98-HeBe-Events").exists())

    def test_failed_registration_keeps_identity_until_markers_are_repaired(self):
        central = self.home / "Brain.md"
        original = central.read_text()
        central.write_text(original.replace("<!-- hebe-brain:projects:end -->", ""))
        new_project = self.root / "registration-retry"
        new_project.mkdir()
        with self.assertRaises(BrainError):
            self.brain.register(new_project, "Retry")
        registered = next(p for p in self.brain.list() if p["path"] == str(new_project))
        project_id = registered["project_id"]
        self.assertIn(project_id, (new_project / "Brain.md").read_text())
        self.assertEqual(self.brain.status()["pending_materializations"], 1)
        central.write_text(original)
        retried = self.brain.register(new_project, "Retry")
        self.assertEqual(retried["project_id"], project_id)
        self.assertEqual(self.brain.status()["pending_materializations"], 0)
        self.assertEqual((new_project / "Brain.md").read_text().count(project_id), 1)

    def test_registration_survives_late_io_failure_and_consolidate_recovers(self):
        new_project = self.root / "io-retry"
        new_project.mkdir()
        real_write = brain_module.atomic_write

        def fail_central_index(root, relative, content):
            if root == self.home and relative == "vault/00-Indice.md":
                raise OSError("Simulated local write failure")
            return real_write(root, relative, content)

        with mock.patch.object(brain_module, "atomic_write", side_effect=fail_central_index):
            with self.assertRaises(OSError):
                self.brain.register(new_project, "IO Retry")
        registered = next(p for p in self.brain.list() if p["path"] == str(new_project))
        project_id = registered["project_id"]
        self.assertIn(project_id, (new_project / "Brain.md").read_text())
        self.assertEqual(self.brain.status()["pending_materializations"], 1)
        self.brain.consolidate(project_id)
        self.assertEqual(self.brain.status()["pending_materializations"], 0)
        self.assertEqual(next(p for p in self.brain.list() if p["path"] == str(new_project))["project_id"], project_id)

    def test_rejects_secrets_without_echo_or_storage(self):
        secret = "sk-ant-" + "aB91" * 12
        event = self.event(body="Chave: " + secret)
        result = self.cli("record", data=event)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertIn("conteúdo omitido", result.stderr)
        self.assertNotIn(secret.encode(), (self.home / ".state/brain.sqlite3").read_bytes())
        self.assertEqual(self.brain.status()["events"], 0)
        for body in ("PASSWORD=supersecret123", "-----BEGIN PRIVATE KEY-----", "https://user:pass@example.com"):
            with self.subTest(body=body), self.assertRaises(BrainError):
                self.brain.record(self.event(body=body))
        with self.assertRaises(BrainError):
            self.brain.record(self.event(api_key="plain-credential-value"))

    def test_reserved_markers_malformed_timestamps_and_duplicate_keys(self):
        with self.assertRaises(BrainError):
            self.brain.record(self.event(extra="<!-- hebe-brain:event:end -->"))
        event = self.event()
        event["occurred_at"] = "2026-09-23"
        with self.assertRaises(BrainError):
            self.brain.record(event)
        with self.assertRaises(BrainError):
            brain_module.no_duplicate_keys([("event_id", "one"), ("event_id", "two")])

    def test_interrupted_document_updates_replay_without_duplicate_notes(self):
        self.brain.record(self.event())
        decisions = Path(self.registered["decisions_path"])
        original = decisions.read_text()
        decisions.write_text(original.replace("<!-- hebe-brain:decisions:end -->", ""))
        with self.assertRaises(BrainError):
            self.brain.consolidate()
        self.assertEqual(self.brain.status()["pending_events"], 1)
        decisions.write_text(original)
        self.brain.consolidate()
        self.assertEqual(self.brain.status()["pending_events"], 0)
        self.assertEqual(len(list((self.project / "vault/98-HeBe-Events").glob("*.md"))), 1)

    def test_parallel_processes_serialize_record_and_consolidate(self):
        def record(number):
            return self.cli("record", data=self.event("parallel:" + str(number % 4)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(record, range(8)))
        self.assertTrue(all(result.returncode == 0 for result in outcomes), [r.stderr for r in outcomes])
        self.assertEqual(sum(json.loads(r.stdout)["inserted"] for r in outcomes), 4)
        self.assertEqual(sum(json.loads(r.stdout)["duplicates"] for r in outcomes), 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: self.cli("consolidate"), range(2)))
        self.assertTrue(all(result.returncode == 0 for result in outcomes), [r.stderr for r in outcomes])
        self.assertEqual(self.brain.status()["events"], 4)
        self.assertEqual(self.brain.status()["pending_events"], 0)
        self.assertEqual(len(list((self.project / "vault/98-HeBe-Events").glob("*.md"))), 4)
        with sqlite3.connect(self.home / ".state/brain.sqlite3") as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
