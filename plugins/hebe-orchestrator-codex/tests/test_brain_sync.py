"""Backup/recovery against temporary Brain stores and local bare Git remotes.

No real repository, credentials, network, scheduler or user configuration is used.
"""

import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import brain_sync as backup
from brain import Brain
from orchestrator import Orchestrator


class BrainSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "central"
        self.project = self.root / "project"
        self.project.mkdir()
        self.brain = Brain(self.home)
        self.brain.init()
        self.project_id = self.brain.register(self.project, "Produto com acentuação")["project_id"]
        self.note = self.project / "vault/Nota.md"
        self.note.write_text("# Conhecimento\n\nDecisão e evidência preservadas.\n", encoding="utf-8")
        self.repo = self.root / "checkout"
        self.repo.mkdir()
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Brain Test")
        self.git("config", "user.email", "brain@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.remote = self.root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(self.remote)], check=True, capture_output=True)
        self.git("remote", "add", "origin", str(self.remote))
        self.config = self.root / "private/sync.json"
        backup.configure(self.config, self.home, self.repo)

    def git(self, *args, cwd=None):
        result = subprocess.run(["git", "-C", str(cwd or self.repo), *args], check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "brain_sync.py"), "--config", str(self.config), *args],
                              capture_output=True, text=True, timeout=30)

    def snapshot(self):
        return Path(backup.export(self.config)["path"])

    def event(self):
        return {"event_id": "sync:fixture", "project_id": self.project_id, "kind": "decision.accepted",
                "occurred_at": "2026-09-23T10:00:00-03:00", "source": "manual", "source_ref": "test:local",
                "payload": {"title": "Decisão aceita", "body": "Persistir apenas o conhecimento autorizado."}}

    def test_configuration_is_private_and_status_is_read_only(self):
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.config.parent.stat().st_mode), 0o700)
        result = backup.status(self.config)
        self.assertTrue(result["configured"])
        self.assertIsNone(result["last_run"])
        absent = self.root / "absent/config.json"
        self.assertFalse(backup.status(absent)["configured"])
        self.assertFalse(absent.parent.exists())
        self.config.chmod(0o644)
        with self.assertRaises(backup.SyncError):
            backup.load_config(self.config)

    def test_configuration_rejects_credentials_symlinks_and_non_dedicated_checkout(self):
        raw = json.loads(self.config.read_text())
        raw["token"] = "synthetic-value"
        self.config.write_text(json.dumps(raw))
        with self.assertRaises(backup.SyncError):
            backup.load_config(self.config)
        self.config.unlink()
        outside = self.root / "outside"
        outside.write_text("preserve")
        self.config.symlink_to(outside)
        with self.assertRaises(backup.SyncError):
            backup.configure(self.config, self.home, self.repo)
        self.assertEqual(outside.read_text(), "preserve")
        self.config.unlink()
        self.git("remote", "set-url", "origin", "https://user:synthetic-password@example.invalid/brain.git")
        outcome = self.cli("configure", "--brain-home", str(self.home), "--checkout", str(self.repo))
        self.assertEqual(outcome.returncode, 2)
        self.assertNotIn("synthetic-password", outcome.stdout + outcome.stderr)
        self.assertFalse(self.config.exists())
        self.git("remote", "set-url", "origin", str(self.remote))
        (self.repo / "unrelated.txt").write_text("keep")
        with self.assertRaises(backup.SyncError):
            backup.configure(self.config, self.home, self.repo)

    def test_checkout_must_be_outside_central_and_every_registered_project(self):
        nested = self.project / "backup"
        nested.mkdir()
        self.git("init", "-q", "--initial-branch=main", cwd=nested)
        self.git("remote", "add", "origin", str(self.remote), cwd=nested)
        with self.assertRaises(backup.SyncError):
            backup.configure(self.root / "other-config.json", self.home, nested)
        self.assertFalse((self.root / "other-config.json").exists())

    def test_network_destination_needs_privacy_confirmation_bound_to_its_url(self):
        self.git("remote", "set-url", "origin", "https://example.invalid/private-brain.git")
        before = self.config.read_bytes()
        with self.assertRaises(backup.SyncError):
            backup.configure(self.config, self.home, self.repo)
        self.assertEqual(self.config.read_bytes(), before)
        configured = backup.configure(self.config, self.home, self.repo, confirm_private=True)
        self.assertTrue(configured["private_destination_confirmed_by_user"])
        self.assertFalse(configured["privacy_verified_by_cli"])
        self.assertEqual(backup.status(self.config)["destination_kind"], "remote")
        self.git("remote", "set-url", "origin", "https://example.invalid/another-brain.git")
        with self.assertRaises(backup.SyncError):
            backup.export(self.config)
        self.assertFalse((self.repo / "CURRENT.json").exists())
        self.git("remote", "set-url", "origin", self.remote.as_uri())
        local = backup.configure(self.config, self.home, self.repo)
        self.assertEqual(local["destination_kind"], "local")
        self.assertFalse(local["private_destination_confirmed_by_user"])

    def test_push_rechecks_destination_after_export(self):
        redirected = self.root / "redirected.git"
        self.git("init", "-q", "--bare", "--initial-branch=main", str(redirected))
        original_export = backup._export
        def swapped(config):
            result = original_export(config)
            self.git("remote", "set-url", "origin", str(redirected))
            return result
        with mock.patch.object(backup, "_export", side_effect=swapped):
            with self.assertRaisesRegex(backup.SyncError, "Destino Git mudou"):
                backup.sync(self.config)
        self.assertNotEqual(backup.git(redirected, "rev-parse", "--verify", "HEAD", check=False).returncode, 0)
        state = backup.status(self.config)["last_run"]
        self.assertEqual(state["failed_phase"], "push")
        self.assertIsNone(state["pushed_commit"])

    def test_chained_git_rewrite_cannot_change_the_resolved_push_destination(self):
        redirected = self.root / "redirected.git"
        self.git("init", "-q", "--bare", "--initial-branch=main", str(redirected))
        alias = str(self.root / "local-alias")
        self.git("remote", "set-url", "origin", alias)
        self.git("config", "url." + str(self.remote) + ".insteadOf", alias)
        self.git("config", "url." + str(redirected) + ".insteadOf", str(self.remote))
        # get-url expands only the first rule; pushing that output would expand
        # it a second time and reach a repository that was never confirmed.
        self.assertEqual(backup.remote_url(self.repo, "origin"), str(self.remote))
        backup.configure(self.config, self.home, self.repo)
        with self.assertRaisesRegex(backup.SyncError, "Reescritas Git encadeadas"):
            backup.sync(self.config)
        self.assertNotEqual(backup.git(redirected, "rev-parse", "--verify", "HEAD", check=False).returncode, 0)
        self.assertFalse((self.repo / "CURRENT.json").exists())

    def test_database_reader_uses_safe_copy_after_source_is_replaced_by_symlink(self):
        foreign = self.root / "foreign"
        Brain(foreign).init()
        source = self.home / ".state/brain.sqlite3"
        original_connect = backup.sqlite3.connect
        def swapped(path, *args, **kwargs):
            source.rename(source.with_suffix(".saved"))
            source.symlink_to(foreign / ".state/brain.sqlite3")
            return original_connect(path, *args, **kwargs)
        with mock.patch.object(backup.sqlite3, "connect", side_effect=swapped):
            result = backup.database_export(source, "brain")
        self.assertEqual([row["project_id"] for row in result["tables"]["projects"]], [self.project_id])

    def test_database_copy_rejects_hardlinks_and_oversized_state_before_sqlite(self):
        source = self.home / ".state/brain.sqlite3"
        linked = self.root / "linked.sqlite3"
        os.link(source, linked)
        with mock.patch.object(backup.sqlite3, "connect", side_effect=AssertionError("unsafe open")):
            with self.assertRaises(backup.SyncError):
                backup.database_export(source, "brain")
        linked.unlink()
        with mock.patch.object(backup, "MAX_TOTAL", 1), \
                mock.patch.object(backup.sqlite3, "connect", side_effect=AssertionError("oversized open")):
            with self.assertRaisesRegex(backup.SyncError, "limite"):
                backup.database_export(source, "brain")

    def test_database_copy_preserves_committed_wal_records(self):
        source = self.home / ".state/brain.sqlite3"
        connection = sqlite3.connect(source)
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("UPDATE projects SET name=? WHERE project_id=?", ("Committed in WAL", self.project_id))
        connection.commit()
        self.assertTrue(Path(str(source) + "-wal").exists())
        result = backup.database_export(source, "brain")
        self.assertEqual(result["tables"]["projects"][0]["name"], "Committed in WAL")

    def test_secret_scan_is_bounded_for_long_unbroken_input(self):
        command = [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                   "import brain_sync; brain_sync.secret_check('a' * 262144)", str(SCRIPTS)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaisesRegex(backup.SyncError, "segredo"):
            backup.secret_check("https://user:synthetic-private-password@example.invalid/")

    def test_deterministic_export_and_explicit_document_scope(self):
        (self.project / ".env").write_text("not exported")
        (self.project / "vault/.env").write_text("not exported")
        (self.project / "vault/credentials.md").write_text("not exported")
        (self.project / "vault/runner.py").write_text("not exported")
        (self.project / "vault/.git").mkdir()
        (self.project / "vault/.git/config").write_text("not exported")
        (self.project / "vault/image.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        first = backup.export(self.config)
        pointer = (self.repo / "CURRENT.json").stat().st_mtime_ns
        second = backup.export(self.config)
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertFalse(second["changed"])
        self.assertEqual(pointer, (self.repo / "CURRENT.json").stat().st_mtime_ns)
        self.assertEqual(len(list((self.repo / "snapshots").iterdir())), 1)
        manifest = json.loads((Path(first["path"]) / "manifest.json").read_text())
        paths = [item["path"] for item in manifest["files"]]
        self.assertIn(f"projects/{self.project_id}/vault/image.png", paths)
        self.assertFalse(any(p.endswith((".env", "credentials.md", "runner.py", ".git/config")) for p in paths))
        self.assertGreaterEqual(first["excluded_entries"], 4)
        self.assertTrue(backup.verify(self.repo)["verified"])

    def test_roundtrip_restores_registry_events_delivery_and_documents(self):
        legacy = self.root / "legacy"
        (legacy / "brain").mkdir(parents=True)
        (legacy / "brain/INDEX.md").write_text("# Legado\n")
        child = self.brain.register(legacy, "Filho", self.project_id)["project_id"]
        self.brain.record(self.event())
        self.brain.consolidate()
        runtime = Orchestrator(self.home)
        delivery = runtime.start(self.project_id, "Restaurar o Brain", ["roundtrip=Conhecimento recuperável"])["delivery"]
        runtime.checkpoint(delivery["delivery_id"], summary="Fixture criada")
        snapshot = self.snapshot()
        restored = self.root / "restored"
        plan = backup.restore(snapshot, restored)
        self.assertTrue(plan["dry_run"])
        self.assertFalse(restored.exists())
        result = backup.restore(snapshot, restored, apply=True)
        self.assertTrue(result["applied"])
        recovered = Brain(restored / "central")
        projects = {p["project_id"]: p for p in recovered.list()}
        self.assertEqual(projects[child]["parent_id"], self.project_id)
        self.assertEqual(projects[self.project_id]["path"], str(restored / "projects" / self.project_id))
        self.assertEqual(recovered.status()["events"], self.brain.status()["events"])
        self.assertEqual((restored / "projects" / self.project_id / "vault/Nota.md").read_bytes(), self.note.read_bytes())
        old = runtime.status(delivery=delivery["delivery_id"])
        new = Orchestrator(restored / "central").status(delivery=delivery["delivery_id"])
        self.assertEqual(new, old)
        self.assertIn("../projects/" + self.project_id, (restored / "central/Brain.md").read_text())
        self.assertIn("/.state/", (restored / "central/.gitignore").read_text())
        self.assertEqual(backup.restore(snapshot, restored)["conflicts"], [])
        repeated = backup.restore(snapshot, restored, apply=True)
        self.assertEqual(repeated["create"], [])

    def test_restore_preserves_extras_and_conflicts_without_mutation(self):
        snapshot = self.snapshot()
        destination = self.root / "restored"
        destination.mkdir()
        extra = destination / "keep.txt"
        extra.write_text("human file")
        result = backup.restore(snapshot, destination, apply=True)
        self.assertEqual(result["extras_preserved"], ["keep.txt"])
        self.assertEqual(extra.read_text(), "human file")
        note = destination / "projects" / self.project_id / "vault/Nota.md"
        note.write_text("new human knowledge")
        plan = backup.restore(snapshot, destination)
        self.assertIn(f"projects/{self.project_id}/vault/Nota.md", plan["conflicts"])
        with self.assertRaises(backup.SyncError):
            backup.restore(snapshot, destination, apply=True)
        self.assertEqual(note.read_text(), "new human knowledge")
        self.assertEqual(extra.read_text(), "human file")

    def test_corruption_and_unlisted_files_fail_verification_and_restore(self):
        snapshot = self.snapshot()
        note = snapshot / "projects" / self.project_id / "vault/Nota.md"
        note.write_text("corrupted")
        with self.assertRaises(backup.SyncError):
            backup.verify(snapshot)
        with self.assertRaises(backup.SyncError):
            backup.restore(snapshot, self.root / "restored", apply=True)
        self.assertFalse((self.root / "restored").exists())
        note.write_bytes(self.note.read_bytes())
        (snapshot / "extra.txt").write_text("undeclared")
        with self.assertRaises(backup.SyncError):
            backup.verify(snapshot)

    def test_state_layout_cannot_redirect_future_runtime_writes(self):
        original = self.snapshot()
        modified = self.root / "malicious-state"
        shutil.copytree(original, modified)
        state_file = modified / "state/brain.json"
        state = json.loads(state_file.read_text())
        state["tables"]["projects"][0]["index_rel"] = ".git/config"
        encoded = backup.canonical(state)
        state_file.write_bytes(encoded)
        manifest_file = modified / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        for item in manifest["files"]:
            if item["path"] == "state/brain.json":
                item.update(bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())
        manifest_file.write_bytes(backup.canonical(manifest))
        with self.assertRaises(backup.SyncError):
            backup.restore(modified, self.root / "restored", apply=True)
        self.assertFalse((self.root / "restored").exists())
    def test_manifest_traversal_and_rehashed_out_of_scope_file_are_rejected(self):
        source = self.snapshot()
        modified = self.root / "malicious"
        shutil.copytree(source, modified)
        manifest = json.loads((modified / "manifest.json").read_text())
        manifest["files"][0]["path"] = "../escaped.md"
        (modified / "manifest.json").write_bytes(backup.canonical(manifest))
        with self.assertRaises(backup.SyncError):
            backup.restore(modified, self.root / "restored", apply=True)
        manifest = json.loads((source / "manifest.json").read_text())
        injected = f"projects/{self.project_id}/.git/config"
        target = modified / injected
        target.parent.mkdir(parents=True)
        target.write_bytes(b"injected")
        manifest["files"].append({"path": injected, "bytes": 8, "sha256": hashlib.sha256(b"injected").hexdigest()})
        (modified / "manifest.json").write_bytes(backup.canonical(manifest))
        with self.assertRaises(backup.SyncError):
            backup.restore(modified, self.root / "restored", apply=True)
        self.assertFalse((self.root / "escaped.md").exists())
        self.assertFalse((self.root / "restored").exists())

    def test_symlinks_at_source_snapshot_destination_and_config_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "note.md").write_text("outside")
        link = self.project / "vault/link.md"
        link.symlink_to(outside / "note.md")
        with self.assertRaises(backup.SyncError):
            backup.export(self.config)
        link.unlink()
        snapshot = self.snapshot()
        original = snapshot / "projects" / self.project_id / "vault/Nota.md"
        original.unlink()
        original.symlink_to(self.note)
        with self.assertRaises(backup.SyncError):
            backup.verify(snapshot)
        original.unlink()
        original.write_bytes(self.note.read_bytes())
        destination = self.root / "restored"
        destination.mkdir()
        (destination / "central").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(backup.SyncError):
            backup.restore(snapshot, destination, apply=True)
        self.assertEqual(list(outside.iterdir()), [outside / "note.md"])
        self.config.unlink()
        self.config.symlink_to(outside / "note.md")
        with self.assertRaises(backup.SyncError):
            backup.load_config(self.config)

    def test_failed_export_keeps_previous_current_pointer(self):
        previous = backup.export(self.config)
        pointer = (self.repo / "CURRENT.json").read_bytes()
        synthetic = "ghp_" + "a" * 32
        self.note.write_text("Forbidden example " + synthetic)
        result = self.cli("export")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(synthetic, result.stdout + result.stderr)
        self.assertEqual((self.repo / "CURRENT.json").read_bytes(), pointer)
        self.assertEqual(backup.verify(self.repo)["snapshot"], previous["snapshot"])
        self.assertEqual(list((self.repo / ".git").glob("hebe-snapshot-*")), [])

    def test_unknown_database_schema_refuses_incomplete_backup(self):
        with sqlite3.connect(self.home / ".state/brain.sqlite3") as conn:
            conn.execute("CREATE TABLE future_state (important TEXT)")
        with self.assertRaises(backup.SyncError):
            backup.export(self.config)
        self.assertFalse((self.repo / "CURRENT.json").exists())

    def test_sync_pushes_only_changed_snapshot_and_noop_reuses_commit(self):
        first = backup.sync(self.config)
        self.assertTrue(first["committed"])
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.remote), first["pushed_commit"])
        second = backup.sync(self.config)
        self.assertFalse(second["committed"])
        self.assertEqual(first["local_commit"], second["local_commit"])
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")
        self.note.write_text("# Updated knowledge\n")
        reviewed = backup.export(self.config)
        third = backup.sync(self.config)
        self.assertEqual(third["snapshot"], reviewed["snapshot"])
        self.assertNotEqual(first["local_commit"], third["local_commit"])
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "2")
        state = backup.status(self.config)["last_run"]
        self.assertEqual(state["phase"], "complete")
        self.assertEqual(state["local_commit"], state["pushed_commit"])

    def test_sync_preserves_verified_bytes_with_autocrlf_enabled(self):
        self.note.write_bytes(b"# CRLF knowledge\r\nEvidence\r\n")
        self.git("config", "core.autocrlf", "true")
        result = backup.sync(self.config)
        rel = "snapshots/" + result["snapshot"] + "/projects/" + self.project_id + "/vault/Nota.md"
        committed = backup.git(self.repo, "show", result["pushed_commit"] + ":" + rel).stdout
        self.assertEqual(committed, self.note.read_bytes())

    def test_sync_rejects_inherited_snapshot_attributes(self):
        (self.repo / "snapshots").mkdir()
        (self.repo / "snapshots/.gitattributes").write_text("* text\n")
        with self.assertRaisesRegex(backup.SyncError, "gitattributes"):
            backup.sync(self.config)
        self.assertNotEqual(backup.git(self.repo, "rev-parse", "--verify", "HEAD", check=False).returncode, 0)

    def test_changes_after_export_are_not_committed(self):
        original_export = backup._export
        def changed(config):
            result = original_export(config)
            altered = Path(result["path"]) / "projects" / self.project_id / "vault/Nota.md"
            altered.write_text("unverified content\n")
            return result
        with mock.patch.object(backup, "_export", side_effect=changed):
            with self.assertRaisesRegex(backup.SyncError, "corrompido"):
                backup.sync(self.config)
        self.assertNotEqual(backup.git(self.repo, "rev-parse", "--verify", "HEAD", check=False).returncode, 0)
        self.assertNotEqual(backup.git(self.remote, "rev-parse", "--verify", "HEAD", check=False).returncode, 0)

    def test_push_uses_verified_revision_when_head_changes_concurrently(self):
        original_git = backup.git
        def changed(checkout, *args, **kwargs):
            if args and args[0] == "push":
                extra = self.repo / "snapshots/unverified.txt"
                extra.write_text("concurrent unreviewed content\n")
                self.git("add", "--", str(extra))
                self.git("commit", "-qm", "concurrent local change")
            return original_git(checkout, *args, **kwargs)
        with mock.patch.object(backup, "git", side_effect=changed):
            result = backup.sync(self.config)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.remote), result["pushed_commit"])
        self.assertNotEqual(self.git("rev-parse", "HEAD"), result["pushed_commit"])
        self.assertEqual(self.git("ls-tree", "-r", "--name-only", result["pushed_commit"], "--", "snapshots/unverified.txt"), "")

    def test_failed_push_reports_local_commit_and_retry_does_not_duplicate_it(self):
        hook = self.remote / "hooks/pre-receive"
        synthetic = "ghp_" + "b" * 32
        hook.write_text("#!/bin/sh\nprintf '%s\\n' '" + synthetic + "' >&2\nexit 1\n")
        hook.chmod(0o700)
        result = self.cli("sync")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(synthetic, result.stdout + result.stderr)
        state = backup.status(self.config)["last_run"]
        self.assertEqual(state["phase"], "failed")
        self.assertEqual(state["failed_phase"], "push")
        self.assertEqual(state["local_commit"], self.git("rev-parse", "HEAD"))
        self.assertIsNone(state["pushed_commit"])
        self.assertNotIn(synthetic, backup.status_path(self.config).read_text())
        hook.unlink()
        result = backup.sync(self.config)
        self.assertFalse(result["committed"])
        self.assertEqual(result["pushed_commit"], state["local_commit"])
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")

    def test_diverging_remote_is_never_force_pushed_or_merged(self):
        initial = backup.sync(self.config)
        peer = self.root / "peer"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(peer)], check=True, capture_output=True)
        self.git("config", "user.name", "Other", cwd=peer)
        self.git("config", "user.email", "other@example.invalid", cwd=peer)
        (peer / "remote-note.txt").write_text("remote change")
        self.git("add", "--", "remote-note.txt", cwd=peer)
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "remote change", cwd=peer)
        self.git("push", "-q", "origin", "main", cwd=peer)
        remote_revision = self.git("rev-parse", "HEAD", cwd=self.remote)
        self.note.write_text("Independent local change\n")
        with self.assertRaises(backup.SyncError):
            backup.sync(self.config)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.remote), remote_revision)
        self.assertEqual(self.git("rev-parse", "HEAD^"), initial["local_commit"])
        self.assertIsNone(backup.status(self.config)["last_run"]["pushed_commit"])

    def test_lock_rejects_overlapping_operations_and_preserves_index(self):
        with backup.lock(self.config.with_suffix(".lock")):
            with self.assertRaises(backup.SyncError):
                backup.sync(self.config)
        self.assertEqual(self.git("ls-files"), "")
        snapshot = backup.export(self.config)
        self.git("add", "--", "CURRENT.json")
        with self.assertRaises(backup.SyncError):
            backup.sync(self.config)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "CURRENT.json")
        self.assertEqual(backup.verify(self.repo)["snapshot"], snapshot["snapshot"])

    def test_launchd_generation_does_not_activate_or_copy_credentials(self):
        user = self.root / "user"
        user.mkdir()
        original_run = subprocess.run
        observed = []
        def isolated_run(args, *more, **kwargs):
            observed.append(args)
            self.assertNotEqual(args[0], "launchctl", "Tests must not activate launchd")
            return original_run(args, *more, **kwargs)
        with mock.patch.object(backup.sys, "platform", "darwin"), mock.patch.object(backup.Path, "home", return_value=user), \
                mock.patch.object(backup.subprocess, "run", side_effect=isolated_run):
            result = backup.install_launchd(self.config)
            self.assertFalse(result["active"])
            self.assertFalse(result["installed"])
            self.assertTrue(result["prepared"])
            plist = Path(result["plist"])
            self.assertNotIn("LaunchAgents", plist.parts)
            self.assertFalse((user / "Library/LaunchAgents").exists())
            self.assertEqual(stat.S_IMODE(plist.stat().st_mode), 0o600)
            document = plistlib.loads(plist.read_bytes())
            self.assertEqual(document["StartInterval"], 300)
            self.assertEqual(document["ProgramArguments"][-2:], ["run", "--once"])
            self.assertNotIn("StandardOutPath", document)
            self.assertNotIn("StandardErrorPath", document)
            self.assertEqual(set(document["EnvironmentVariables"]), {"PATH"})
            self.assertNotIn(str(self.home), plist.read_text())
            backup.install_launchd(self.config)
        self.assertTrue(observed)

    def test_foreground_once_has_honest_success_and_failure_exit_codes(self):
        result = self.cli("run", "--once")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["event"], "sync.completed")
        self.git("remote", "set-url", "origin", str(self.root / "missing-remote.git"))
        backup.configure(self.config, self.home, self.repo)
        result = self.cli("run", "--once")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["event"], "sync.failed")


if __name__ == "__main__":
    unittest.main()
