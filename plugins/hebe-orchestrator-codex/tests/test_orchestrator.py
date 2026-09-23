"""Local delivery/runtime coverage; every filesystem mutation uses a temporary root."""

import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("hebe_orchestrator", SCRIPTS / "orchestrator.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.user_root = self.root / "user"
        self.user_root.mkdir(mode=0o700)
        self.home = self.root / "central"
        self.project = self.root / "product"
        self.project.mkdir()
        self.brain = runtime.Brain(self.home)
        self.brain.init()
        self.project_id = self.brain.register(self.project, "Produto")["project_id"]
        self.store = runtime.Orchestrator(self.home)
        self.environment = dict(os.environ)
        self.environment.pop("HEBE_BRAIN_HOME", None)
        self.environment.pop("TYPESAFE_API_KEY", None)
        self.environment["HOME"] = str(self.user_root)

    def cli(self, *args, with_home=True, cwd=None):
        command = [sys.executable, str(SCRIPTS / "orchestrator.py")]
        if with_home:
            command += ["--home", str(self.home)]
        return subprocess.run(command + list(args), cwd=cwd, env=self.environment,
                              text=True, capture_output=True, timeout=30)

    def start(self, *, fronts=True):
        return self.store.start(self.project_id, "Entregar exportação", ["csv=Arquivo CSV correto", "utf8=Acentos preservados"],
                                ["backend=Implementar exportação", "frontend=Expor download"] if fronts else [])["delivery"]

    def complete(self, delivery):
        return self.store.update(delivery["delivery_id"], {
            "criteria": [{"id": item["id"], "status": "passed", "evidence": ["fixture e procedimento observados"]}
                         for item in delivery["criteria"]],
            "fronts": [{"id": item["id"], "status": "completed", "model": "modelo-observado", "effort": "medium"}
                       for item in delivery["fronts"]], "next_step": "Fechar entrega"})

    @staticmethod
    def snapshot(root):
        return {str(path.relative_to(root)): (path.lstat().st_mode, path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() and not path.is_symlink() and path.lstat().st_mode & 0o400 else None)
                for path in root.rglob("*")}

    def test_configuration_is_explicit_private_and_does_not_initialize_brain(self):
        absent = self.root / "new-central"
        result = self.cli("doctor", "--path", str(self.project), with_home=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["brain"]["configured"])
        self.assertFalse((self.user_root / ".config").exists())
        result = self.cli("configure", "--brain-home", str(absent), with_home=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.user_root / ".config/hebe-brain/orchestrator.json"
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(config.parent.stat().st_mode), 0o700)
        self.assertEqual(json.loads(config.read_text()), {"schema_version": 1, "brain_home": str(absent)})
        self.assertFalse(absent.exists())
        self.assertFalse(json.loads(result.stdout)["brain_initialized"])

    def test_configuration_override_order_and_reuse(self):
        self.assertEqual(self.cli("configure", "--brain-home", str(self.home), with_home=False).returncode, 0)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            self.assertEqual(runtime.resolve_home(), (self.home, "configuration"))
            with mock.patch.dict(os.environ, {"HEBE_BRAIN_HOME": str(self.root / "environment")}):
                self.assertEqual(runtime.resolve_home()[1], "environment")
                self.assertEqual(runtime.resolve_home(str(self.home)), (self.home, "argument"))
        delivery = self.start()
        result = self.cli("resume", "--path", str(self.project), with_home=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["delivery"]["delivery_id"], delivery["delivery_id"])

    def test_configuration_rejects_symlinks_and_unsafe_modes(self):
        directory = self.user_root / ".config/hebe-brain"
        directory.mkdir(parents=True, mode=0o700)
        outside = self.root / "outside.json"
        outside.write_text("preserve")
        config = directory / "orchestrator.json"
        config.symlink_to(outside)
        result = self.cli("configure", "--brain-home", str(self.home), with_home=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_text(), "preserve")
        config.unlink()
        config.write_text("preserve local")
        config.chmod(0o644)
        result = self.cli("configure", "--brain-home", str(self.home), with_home=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_text(), "preserve local")

    def test_configuration_rejects_symlink_directory(self):
        outside = self.root / "outside-dir"
        outside.mkdir()
        (self.user_root / ".config").symlink_to(outside)
        result = self.cli("configure", "--brain-home", str(self.home), with_home=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_start_persists_and_resume_resolves_nested_project_path(self):
        child = self.project / "frontend"
        child.mkdir()
        child_id = self.brain.register(child, "Frontend", self.project_id)["project_id"]
        delivery = self.store.start(child_id, "Entregar interface", ["Tela acessível", "valor esperado = 200"], ["ui=Interface"])["delivery"]
        self.assertEqual([item["id"] for item in delivery["criteria"]], ["c1", "c2"])
        result = self.cli("resume", "--path", str(child / "src"))
        self.assertEqual(result.returncode, 0, result.stderr)
        found = json.loads(result.stdout)["delivery"]
        self.assertEqual(found["delivery_id"], delivery["delivery_id"])
        self.assertEqual(found["project_id"], child_id)
        self.assertEqual(stat.S_IMODE((self.home / runtime.DB_REL).stat().st_mode), 0o600)
        self.assertIsNone(self.store.status(project=self.project_id)["delivery"])

    def test_cli_start_can_resolve_project_from_path(self):
        result = self.cli("start", "--path", str(self.project), "--objective", "Entrega por caminho",
                          "--criterion", "Critério observável")
        self.assertEqual(result.returncode, 0, result.stderr)
        delivery = json.loads(result.stdout)["delivery"]
        self.assertEqual(delivery["project_id"], self.project_id)

    def test_start_reuses_identical_active_delivery_without_resetting_progress(self):
        initial = self.start()
        self.store.update(initial["delivery_id"], {"next_step": "Concluir frontend"})
        repeated = self.store.start(self.project_id, initial["objective"], ["csv=Arquivo CSV correto", "utf8=Acentos preservados"],
                                    ["backend=Implementar exportação", "frontend=Expor download"])
        self.assertFalse(repeated["created"])
        self.assertEqual(repeated["delivery"]["delivery_id"], initial["delivery_id"])
        self.assertEqual(repeated["delivery"]["next_step"], "Concluir frontend")
        with self.assertRaises(runtime.BrainError):
            self.store.start(self.project_id, "Outro escopo", ["Resultado diferente"])

    def test_start_requires_real_project_and_criteria(self):
        with self.assertRaises(runtime.BrainError):
            self.store.start(str(uuid.uuid4()), "Inválido", ["Critério"])
        with self.assertRaises(runtime.BrainError):
            self.store.start(self.project_id, "Inválido", [])
        with self.assertRaises(runtime.BrainError):
            self.store.start(self.project_id, "Inválido", ["a=Um", "a=Dois"])
        with self.assertRaises(runtime.BrainError):
            self.store.start(self.project_id, "Inválido", ["Critério"], ["Sem identificador"])
        self.assertFalse(self.store.initialized())

    def test_update_requires_evidence_and_rolls_back_invalid_patch(self):
        delivery = self.start()
        did = delivery["delivery_id"]
        bad_patches = [
            {"criteria": [{"id": "csv", "status": "passed"}]},
            {"criteria": [{"id": "csv", "status": "passed", "evidence": [""]}]},
            {"criteria": [{"id": "csv", "status": "waived"}]},
            {"criteria": [{"id": "unknown", "status": "failed"}]},
            {"criteria": [{"id": "csv", "status": "completed"}]},
            {"fronts": [{"id": "frontend", "status": "passed"}]},
            {"criteria": [{"id": "csv", "status": "passed", "evidence": ["observada"]}], "fronts": [{"id": "bad", "status": "completed"}]},
            {"state": "closed"}, {"objective": "Alterar escopo silenciosamente"},
        ]
        for patch in bad_patches:
            with self.subTest(patch=patch), self.assertRaises(runtime.BrainError):
                self.store.update(did, patch)
            self.assertEqual(self.store.status(delivery=did)["delivery"], delivery)

    def test_update_preserves_stable_ids_and_tracks_actual_model(self):
        delivery = self.start()
        result = self.store.update(delivery["delivery_id"], {
            "criteria": [{"id": "csv", "status": "passed", "evidence": "verificação registrada"}],
            "fronts": [{"id": "backend", "status": "running", "model": "effective-model", "effort": "high"}],
            "blockers": ["Falta amostra"], "next_step": "Obter amostra", "expected_revision": 1})
        self.assertEqual(result["delivery"]["revision"], 2)
        self.assertEqual([x["id"] for x in result["delivery"]["criteria"]], ["csv", "utf8"])
        self.assertEqual(result["delivery"]["fronts"][0]["model"], "effective-model")
        self.assertEqual(result["remaining_criteria"], ["utf8"])
        with self.assertRaises(runtime.BrainError):
            self.store.update(delivery["delivery_id"], {"expected_revision": 1, "next_step": "stale"})

    def test_concurrent_updates_preserve_independent_changes(self):
        delivery = self.start()
        did = delivery["delivery_id"]
        changes = [
            {"criteria": [{"id": "csv", "status": "passed", "evidence": ["CSV observado"]}]},
            {"criteria": [{"id": "utf8", "status": "passed", "evidence": ["Acentos observados"]}]},
            {"fronts": [{"id": "backend", "status": "completed"}]},
            {"fronts": [{"id": "frontend", "status": "completed"}]},
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda patch: runtime.Orchestrator(self.home).update(did, patch), changes))
        state = self.store.status(delivery=did)
        self.assertEqual(state["delivery"]["revision"], 5)
        self.assertEqual(state["remaining_criteria"], [])
        self.assertEqual(state["unfinished_fronts"], [])

    def test_close_refuses_pending_failed_cancelled_and_blocked_work(self):
        delivery = self.start()
        did = delivery["delivery_id"]
        with self.assertRaises(runtime.BrainError):
            self.store.close(did, "Pronto")
        self.complete(delivery)
        for front_state in ("planned", "running", "failed", "cancelled"):
            self.store.update(did, {"fronts": [{"id": "backend", "status": front_state}]})
            with self.assertRaises(runtime.BrainError):
                self.store.close(did, "Pronto")
        self.store.update(did, {"fronts": [{"id": "backend", "status": "completed"}], "blockers": ["Acesso pendente"]})
        with self.assertRaises(runtime.BrainError):
            self.store.close(did, "Pronto")
        self.store.update(did, {"blockers": [], "criteria": [{"id": "csv", "status": "failed"}]})
        with self.assertRaises(runtime.BrainError):
            self.store.close(did, "Pronto")
        self.assertEqual(self.store.status(delivery=did)["delivery"]["state"], "active")

    def test_close_records_checkpoint_and_is_idempotent(self):
        delivery = self.start()
        did = delivery["delivery_id"]
        self.complete(delivery)
        result = self.store.close(did, "Exportação entregue com evidências")
        self.assertEqual(result["delivery"]["state"], "closed")
        self.assertFalse(result["checkpoint"]["required"])
        self.assertEqual(self.brain.status()["events"], 1)
        repeated = self.store.close(did, "Exportação entregue com evidências")
        self.assertEqual(repeated, result)
        self.assertEqual(self.brain.status()["events"], 1)
        with self.assertRaises(runtime.BrainError):
            self.store.update(did, {"next_step": "Mudar fechamento"})
        with self.assertRaises(runtime.BrainError):
            self.store.close(did, "Outro resumo")
        newer = self.store.start(self.project_id, "Nova entrega", ["Novo critério"])["delivery"]
        self.assertNotEqual(newer["delivery_id"], did)
        self.assertEqual(self.store.status(project=self.project_id)["delivery"]["delivery_id"], newer["delivery_id"])

    def test_waiver_requires_explicit_rationale_and_is_separate_in_closure(self):
        delivery = self.start(fronts=False)
        did = delivery["delivery_id"]
        self.complete(delivery)
        with self.assertRaises(runtime.BrainError):
            self.store.update(did, {"criteria": [{"id": "utf8", "status": "waived"}]})
        self.store.update(did, {"criteria": [{"id": "utf8", "status": "waived", "evidence": ["Usuário retirou suporte a acentos deste escopo"]}]})
        closed = self.store.close(did, "Entregue no escopo ajustado")
        self.assertEqual([x["id"] for x in closed["waived_criteria"]], ["utf8"])
        self.assertEqual(closed["delivery"]["closure"]["waived_criteria"], closed["waived_criteria"])
        self.assertEqual(closed["delivery"]["criteria"][1]["status"], "waived")

    def test_checkpoint_replays_without_duplicate_brain_events(self):
        delivery = self.start()
        did = delivery["delivery_id"]
        first = self.store.checkpoint(did)
        self.assertFalse(first["checkpoint"]["required"])
        self.assertEqual(self.brain.status()["events"], 1)
        self.store.checkpoint(did)
        self.assertEqual(self.brain.status()["events"], 1)
        self.assertIn("Entrega: Entregar exportação", (self.project / "Brain.md").read_text())
        self.store.update(did, {"next_step": "Nova evidência"})
        self.store.checkpoint(did)
        self.assertEqual(self.brain.status()["events"], 2)

    def test_checkpoint_preserves_effective_host_source(self):
        delivery = self.start(fronts=False)
        self.store.checkpoint(delivery["delivery_id"], source="grok", source_ref="grok:session:synthetic")
        with self.brain.connection(readonly=True) as conn:
            row = conn.execute("SELECT source, source_ref FROM events").fetchone()
        self.assertEqual(dict(row), {"source": "grok", "source_ref": "grok:session:synthetic"})

    def test_invalid_checkpoint_provenance_cannot_mutate_or_close_delivery(self):
        delivery = self.start(fronts=False)
        did = delivery["delivery_id"]
        with self.assertRaises(runtime.BrainError):
            self.store.checkpoint(did, summary="Não deve persistir", source_ref="session\ninvalid")
        self.assertEqual(self.store.status(delivery=did)["delivery"]["summary"], "")

        self.complete(delivery)
        fake = "ghp_" + "Z" * 30
        before = self.store.status(delivery=did)["delivery"]
        for invalid in ("session\ninvalid", "session\rinvalid", "session\tinvalid", fake):
            with self.assertRaises(runtime.BrainError):
                self.store.close(did, "Escopo comprovado", source_ref=invalid)
        after = self.store.status(delivery=did)["delivery"]
        self.assertEqual(after, before)
        self.assertEqual(after["state"], "active")

    def test_checkpoint_recovers_failed_materialization_from_durable_outbox(self):
        delivery = self.start()
        did = delivery["delivery_id"]
        with mock.patch.object(self.store.brain, "consolidate", side_effect=runtime.BrainError("Falha simulada")):
            with self.assertRaises(runtime.BrainError):
                self.store.checkpoint(did)
        pending = self.store.status(delivery=did)
        self.assertEqual(pending["checkpoint"]["pending"], 1)
        self.assertTrue(pending["checkpoint"]["required"])
        self.assertEqual(self.brain.status()["events"], 1)
        recovered = runtime.Orchestrator(self.home).checkpoint(did)
        self.assertEqual(recovered["checkpoint"]["pending"], 0)
        self.assertFalse(recovered["checkpoint"]["required"])
        self.assertEqual(self.brain.status()["events"], 1)

    def test_doctor_is_read_only_and_does_not_read_credentials(self):
        (self.project / "AGENTS.md").write_text("Contrato")
        nested = self.project / "frontend"
        nested.mkdir()
        (nested / "AGENTS.md").write_text("Regras locais")
        (self.project / "playwright.config.ts").write_text("export default {}")
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        credential = self.user_root / ".config/hebe-brain/typesafe.json"
        credential.parent.mkdir(parents=True, mode=0o700)
        credential.write_text("This deliberately is not valid credential JSON")
        credential.chmod(0o000)
        self.start()
        before = self.snapshot(self.root)
        real_open = os.open
        def guarded_open(path, *args, **kwargs):
            if "typesafe.json" in str(path):
                self.fail("doctor attempted to open a credential")
            return real_open(path, *args, **kwargs)
        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(runtime.os, "open", side_effect=guarded_open):
            result = runtime.doctor(nested, self.home, "argument")
        self.assertEqual(self.snapshot(self.root), before)
        self.assertEqual(result["agents"]["host_loaded"], "unknown")
        self.assertEqual(result["agents"]["applicable"], [str(self.project / "AGENTS.md"), str(nested / "AGENTS.md")])
        self.assertEqual(result["jev"]["source"], "local_file")
        self.assertTrue(result["jev"]["presence_only"])
        self.assertTrue(result["git"]["repository"])
        self.assertEqual(result["playwright"]["configs"], [str(self.project / "playwright.config.ts")])

    def test_doctor_does_not_create_runtime_database(self):
        absent = self.root / "missing-central"
        before = self.snapshot(self.root)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            result = runtime.doctor(self.project, absent, "argument")
        self.assertFalse(result["brain"]["initialized"])
        self.assertEqual(self.snapshot(self.root), before)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            result = runtime.doctor(self.project, self.home, "argument")
        self.assertIsNone(result["delivery"]["delivery"])
        self.assertFalse((self.home / runtime.DB_REL).exists())

    def test_database_symlink_does_not_modify_redirected_file(self):
        outside = self.root / "outside.sqlite"
        outside.write_text("preserve")
        (self.home / runtime.DB_REL).symlink_to(outside)
        with self.assertRaises(runtime.BrainError):
            self.start()
        self.assertEqual(outside.read_text(), "preserve")

    def test_empty_database_from_interrupted_initialization_is_recoverable(self):
        target = self.home / runtime.DB_REL
        target.touch(mode=0o600)
        delivery = self.start()
        self.assertEqual(self.store.status(delivery=delivery["delivery_id"])["delivery"], delivery)

    def test_close_reports_pending_checkpoint_and_can_recover(self):
        delivery = self.start(fronts=False)
        did = delivery["delivery_id"]
        self.complete(delivery)
        with mock.patch.object(self.store.brain, "consolidate", side_effect=runtime.BrainError("Falha simulada")):
            with self.assertRaises(runtime.BrainError):
                self.store.close(did, "Escopo comprovado")
        pending = self.store.status(delivery=did)
        self.assertEqual(pending["delivery"]["state"], "closed")
        self.assertEqual(pending["checkpoint"]["pending"], 1)
        self.assertTrue(pending["checkpoint"]["required"])
        recovered = self.store.close(did, "Escopo comprovado")
        self.assertFalse(recovered["checkpoint"]["required"])
        self.assertEqual(self.brain.status()["events"], 1)

    def test_cli_update_checkpoint_and_json_errors(self):
        started = self.cli("start", "--project", self.project_id, "--objective", "Uma entrega", "--criterion", "Um critério")
        self.assertEqual(started.returncode, 0, started.stderr)
        did = json.loads(started.stdout)["delivery"]["delivery_id"]
        patch = self.root / "patch.json"
        patch.write_text(json.dumps({"criteria": [{"id": "c1", "status": "passed", "evidence": ["observada"]}]}))
        result = self.cli("update", "--delivery", did, "--file", str(patch))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("checkpoint", "--delivery", did)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("close", "--delivery", did, "--summary", "Critério comprovado")
        self.assertEqual(result.returncode, 0, result.stderr)
        invalid = self.cli("update", "--delivery", did)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("error", json.loads(invalid.stderr))

    def test_secrets_and_duplicate_json_are_rejected_without_echo(self):
        fake = "ghp_" + "Z" * 30
        started = self.cli("start", "--project", self.project_id, "--objective", fake, "--criterion", "Um critério")
        self.assertEqual(started.returncode, 2)
        self.assertNotIn(fake, started.stdout + started.stderr)
        invalid = self.cli("--unsupported", fake)
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn(fake, invalid.stdout + invalid.stderr)
        with self.assertRaises(runtime.BrainError):
            runtime.strict_json('{"next_step":"A","next_step":"B"}')
        with self.assertRaises(runtime.BrainError):
            runtime.strict_json('{"api_key":"example-secret-that-must-not-enter-state"}')


if __name__ == "__main__":
    unittest.main()
