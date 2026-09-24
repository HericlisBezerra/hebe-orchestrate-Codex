#!/usr/bin/env python3
"""Local HeBe Brain registry and event journal. Python standard library only."""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.parse import quote
from urllib.parse import urlsplit
import uuid


KINDS = {
    "decision.proposed", "decision.accepted", "decision.superseded",
    "implementation.completed", "verification.completed", "commit.created",
    "review.completed", "note.recorded", "push.completed", "publication.completed",
}
SOURCES = {"codex", "claude-code", "grok", "git", "manual"}
MARKER = "<!-- hebe-brain:"
MAX_INPUT = 2 * 1024 * 1024
MAX_EVENTS = 500
SENSITIVE_KEY = re.compile(
    r"^(?:api[_-]?key|secret|token|password|passwd|senha|private[_-]?key|"
    r"service[_-]?role[_-]?key|database[_-]?url)$", re.I
)
SECRET_PATTERNS = [
    re.compile(r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{12,})"),
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.I),
    # Start only at a scheme boundary. An unanchored greedy scheme retries at
    # every letter of long prose and makes this safety scan quadratic.
    re.compile(r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@", re.I),
    re.compile(r"\b(?:[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|PASSWD|SENHA|SERVICE_ROLE_KEY))\s*[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_./+!@$%-]{8,})", re.I),
]
PLACEHOLDERS = {"redacted", "redigido", "example", "changeme", "placeholder"}


class BrainError(Exception):
    """An error whose message contains no input data."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def contains_secret(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if SENSITIVE_KEY.fullmatch(key) and isinstance(item, (str, int, float)):
                plain = str(item).strip(" <>[]\"'").lower()
                if plain and plain not in PLACEHOLDERS and not plain.startswith("your_"):
                    return True
            if contains_secret(item):
                return True
        return False
    if isinstance(value, list):
        return any(contains_secret(item) for item in value)
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(value):
                if match.lastindex:
                    matched = match.group(1).lower()
                    if matched in PLACEHOLDERS or matched.startswith("your_"):
                        continue
                return True
    return False


def output_text(value):
    return "[conteúdo omitido: possível segredo]" if contains_secret(value) else value


def validate_text(value, maximum, *, empty=False, single_line=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise BrainError("Campo de texto ausente, inválido ou muito grande.")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value) or MARKER in value:
        raise BrainError("Conteúdo contém caracteres ou marcadores reservados.")
    if single_line and any(c in value for c in "\n\r\t"):
        raise BrainError("Este campo deve ocupar uma única linha.")
    return value


def valid_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise BrainError("Identificador de projeto inválido.") from None
    return value


def safe_path(root, relative):
    """Reject traversal, changed root ancestry and symlinks below a canonical root."""
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(p in {"..", "."} for p in rel.parts):
        raise BrainError("Caminho fora da raiz permitida.")
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or root != root.resolve():
        raise BrainError("Raiz local inválida ou link simbólico.")
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise BrainError("Link simbólico em caminho gerenciado não é permitido.")
    if os.path.commonpath((str(root.resolve()), str(current.resolve()))) != str(root.resolve()):
        raise BrainError("Caminho fora da raiz permitida.")
    return current


def read_text(root, relative):
    target = safe_path(root, relative)
    if not target.exists():
        return ""
    if not target.is_file() or target.stat().st_size > 4 * 1024 * 1024:
        raise BrainError("Documento gerenciado inválido ou muito grande.")
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        return stream.read()


def atomic_write(root, relative, content):
    target = safe_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe_path(root, relative)
    if target.exists() and read_text(root, relative) == content:
        return
    fd, temporary = tempfile.mkstemp(prefix=".hebe-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(root, relative)
        os.replace(temporary, target)
        parent_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def managed(root, relative, section, content, initial):
    existing = read_text(root, relative)
    start = f"{MARKER}{section}:start -->"
    end = f"{MARKER}{section}:end -->"
    block = f"{start}\n{content.rstrip()}\n{end}"
    if start in existing or end in existing:
        if existing.count(start) != 1 or existing.count(end) != 1 or existing.index(start) > existing.index(end):
            raise BrainError("Seção gerenciada incompleta; preserve o arquivo e corrija seus marcadores.")
        left, remainder = existing.split(start, 1)
        _, right = remainder.split(end, 1)
        updated = left + block + right
    else:
        updated = (existing or initial).rstrip("\n") + "\n\n" + block + "\n"
    atomic_write(root, relative, updated)


def md_label(value):
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def local_link(label, target, base):
    return f"[{md_label(label)}]({quote(os.path.relpath(target, base), safe='/.-_')})"


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
  parent_id TEXT REFERENCES projects(project_id), brain_rel TEXT NOT NULL,
  vault_rel TEXT NOT NULL, index_rel TEXT NOT NULL, decisions_rel TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
  project_id TEXT NOT NULL REFERENCES projects(project_id), kind TEXT NOT NULL,
  occurred_at TEXT NOT NULL, source TEXT NOT NULL, source_ref TEXT NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, payload_json TEXT NOT NULL,
  event_json TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_project_seq ON events(project_id, seq);
CREATE TABLE IF NOT EXISTS checkpoints (
  project_id TEXT PRIMARY KEY REFERENCES projects(project_id),
  last_seq INTEGER NOT NULL, consolidated_at TEXT NOT NULL
);
PRAGMA user_version = 1;
"""


