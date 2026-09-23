#!/usr/bin/env python3
"""Persistent delivery coordination. Local Python stdlib; no provider calls."""

from __future__ import annotations

import argparse
import contextlib
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import uuid

from brain import Brain, BrainError, SOURCES, contains_secret, now, safe_path, validate_text, valid_uuid


CONFIG_NAME = "orchestrator.json"
DB_REL = ".state/orchestrator.sqlite3"
MAX_JSON = 128 * 1024
CRITERION_STATES = {"pending", "passed", "failed", "waived"}
FRONT_STATES = {"planned", "running", "completed", "failed", "cancelled"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
PLAYWRIGHT_CONFIGS = tuple("playwright.config." + ext for ext in ("ts", "js", "mts", "mjs", "cts", "cjs"))


class OrchestratorError(BrainError):
    pass


def text_field(value, maximum=4000, *, empty=False):
    validate_text(value, maximum, empty=empty)
    if contains_secret(value):
        raise OrchestratorError("Possível segredo recusado; conteúdo omitido.")
    return value


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise OrchestratorError("ID de critério ou frente inválido.")
    return value


def evidence_list(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or len(value) > 30:
        raise OrchestratorError("Evidência deve ser uma lista curta de textos.")
    return [text_field(item, 4000) for item in value]


def strict_json(raw):
    if len(raw) > MAX_JSON:
        raise OrchestratorError("Documento JSON excede o limite.")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise OrchestratorError("Chave JSON duplicada.")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise OrchestratorError("JSON inválido; conteúdo omitido.") from None
    if contains_secret(value):
        raise OrchestratorError("Possível segredo recusado; conteúdo omitido.")
    return value


def regular_private(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
        raise OrchestratorError("Arquivo local deve ser regular, próprio e ter permissão 0600.")


@contextlib.contextmanager
def config_directory(*, create=False):
    """Use fixed dirfds; never follow a replacement symlink for configuration."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(str(Path.home()), flags)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise OrchestratorError("A pasta do usuário tem proprietário ou permissões incompatíveis.")
        for name, private in ((".config", False), ("hebe-brain", True)):
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & (0o077 if private else 0o022):
                raise OrchestratorError("Configuração requer pasta própria; hebe-brain precisa ter modo 0700.")
        yield fd
    finally:
        os.close(fd)


def load_configuration():
    try:
        with config_directory() as directory:
            try:
                fd = os.open(CONFIG_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            except FileNotFoundError:
                return None
            with os.fdopen(fd, "rb") as stream:
                regular_private(os.fstat(stream.fileno()))
                data = strict_json(stream.read(MAX_JSON + 1))
    except FileNotFoundError:
        return None
    if (not isinstance(data, dict) or set(data) != {"schema_version", "brain_home"}
            or data["schema_version"] != 1):
        raise OrchestratorError("Formato de configuração não suportado.")
    text_field(data["brain_home"])
    if not Path(data["brain_home"]).is_absolute():
        raise OrchestratorError("A configuração precisa conter raiz absoluta.")
    return data


def configure(brain_home):
    root = Brain(text_field(str(brain_home))).home
    content = json.dumps({"schema_version": 1, "brain_home": str(root)}, ensure_ascii=False) + "\n"
    with config_directory(create=True) as directory:
        try:
            regular_private(os.stat(CONFIG_NAME, dir_fd=directory, follow_symlinks=False))
        except FileNotFoundError:
            pass
        temporary = ".orchestrator-" + secrets.token_hex(12) + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, CONFIG_NAME, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
    return {"configured": True, "brain_home": str(root), "source": "configuration",
            "brain_initialized": Brain(root).initialized()}


def resolve_home(override=None, *, required=True):
    if override is not None:
        return Brain(text_field(str(override))).home, "argument"
    if "HEBE_BRAIN_HOME" in os.environ:
        return Brain(text_field(os.environ["HEBE_BRAIN_HOME"])).home, "environment"
    config = load_configuration()
    if config:
        return Brain(config["brain_home"]).home, "configuration"
    if required:
        raise OrchestratorError("Raiz central ausente; use configure --brain-home, --home ou HEBE_BRAIN_HOME.")
    return None, None


SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE deliveries (
 delivery_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL,
 revision INTEGER NOT NULL, data_json TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX active_project ON deliveries(project_id) WHERE state = 'active';
CREATE TABLE checkpoints (
 delivery_id TEXT NOT NULL REFERENCES deliveries(delivery_id), revision INTEGER NOT NULL,
 event_json TEXT NOT NULL, applied_at TEXT,
 PRIMARY KEY(delivery_id, revision)
);
PRAGMA user_version = 1;
COMMIT;
"""


class Orchestrator:
    def __init__(self, home):
        self.brain = Brain(home)
        self.home = self.brain.home

    def initialized(self):
        return self.home.exists() and safe_path(self.home, DB_REL).is_file()

    @contextlib.contextmanager
    def lock(self):
        if not self.brain.initialized():
            raise OrchestratorError("Inicialize e registre o projeto no Brain antes de iniciar uma entrega.")
        target = safe_path(self.home, ".state/orchestrator.lock")
        fd = os.open(target, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            regular_private(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @contextlib.contextmanager
    def connection(self, *, write=False):
        target = safe_path(self.home, DB_REL)
        for suffix in ("-journal", "-wal", "-shm"):
            safe_path(self.home, DB_REL + suffix)
        if write:
            try:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        if not target.exists():
            raise OrchestratorError("Nenhuma entrega registrada nesta central.")
        regular_private(target.lstat())
        conn = sqlite3.connect(target if write else target.as_uri() + "?mode=ro", uri=not write, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if write and version == 0 and not conn.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
                conn.executescript(SCHEMA)
            if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise OrchestratorError("Versão de armazenamento do orquestrador não suportada.")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            if write:
                conn.commit()
        except BaseException:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def project_id(self, project=None, path=None):
        with self.brain.connection(readonly=True) as conn:
            row = self.brain.project(conn, project) if project else self.brain.resolve(conn, path or os.getcwd())
            return row["project_id"]

    @staticmethod
    def get(conn, delivery_id):
        valid_uuid(delivery_id)
        row = conn.execute("SELECT data_json FROM deliveries WHERE delivery_id = ?", (delivery_id,)).fetchone()
        if row is None:
            raise OrchestratorError("Entrega não encontrada.")
        return strict_json(row["data_json"])

    @staticmethod
    def validate_document(document):
        raw = json.dumps(document, ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > 48000 or contains_secret(document):
            raise OrchestratorError("Estado da entrega excede o limite ou contém possível segredo.")
        return raw

    @classmethod
    def save(cls, conn, data, *, insert=False):
        raw = cls.validate_document(data)
        if insert:
            conn.execute("INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (data["delivery_id"], data["project_id"], data["state"], data["revision"],
                          raw, data["created_at"], data["updated_at"]))
        else:
            conn.execute("UPDATE deliveries SET state=?, revision=?, data_json=?, updated_at=? WHERE delivery_id=?",
                         (data["state"], data["revision"], raw, data["updated_at"], data["delivery_id"]))

    @staticmethod
    def items(values, *, front=False):
        if not isinstance(values, list) or len(values) > 100 or (not front and not values):
            raise OrchestratorError("Defina de 1 a 100 critérios e no máximo 100 frentes.")
        items, seen = [], set()
        for index, value in enumerate(values, 1):
            text_field(value, 2000)
            left, separator, right = value.partition("=")
            if front and not separator:
                raise OrchestratorError("Frentes usam ID=TÍTULO.")
            explicit = bool(separator and IDENTIFIER.fullmatch(left))
            if front and not explicit:
                raise OrchestratorError("Frentes usam ID=TÍTULO com ID válido.")
            key, title = (identifier(left), text_field(right, 2000)) if explicit else (f"c{index}", value)
            if key in seen:
                raise OrchestratorError("ID duplicado no escopo da entrega.")
            seen.add(key)
            item = {"id": key, "title": title, "status": "planned" if front else "pending", "evidence": []}
            if front:
                item.update(model=None, effort=None)
            items.append(item)
        return items

    def start(self, project, objective, criteria, fronts=None, *, path=None):
        project = self.project_id(project, path)
        objective = text_field(objective)
        criteria, fronts = self.items(criteria), self.items(fronts or [], front=True)
        with self.lock(), self.connection(write=True) as conn:
            row = conn.execute("SELECT delivery_id FROM deliveries WHERE project_id=? AND state='active'", (project,)).fetchone()
            if row:
                current = self.get(conn, row["delivery_id"])
                signature = lambda items: [(x["id"], x["title"]) for x in items]
                if (current["objective"] == objective and signature(current["criteria"]) == signature(criteria)
                        and signature(current["fronts"]) == signature(fronts)):
                    return {"created": False, "delivery": current}
                raise OrchestratorError("Já existe entrega ativa neste projeto; retome seu escopo antes de criar outra.")
            stamp = now()
            data = {"delivery_id": str(uuid.uuid4()), "project_id": project, "objective": objective,
                    "state": "active", "revision": 1, "criteria": criteria, "fronts": fronts,
                    "blockers": [], "next_step": "", "summary": "", "created_at": stamp,
                    "updated_at": stamp, "closed_at": None}
            self.save(conn, data, insert=True)
        return {"created": True, "delivery": data}

    def status(self, *, delivery=None, project=None, path=None):
        if sum(value is not None for value in (delivery, project, path)) > 1:
            raise OrchestratorError("Use somente um seletor: entrega, projeto ou caminho.")
        selected = self.project_id(project, path) if delivery is None else None
        if not self.initialized():
            if delivery:
                raise OrchestratorError("Entrega não encontrada.")
            return {"delivery": None, "project_id": selected}
        with self.connection() as conn:
            if delivery is None:
                row = conn.execute("""SELECT delivery_id FROM deliveries WHERE project_id=?
                    ORDER BY CASE state WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC, rowid DESC LIMIT 1""",
                                   (selected,)).fetchone()
                if row is None:
                    return {"delivery": None, "project_id": selected}
                delivery = row["delivery_id"]
            data = self.get(conn, delivery)
            last = conn.execute("SELECT max(revision) FROM checkpoints WHERE delivery_id=? AND applied_at IS NOT NULL", (delivery,)).fetchone()[0]
            pending = conn.execute("SELECT count(*) FROM checkpoints WHERE delivery_id=? AND applied_at IS NULL", (delivery,)).fetchone()[0]
            return {"delivery": data, "checkpoint": {"last_applied_revision": last,
                    "pending": pending, "required": last != data["revision"]},
                    "remaining_criteria": [item["id"] for item in data["criteria"] if item["status"] not in {"passed", "waived"}],
                    "waived_criteria": [item for item in data["criteria"] if item["status"] == "waived"],
                    "unfinished_fronts": [item["id"] for item in data["fronts"] if item["status"] != "completed"]}

    def update(self, delivery, patch):
        allowed = {"criteria", "fronts", "blockers", "next_step", "summary", "expected_revision"}
        if not isinstance(patch, dict) or not patch or set(patch) - allowed or contains_secret(patch):
            raise OrchestratorError("Atualização inválida ou com possível segredo.")
        with self.lock(), self.connection(write=True) as conn:
            data = self.get(conn, delivery)
            if data["state"] != "active":
                raise OrchestratorError("Entrega fechada não aceita alterações.")
            if "expected_revision" in patch and (type(patch["expected_revision"]) is not int or patch["expected_revision"] != data["revision"]):
                raise OrchestratorError("Revisão divergente; retome o estado antes de atualizar.")
            updated = copy.deepcopy(data)
            for group in ("criteria", "fronts"):
                if group not in patch:
                    continue
                changes = patch[group]
                if not isinstance(changes, list) or len(changes) > 100:
                    raise OrchestratorError("Lista de alterações inválida.")
                indexed = {item["id"]: item for item in updated[group]}
                seen = set()
                for change in changes:
                    keys = {"id", "status", "evidence"} | ({"model", "effort"} if group == "fronts" else set())
                    if not isinstance(change, dict) or "id" not in change or set(change) - keys:
                        raise OrchestratorError("Campos de critério ou frente inválidos.")
                    key = identifier(change["id"])
                    if key not in indexed or key in seen:
                        raise OrchestratorError("Critério ou frente ausente ou repetido.")
                    seen.add(key)
                    item = indexed[key]
                    if "status" in change:
                        states = CRITERION_STATES if group == "criteria" else FRONT_STATES
                        if not isinstance(change["status"], str) or change["status"] not in states:
                            raise OrchestratorError("Estado de critério ou frente inválido.")
                        item["status"] = change["status"]
                    if "evidence" in change:
                        item["evidence"] = evidence_list(change["evidence"])
                    for field in ("model", "effort"):
                        if field in change:
                            item[field] = None if change[field] is None else text_field(change[field], 160)
                    if group == "criteria" and item["status"] in {"passed", "waived"} and not item["evidence"]:
                        raise OrchestratorError("Critério passed ou waived exige evidência ou justificativa não vazia.")
                    if (group == "criteria" and change.get("status") == "waived"
                            and "evidence" not in change):
                        raise OrchestratorError("Dispensa explícita exige nova justificativa no mesmo update.")
            if "blockers" in patch:
                if not isinstance(patch["blockers"], list) or len(patch["blockers"]) > 100:
                    raise OrchestratorError("Impedimentos devem ser uma lista curta de textos.")
                updated["blockers"] = [text_field(item, 2000) for item in patch["blockers"]]
            for field in ("next_step", "summary"):
                if field in patch:
                    updated[field] = text_field(patch[field], empty=True)
            if updated != data:
                updated.update(revision=data["revision"] + 1, updated_at=now())
                self.save(conn, updated)
        return self.status(delivery=delivery)

    @staticmethod
    def provenance(source="manual", source_ref=None, delivery_id=None):
        if source not in SOURCES:
            raise OrchestratorError("Origem do checkpoint não suportada.")
        fallback = "hebe-orchestrator:delivery:" + delivery_id if delivery_id else None
        reference = text_field(source_ref or fallback, 2048)
        validate_text(reference, 2048, single_line=True)
        return source, reference

    @staticmethod
    def snapshot(data, source="manual", source_ref=None):
        source, source_ref = Orchestrator.provenance(source, source_ref, data["delivery_id"])
        title = "Entrega: " + " ".join(data["objective"].split())[:200]
        body = json.dumps({key: value for key, value in data.items() if key not in {"created_at", "updated_at"}},
                          ensure_ascii=False, separators=(",", ":"))
        event = {"event_id": f"delivery:{data['delivery_id']}:r{data['revision']}",
                 "project_id": data["project_id"], "kind": "note.recorded", "occurred_at": data["updated_at"],
                 "source": source, "source_ref": source_ref,
                 "payload": {"title": title, "body": body, "delivery_id": data["delivery_id"],
                             "delivery_revision": data["revision"], "delivery_state": data["state"]}}
        Brain.validate_event(event)
        return event

    def _checkpoint_locked(self, delivery, source="manual", source_ref=None):
        with self.connection(write=True) as conn:
            data = self.get(conn, delivery)
            event = self.snapshot(data, source, source_ref)
            conn.execute("INSERT OR IGNORE INTO checkpoints(delivery_id,revision,event_json) VALUES (?,?,?)",
                         (delivery, data["revision"], json.dumps(event, ensure_ascii=False)))
            pending = conn.execute("SELECT revision,event_json FROM checkpoints WHERE delivery_id=? AND applied_at IS NULL ORDER BY revision", (delivery,)).fetchall()
        # Durable outbox precedes Brain writes. A replay uses the same immutable event.
        for row in pending:
            self.brain.record(strict_json(row["event_json"]))
        if pending:
            self.brain.consolidate(data["project_id"])
            with self.connection(write=True) as conn:
                conn.executemany("UPDATE checkpoints SET applied_at=? WHERE delivery_id=? AND revision=?",
                                 [(now(), delivery, row["revision"]) for row in pending])

    def checkpoint(self, delivery, summary=None, source="manual", source_ref=None):
        # Validate provenance before an optional summary update can mutate state.
        self.provenance(source, source_ref, delivery)
        if summary is not None:
            self.update(delivery, {"summary": summary})
        with self.lock():
            self._checkpoint_locked(delivery, source, source_ref)
        return self.status(delivery=delivery)

    def close(self, delivery, summary, source="manual", source_ref=None):
        summary = text_field(summary)
        # Refuse invalid or secret-bearing provenance before closing the delivery.
        self.provenance(source, source_ref, delivery)
        with self.lock():
            with self.connection(write=True) as conn:
                data = self.get(conn, delivery)
                if data["state"] == "closed":
                    if data["summary"] != summary:
                        raise OrchestratorError("Entrega já fechada com outro resumo; seu histórico foi preservado.")
                else:
                    if (any(item["status"] not in {"passed", "waived"} or not item["evidence"] for item in data["criteria"])
                            or data["blockers"] or any(item["status"] != "completed" for item in data["fronts"])):
                        raise OrchestratorError("Entrega incompleta: confira critérios, evidências, impedimentos e frentes.")
                    data.update(state="closed", summary=summary,
                                closure={"summary": summary, "waived_criteria": [copy.deepcopy(item) for item in data["criteria"] if item["status"] == "waived"]},
                                revision=data["revision"] + 1,
                                closed_at=now(), updated_at=now())
                    self.save(conn, data)
            self._checkpoint_locked(delivery, source, source_ref)
        return self.status(delivery=delivery)


def regular_present(path):
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except (FileNotFoundError, PermissionError):
        return False


def doctor(path, home=None, source=None):
    root = Path(text_field(str(path))).expanduser().resolve()
    if not root.is_dir():
        raise OrchestratorError("doctor requer uma pasta existente.")
    ancestors = list(reversed([root, *root.parents]))
    applicable = [str(folder / "AGENTS.md") for folder in ancestors if regular_present(folder / "AGENTS.md")]
    git = {"available": shutil.which("git") is not None, "repository": False, "root": None}
    if git["available"]:
        try:
            result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                                    capture_output=True, text=True, timeout=5,
                                    env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
            if result.returncode == 0:
                git.update(repository=True, root=str(Path(result.stdout.strip()).resolve()))
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            git["inspection"] = "unavailable"
    configs = []
    for folder in [root, *root.parents]:
        configs += [str(folder / name) for name in PLAYWRIGHT_CONFIGS if regular_present(folder / name)]
        if str(folder) == git["root"]:
            break
    credential_file = Path.home() / ".config" / "hebe-brain" / "typesafe.json"
    # Presence only. Do not open a credential file or inspect its value.
    credential_source = "environment" if "TYPESAFE_API_KEY" in os.environ else "local_file" if regular_present(credential_file) else None
    result = {"path": str(root), "agents": {"present_here": regular_present(root / "AGENTS.md"),
              "applicable": applicable, "host_loaded": "unknown"},
              "brain": {"configured": home is not None, "source": source, "initialized": False},
              "jev": {"configured": credential_source is not None, "source": credential_source,
                      "presence_only": True, "connection_checked": False},
              "git": git, "playwright": {"configs": configs, "execution_verified": False}}
    if home is not None:
        brain = Brain(home)
        result["brain"].update(brain.status())
        if brain.initialized():
            try:
                with brain.connection(readonly=True) as conn:
                    project = brain.public_project(brain.resolve(conn, root))
                result["brain"]["project"] = project
                result["delivery"] = Orchestrator(home).status(project=project["project_id"])
            except BrainError:
                result["brain"]["project"] = None
                result["brain"]["project_resolution"] = "unavailable"
    return result


def safe_output(value):
    if isinstance(value, dict):
        return {key: safe_output(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_output(item) for item in value]
    if isinstance(value, str) and contains_secret(value):
        return "[conteúdo omitido: possível segredo]"
    return value


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        raise OrchestratorError("Argumentos inválidos; consulte --help.")


def main(argv=None):
    parser = JsonParser(description=__doc__)
    parser.add_argument("--home", help="Override da central; prevalece sobre ambiente e configuração.")
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("configure", help="Persiste a escolha da central, sem inicializar o Brain.")
    config.add_argument("--brain-home", required=True)
    check = sub.add_parser("doctor", help="Inspeção local somente leitura; não verifica credenciais.")
    check.add_argument("--path", default=os.getcwd())
    start = sub.add_parser("start")
    start_selector = start.add_mutually_exclusive_group(required=True)
    start_selector.add_argument("--project")
    start_selector.add_argument("--path")
    start.add_argument("--objective", required=True)
    start.add_argument("--criterion", action="append", required=True)
    start.add_argument("--front", action="append", default=[])
    for command in ("status", "resume"):
        selection = sub.add_parser(command).add_mutually_exclusive_group()
        selection.add_argument("--delivery")
        selection.add_argument("--project")
        selection.add_argument("--path")
    update = sub.add_parser("update")
    update.add_argument("--delivery", required=True)
    update.add_argument("--file", required=True)
    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--delivery", required=True)
    checkpoint.add_argument("--summary")
    checkpoint.add_argument("--source", choices=sorted(SOURCES), default="manual")
    checkpoint.add_argument("--source-ref")
    close = sub.add_parser("close")
    close.add_argument("--delivery", required=True)
    close.add_argument("--summary", required=True)
    close.add_argument("--source", choices=sorted(SOURCES), default="manual")
    close.add_argument("--source-ref")
    try:
        args = parser.parse_args(argv)
        if args.command == "configure":
            result = configure(args.brain_home)
        else:
            home, source = resolve_home(args.home, required=args.command != "doctor")
            if args.command == "doctor":
                result = doctor(args.path, home, source)
            else:
                store = Orchestrator(home)
                if args.command == "start":
                    result = store.start(args.project, args.objective, args.criterion, args.front, path=args.path)
                elif args.command in {"status", "resume"}:
                    result = store.status(delivery=args.delivery, project=args.project, path=args.path)
                elif args.command == "update":
                    target = Path(args.file)
                    if not regular_present(target):
                        raise OrchestratorError("Atualização exige arquivo JSON regular.")
                    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as stream:
                        result = store.update(args.delivery, strict_json(stream.read(MAX_JSON + 1)))
                elif args.command == "checkpoint":
                    result = store.checkpoint(args.delivery, args.summary, args.source, args.source_ref)
                else:
                    result = store.close(args.delivery, args.summary, args.source, args.source_ref)
        print(json.dumps(safe_output(result), ensure_ascii=False, indent=2))
        return 0
    except BrainError as exc:
        message = str(exc)
    except (OSError, sqlite3.Error, ValueError, TypeError, UnicodeError, RecursionError):
        message = "Operação local indisponível; confira caminhos, permissões e formato. Conteúdo omitido."
    except KeyboardInterrupt:
        message = "Operação interrompida; retome o estado e checkpoints pendentes."
    print(json.dumps({"error": safe_output(message)}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