class Brain:
    def __init__(self, home):
        raw = Path(home).expanduser().absolute()
        if raw.is_symlink():
            raise BrainError("A raiz central deve ser uma pasta, não um link simbólico.")
        self.home = raw.resolve()

    def initialized(self):
        if not self.home.exists():
            return False
        return safe_path(self.home, ".state/brain.sqlite3").is_file()

    @contextlib.contextmanager
    def writer(self, *, create=False):
        if create:
            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
            safe_path(self.home, ".state").mkdir(exist_ok=True, mode=0o700)
        elif not self.initialized():
            raise BrainError("Cérebro não inicializado; execute init com --home explícito.")
        lock = safe_path(self.home, ".state/writer.lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextlib.contextmanager
    def connection(self, *, readonly=False, create=False):
        target = safe_path(self.home, ".state/brain.sqlite3")
        for suffix in ("-journal", "-wal", "-shm"):
            safe_path(self.home, ".state/brain.sqlite3" + suffix)
        if not create and not target.is_file():
            raise BrainError("Cérebro não inicializado; execute init com --home explícito.")
        if readonly:
            connection = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True, timeout=30)
        else:
            connection = sqlite3.connect(target, timeout=30)
            os.chmod(target, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if not readonly:
                connection.execute("BEGIN IMMEDIATE")
            else:
                connection.execute("BEGIN")
            yield connection
            if not readonly:
                connection.commit()
        except BaseException:
            if not readonly:
                connection.rollback()
            raise
        finally:
            connection.close()

    def init(self):
        with self.writer(create=True), self.connection(create=True) as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise BrainError("Versão do armazenamento não suportada.")
            conn.executescript(SCHEMA)
            self.ignore_local_state()
            self.central_index(conn)
        return self.status()

    def ignore_local_state(self):
        existing = read_text(self.home, ".gitignore")
        meaningful = [line.strip() for line in existing.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if meaningful and meaningful[-1] == "/.state/":
            return
        separator = "" if not existing or existing.endswith("\n") else "\n"
        addition = "# HeBe Brain: registro e eventos locais fora do Git\n/.state/\n"
        atomic_write(self.home, ".gitignore", existing + separator + addition)

    def central_index(self, conn):
        rows = conn.execute("SELECT * FROM projects ORDER BY name, project_id").fetchall()
        for relative, heading in (("Brain.md", "# HeBe Brain\n"), ("vault/00-Indice.md", "# Índice central\n")):
            lines = ["## Projetos registrados", ""]
            for row in rows:
                lines.append("- " + local_link(row["name"], Path(row["path"]) / row["brain_rel"], (self.home / relative).parent)
                             + f" — `{row['project_id']}`")
            if not rows:
                lines.append("Nenhum projeto registrado.")
            lines += ["", "O registro e os eventos locais vivem em `.state/brain.sqlite3`.",
                      "Cada projeto mantém seus próprios documentos. Não há sincronização remota ativa."]
            managed(self.home, relative, "projects", "\n".join(lines), heading)

    def status(self):
        result = {"initialized": False, "home": str(self.home), "projects": 0,
                  "events": 0, "pending_events": 0, "pending_materializations": 0,
                  "last_consolidated_at": None}
        if not self.initialized():
            return result
        with self.connection(readonly=True) as conn:
            result.update(initialized=True,
                          projects=conn.execute("SELECT count(*) FROM projects").fetchone()[0],
                          events=conn.execute("SELECT count(*) FROM events").fetchone()[0],
                          pending_events=self.pending(conn),
                          pending_materializations=conn.execute("""SELECT count(*) FROM projects p
                              LEFT JOIN checkpoints c USING(project_id)
                              WHERE c.project_id IS NULL OR EXISTS (
                                SELECT 1 FROM events e WHERE e.project_id = p.project_id AND e.seq > c.last_seq
                              )""").fetchone()[0],
                          last_consolidated_at=conn.execute("SELECT max(consolidated_at) FROM checkpoints").fetchone()[0])
        return result

    @staticmethod
    def pending(conn, project_id=None):
        sql = "SELECT count(*) FROM events e LEFT JOIN checkpoints c USING(project_id) WHERE e.seq > coalesce(c.last_seq, 0)"
        args = ()
        if project_id:
            sql += " AND e.project_id = ?"
            args = (project_id,)
        return conn.execute(sql, args).fetchone()[0]

    @staticmethod
    def project(conn, project_id):
        valid_uuid(project_id)
        row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        if row is None:
            raise BrainError("Projeto não registrado.")
        return row

    @staticmethod
    def public_project(row):
        root = Path(row["path"])
        return {"project_id": row["project_id"], "name": row["name"], "path": str(root),
                "parent_id": row["parent_id"], "brain_path": str(root / row["brain_rel"]),
                "vault_path": str(root / row["vault_rel"]), "index_path": str(root / row["index_rel"]),
                "decisions_path": str(root / row["decisions_rel"])}

    @staticmethod
    def detect_layout(root):
        for name in ("Brain.md", "vault", "brain"):
            safe_path(root, name)
        vault = "vault" if (root / "vault").is_dir() else "brain" if (root / "brain").is_dir() else "vault"
        index = next((f"{vault}/{name}" for name in ("00-Indice.md", "INDEX.md")
                      if safe_path(root, f"{vault}/{name}").is_file()), f"{vault}/00-Indice.md")
        entry = "Brain.md" if (root / "Brain.md").is_file() else index if (root / index).is_file() else "Brain.md"
        decisions = f"{vault}/03-Decisoes/Registro-de-Decisoes.md"
        for rel in (entry, index, decisions, f"{vault}/98-HeBe-Events", f"{vault}/04-Engenharia/Commits.md"):
            safe_path(root, rel)
        return entry, vault, index, decisions

    def register(self, path, name, parent=None):
        validate_text(name, 160, single_line=True)
        if contains_secret(name) or contains_secret(str(path)):
            raise BrainError("Entrada recusada: possível segredo; conteúdo omitido.")
        root = Path(path).expanduser().resolve()
        if not root.is_dir() or root == self.home:
            raise BrainError("Projeto deve apontar para uma pasta existente distinta da raiz central.")
        with self.writer():
            # Persist identity before writing Markdown. SQLite and several files cannot
            # share one transaction: a missing checkpoint is a recoverable pending state.
            with self.connection() as conn:
                previous = conn.execute("SELECT * FROM projects WHERE path = ?", (str(root),)).fetchone()
                project_id = previous["project_id"] if previous else str(uuid.uuid4())
                chosen_parent = parent if parent is not None else previous["parent_id"] if previous else None
                ancestor = chosen_parent
                seen = {project_id}
                while ancestor:
                    if ancestor in seen:
                        raise BrainError("A relação entre projetos formaria um ciclo.")
                    seen.add(ancestor)
                    ancestor = self.project(conn, ancestor)["parent_id"]
                if previous:
                    conn.execute("UPDATE projects SET name = ?, parent_id = ? WHERE project_id = ?", (name, chosen_parent, project_id))
                else:
                    entry, vault, index, decisions = self.detect_layout(root)
                    conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (project_id, name, str(root), chosen_parent, entry, vault, index, decisions, now()))
                conn.execute("DELETE FROM checkpoints WHERE project_id = ?", (project_id,))
            with self.connection() as conn:
                row = self.project(conn, project_id)
                last_seq, _ = self.project_documents(conn, row)
                self.central_index(conn)
                conn.execute("INSERT INTO checkpoints VALUES (?, ?, ?)", (project_id, last_seq, now()))
                return self.public_project(row)

    def list(self):
        if not self.initialized():
            return []
        with self.connection(readonly=True) as conn:
            return [self.public_project(row) for row in conn.execute("SELECT * FROM projects ORDER BY name, project_id")]

    def resolve(self, conn, path):
        current = Path(path).expanduser().resolve()
        candidates = [row for row in conn.execute("SELECT * FROM projects")
                      if current == Path(row["path"]) or Path(row["path"]) in current.parents]
        if not candidates:
            raise BrainError("Nenhum projeto registrado contém este caminho.")
        return max(candidates, key=lambda row: len(Path(row["path"]).parts))

    def context(self, path=None, project_id=None):
        with self.connection(readonly=True) as conn:
            row = self.project(conn, project_id) if project_id else self.resolve(conn, path or os.getcwd())
            parents, ancestor, visited = [], row["parent_id"], {row["project_id"]}
            while ancestor:
                if ancestor in visited:
                    raise BrainError("Relação de projetos inválida no registro.")
                visited.add(ancestor)
                parent = self.project(conn, ancestor)
                parents.append(self.public_project(parent))
                ancestor = parent["parent_id"]
            recent = [self.event_summary(event) for event in conn.execute(
                "SELECT * FROM events WHERE project_id = ? ORDER BY seq DESC LIMIT 10", (row["project_id"],))]
            return {"project": self.public_project(row), "parents": parents,
                    "brain_excerpt": output_text(read_text(Path(row["path"]), row["brain_rel"]))[:8000],
                    "recent_events": recent, "pending_events": self.pending(conn, row["project_id"])}

    @staticmethod
    def validate_event(event):
        if not isinstance(event, dict):
            raise BrainError("Cada evento deve ser um objeto JSON.")
        required = {"event_id", "project_id", "kind", "occurred_at", "source", "source_ref", "payload"}
        optional = {"schema_version", "session_id", "source_event_id"}
        if not required <= event.keys() or event.keys() - required - optional:
            raise BrainError("Campos do envelope de evento inválidos.")
        if event.get("schema_version", 1) != 1:
            raise BrainError("Versão de evento não suportada.")
        if contains_secret(event):
            raise BrainError("Entrada recusada: possível segredo; conteúdo omitido.")
        identifier = validate_text(event["event_id"], 160, single_line=True)
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", identifier):
            raise BrainError("Identificador de evento inválido.")
        valid_uuid(event["project_id"])
        if not isinstance(event["kind"], str) or not isinstance(event["source"], str) or event["kind"] not in KINDS or event["source"] not in SOURCES:
            raise BrainError("Tipo ou origem de evento não suportado.")
        validate_text(event["source_ref"], 2048, single_line=True)
        validate_text(event["occurred_at"], 80, single_line=True)
        try:
            occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            if occurred.tzinfo is None:
                raise ValueError
        except ValueError:
            raise BrainError("occurred_at deve ser uma data ISO-8601 com fuso horário.") from None
        payload = event["payload"]
        if not isinstance(payload, dict):
            raise BrainError("payload deve ser um objeto JSON.")
        validate_text(payload.get("title"), 240, single_line=True)
        validate_text(payload.get("body"), 64000, empty=True)
        if event["kind"] == "decision.superseded":
            validate_text(payload.get("supersedes"), 160, single_line=True)
            validate_text(payload.get("replacement"), 160, single_line=True)
            if payload["supersedes"] == payload["replacement"]:
                raise BrainError("Decisão antiga e substituta precisam ser diferentes.")
        if event["kind"] == "push.completed":
            validate_text(payload.get("remote"), 1024, single_line=True)
            validate_text(payload.get("revision"), 160, single_line=True)
        if event["kind"] == "publication.completed":
            url = validate_text(payload.get("url"), 2048, single_line=True)
            validate_text(payload.get("revision"), 160, single_line=True)
            try:
                parsed = urlsplit(url)
                _ = parsed.port
                valid_url = (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                             and not parsed.username and not parsed.password and not any(c.isspace() for c in url))
            except ValueError:
                valid_url = False
            if not valid_url:
                raise BrainError("Publicação exige URL HTTP(S) sem credenciais.")
        for key in ("session_id", "source_event_id"):
            if key in event:
                validate_text(event[key], 240, single_line=True)
        try:
            canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise BrainError("Evento contém valores JSON inválidos.") from None
        if len(canonical.encode("utf-8")) > 128 * 1024:
            raise BrainError("Evento excede o limite de tamanho.")
        if MARKER in canonical:
            raise BrainError("Conteúdo contém marcadores reservados.")
        return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record(self, document):
        events = document if isinstance(document, list) else [document]
        if not events:
            return {"inserted": 0, "duplicates": 0, "event_ids": []}
        if len(events) > MAX_EVENTS:
            raise BrainError("Forneça no máximo 500 eventos.")
        validated = [(event, *self.validate_event(event)) for event in events]
        inserted, duplicates, event_ids = 0, 0, []
        with self.writer(), self.connection() as conn:
            for event, canonical, digest in validated:
                self.project(conn, event["project_id"])
                prior = conn.execute("SELECT content_hash FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
                if prior:
                    if prior["content_hash"] != digest:
                        raise BrainError("Identificador de evento já existe com conteúdo diferente.")
                    duplicates += 1
                else:
                    payload = event["payload"]
                    if event["kind"] == "decision.superseded":
                        accepted = conn.execute("SELECT event_id, kind, project_id FROM events WHERE event_id IN (?, ?)",
                                                (payload["supersedes"], payload["replacement"])).fetchall()
                        if (len(accepted) != 2 or any(row["kind"] != "decision.accepted" or row["project_id"] != event["project_id"]
                                                      for row in accepted)):
                            raise BrainError("Substituição exige duas decisões aceitas deste projeto.")
                        replacements = {}
                        for row in conn.execute("SELECT payload_json FROM events WHERE project_id = ? AND kind = ?",
                                                (event["project_id"], "decision.superseded")):
                            prior_payload = json.loads(row["payload_json"])
                            old, replacement = prior_payload.get("supersedes"), prior_payload.get("replacement")
                            if old and replacement:
                                replacements[old] = replacement
                        if payload["supersedes"] in replacements:
                            raise BrainError("Esta decisão já foi substituída.")
                        cursor = payload["replacement"]
                        while cursor in replacements:
                            cursor = replacements[cursor]
                            if cursor == payload["supersedes"]:
                                raise BrainError("Substituições formariam um ciclo.")
                    conn.execute("""INSERT INTO events
                        (event_id, project_id, kind, occurred_at, source, source_ref, title, body, payload_json, event_json, content_hash, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                 (event["event_id"], event["project_id"], event["kind"], event["occurred_at"], event["source"], event["source_ref"],
                                  payload["title"], payload["body"], json.dumps(payload, ensure_ascii=False, sort_keys=True), canonical, digest, now()))
                    inserted += 1
                event_ids.append(event["event_id"])
        return {"inserted": inserted, "duplicates": duplicates, "event_ids": event_ids}

    @staticmethod
    def note_rel(row, event):
        digest = hashlib.sha256(event["event_id"].encode("utf-8")).hexdigest()[:32]
        return f"{row['vault_rel']}/98-HeBe-Events/Evento-{digest}.md"

    @staticmethod
    def event_summary(event):
        return {key: event[key] for key in ("event_id", "project_id", "kind", "occurred_at", "source", "source_ref", "title", "body")}

    def project_documents(self, conn, row):
        root, project_id = Path(row["path"]), row["project_id"]
        events = conn.execute("SELECT * FROM events WHERE project_id = ? ORDER BY seq", (project_id,)).fetchall()
        superseded, legacy_superseded = {}, {}
        for event in events:
            if event["kind"] != "decision.superseded":
                continue
            payload = json.loads(event["payload_json"])
            old, replacement = payload.get("supersedes"), payload.get("replacement")
            if old and replacement:
                superseded[old] = replacement
            elif old:
                # v0.6 accepted only the old decision id. Preserve the event without
                # inventing which accepted decision became current.
                legacy_superseded[old] = event["event_id"]
        links = []
        for event in events:
            relative = self.note_rel(row, event)
            metadata = {key: value for key, value in json.loads(event["payload_json"]).items() if key not in {"title", "body"}}
            details = [f"# {event['title']}", "", f"- Evento: `{event['event_id']}`",
                       f"- Tipo: `{event['kind']}`", f"- Ocorrido em: {event['occurred_at']}",
                       f"- Origem: `{event['source']}`", f"- Referência: {event['source_ref']}",
                       f"- Projeto: `{project_id}`", "", event["body"], "", "## Metadados", "",
                       "```json", json.dumps(metadata, ensure_ascii=False, indent=2), "```"]
            managed(root, relative, "event", "\n".join(details), "")
            links.append((event, relative))
        decisions = ["## Decisões registradas pelo HeBe Brain", ""]
        accepted = [(event, rel) for event, rel in links if event["kind"] == "decision.accepted"]
        accepted_by_id = {event["event_id"]: (event, rel) for event, rel in accepted}
        for event, rel in accepted:
            label = local_link(event["title"], root / rel, (root / row["decisions_rel"]).parent)
            if event["event_id"] in superseded:
                replacement, replacement_rel = accepted_by_id[superseded[event["event_id"]]]
                state = "substituída por " + local_link(replacement["title"], root / replacement_rel,
                                                       (root / row["decisions_rel"]).parent)
            elif event["event_id"] in legacy_superseded:
                state = ("substituição legada sem decisão vigente vinculada; revisar evento `"
                         + legacy_superseded[event["event_id"]] + "`")
            else:
                state = "aceita"
            decisions += [f"### {label}", "", f"- Data: {event['occurred_at']} · Estado: {state}",
                          f"- Evento: `{event['event_id']}` · Origem: `{event['source']}` · Referência: {event['source_ref']}", ""]
        if not accepted:
            decisions.append("Nenhuma decisão aceita registrada por este núcleo.")
        managed(root, row["decisions_rel"], "decisions", "\n".join(decisions), "# Registro de Decisões\n")
        entry_parent = (root / row["brain_rel"]).parent
        overview = ["## Estado do projeto", "", f"Projeto: **{row['name']}** · ID: `{project_id}`", "",
                    local_link("Registro de Decisões", root / row["decisions_rel"], entry_parent),
                    "", f"Eventos: {len(events)} · Decisões aceitas: {len(accepted)}.", "",
                    "## Atividade recente", ""]
        for event, rel in links[-8:][::-1]:
            overview.append(f"- {event['occurred_at']} · `{event['kind']}` · " + local_link(event["title"], root / rel, entry_parent))
        if not events:
            overview.append("Nenhum evento registrado.")
        managed(root, row["brain_rel"], "overview", "\n".join(overview), f"# Brain — {row['name']}\n")
        if row["index_rel"] != row["brain_rel"]:
            index_parent = (root / row["index_rel"]).parent
            index_lines = ["## Índice do HeBe Brain", "",
                           "- " + local_link("Brain", root / row["brain_rel"], index_parent),
                           "- " + local_link("Registro de Decisões", root / row["decisions_rel"], index_parent)]
            index_lines += ["- " + local_link(event["title"], root / rel, index_parent) for event, rel in links]
            managed(root, row["index_rel"], "index", "\n".join(index_lines), "# Índice do Vault\n")
        commits = [(event, rel) for event, rel in links if event["kind"] == "commit.created"]
        if commits:
            commit_rel = f"{row['vault_rel']}/04-Engenharia/Commits.md"
            commit_lines = ["## Commits locais registrados", "", "Este registro não confirma push ou publicação remota.", ""]
            commit_lines += [f"- `{event['source_ref']}` · {event['occurred_at']} · "
                             + local_link(event["title"], root / rel, (root / commit_rel).parent) for event, rel in commits]
            managed(root, commit_rel, "commits", "\n".join(commit_lines), "# Histórico de commits\n")
        deliveries = [(event, rel) for event, rel in links if event["kind"] in {"push.completed", "publication.completed"}]
        if deliveries:
            delivery_rel = f"{row['vault_rel']}/04-Engenharia/Entregas.md"
            delivery_lines = ["## Pushes e publicações registrados", ""]
            for event, rel in deliveries:
                payload = json.loads(event["payload_json"])
                destination = payload["remote"] if event["kind"] == "push.completed" else payload["url"]
                delivery_lines.append(f"- `{event['kind']}` · {event['occurred_at']} · revisão `{payload['revision']}`"
                                      + f" · destino {destination} · "
                                      + local_link(event["title"], root / rel, (root / delivery_rel).parent))
            managed(root, delivery_rel, "deliveries", "\n".join(delivery_lines), "# Histórico de entregas\n")
        return max((event["seq"] for event in events), default=0), len(events)

    def consolidate(self, project_id=None):
        completed = []
        with self.writer(), self.connection() as conn:
            projects = [self.project(conn, project_id)] if project_id else conn.execute("SELECT * FROM projects ORDER BY project_id").fetchall()
            for row in projects:
                last_seq, count = self.project_documents(conn, row)
                stamp = now()
                conn.execute("""INSERT INTO checkpoints VALUES (?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET last_seq=excluded.last_seq, consolidated_at=excluded.consolidated_at""",
                             (row["project_id"], last_seq, stamp))
                completed.append({"project_id": row["project_id"], "events": count, "last_seq": last_seq})
            self.central_index(conn)
        return {"projects": completed, "pending_events": self.status()["pending_events"]}

    def search(self, query, project_id=None, limit=20):
        validate_text(query, 200)
        if not 1 <= limit <= 100:
            raise BrainError("Limite de busca deve estar entre 1 e 100.")
        with self.connection(readonly=True) as conn:
            args = ()
            sql = "SELECT * FROM events"
            if project_id:
                self.project(conn, project_id)
                sql += " WHERE project_id = ?"
                args = (project_id,)
            sql += " ORDER BY seq DESC"
            results, needle = [], query.casefold()
            for event in conn.execute(sql, args):
                if needle in (event["title"] + "\n" + event["body"]).casefold():
                    results.append(self.event_summary(event))
                    if len(results) >= limit:
                        break
            return results


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BrainError("JSON contém chave duplicada.")
        result[key] = value
    return result


def read_events(filename):
    if filename == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    else:
        with open(filename, "rb") as stream:
            raw = stream.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise BrainError("Entrada JSON excede 2 MiB.")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(BrainError("Número JSON inválido.")))
    except (ValueError, UnicodeError, RecursionError):
        raise BrainError("Entrada JSON inválida; conteúdo omitido.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, help="Raiz central explícita; nenhuma pasta pessoal é escolhida automaticamente.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "status", "list"):
        sub.add_parser(command)
    register = sub.add_parser("register")
    register.add_argument("--path", required=True)
    register.add_argument("--name", required=True)
    register.add_argument("--parent")
    context = sub.add_parser("context")
    context_target = context.add_mutually_exclusive_group()
    context_target.add_argument("--path")
    context_target.add_argument("--project")
    record = sub.add_parser("record")
    record.add_argument("--file", default="-", help="Objeto/lista JSON; '-' lê stdin (padrão).")
    consolidate = sub.add_parser("consolidate")
    consolidate.add_argument("--project")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--project")
    search.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        brain = Brain(args.home)
        if args.command in {"init", "status", "list"}:
            result = getattr(brain, args.command)()
        elif args.command == "register":
            result = brain.register(args.path, args.name, args.parent)
        elif args.command == "context":
            result = brain.context(args.path, args.project)
        elif args.command == "record":
            result = brain.record(read_events(args.file))
        elif args.command == "consolidate":
            result = brain.consolidate(args.project)
        else:
            result = brain.search(args.query, args.project, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except BrainError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, UnicodeError, ValueError, TypeError, RecursionError):
        print(json.dumps({"error": "Operação local recusada ou indisponível; confira os caminhos e o formato, sem expor conteúdo."}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
