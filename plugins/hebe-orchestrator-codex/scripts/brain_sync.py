#!/usr/bin/env python3
"""Explicit HeBe Brain snapshots, safe recovery and Git synchronization.

No tokens, repository creation or implicit scheduler activation. Authentication
belongs to Git's existing credential helper / SSH agent. ``restore`` is a plan
until --apply is provided and never overwrites a differing destination file.
"""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import quote, urlsplit
import uuid

try:
    import fcntl
except ImportError:  # Foreground operation also supports Windows.
    fcntl = None
    import msvcrt


VERSION = 1
FORMAT = "hebe-brain-snapshot"
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 50000
DOC_EXTENSIONS = {".md", ".markdown", ".txt", ".canvas", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".canvas", ".svg"}
SECRET_NAME = re.compile(r"(?:^|[-_.])(?:credentials?|secrets?|tokens?|password|passwd|senha|private[-_]?key)(?:[-_.]|$)", re.I)
SECRET_PATTERNS = [
    re.compile(r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{12,})"),
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.I),
    re.compile(r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@", re.I),
    re.compile(r"\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|PASSWD|SENHA|SERVICE_ROLE_KEY)\s*[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_./+!@$%-]{8,})", re.I),
]
PLACEHOLDERS = {"redacted", "redigido", "example", "changeme", "placeholder"}
DIGEST = re.compile(r"[0-9a-f]{64}")
LABEL = "digital.hebe.brain-sync"

# A data-only format avoids arbitrary SQL execution and deleted SQLite pages.
# Unknown tables/columns/versions fail closed instead of producing an incomplete
# backup after a runtime schema upgrade.
TABLES = {
    "brain": {
        "projects": ("project_id", "name", "path", "parent_id", "brain_rel", "vault_rel", "index_rel", "decisions_rel", "created_at"),
        "events": ("seq", "event_id", "project_id", "kind", "occurred_at", "source", "source_ref", "title", "body", "payload_json", "event_json", "content_hash", "recorded_at"),
        "checkpoints": ("project_id", "last_seq", "consolidated_at"),
    },
    "orchestrator": {
        "deliveries": ("delivery_id", "project_id", "state", "revision", "data_json", "created_at", "updated_at"),
        "checkpoints": ("delivery_id", "revision", "event_json", "applied_at"),
    },
}
SCHEMAS = {
    "brain": """
CREATE TABLE projects (project_id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
 parent_id TEXT REFERENCES projects(project_id), brain_rel TEXT NOT NULL, vault_rel TEXT NOT NULL,
 index_rel TEXT NOT NULL, decisions_rel TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
 project_id TEXT NOT NULL REFERENCES projects(project_id), kind TEXT NOT NULL, occurred_at TEXT NOT NULL,
 source TEXT NOT NULL, source_ref TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 payload_json TEXT NOT NULL, event_json TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE INDEX events_project_seq ON events(project_id, seq);
CREATE TABLE checkpoints (project_id TEXT PRIMARY KEY REFERENCES projects(project_id), last_seq INTEGER NOT NULL,
 consolidated_at TEXT NOT NULL);
PRAGMA user_version=1;
""",
    "orchestrator": """
CREATE TABLE deliveries (delivery_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL,
 revision INTEGER NOT NULL, data_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX active_project ON deliveries(project_id) WHERE state='active';
CREATE TABLE checkpoints (delivery_id TEXT NOT NULL REFERENCES deliveries(delivery_id), revision INTEGER NOT NULL,
 event_json TEXT NOT NULL, applied_at TEXT, PRIMARY KEY(delivery_id, revision));
PRAGMA user_version=1;
""",
}


class SyncError(Exception):
    """Static public diagnostic; never include Git output or source contents."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def secret_check(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if match.lastindex and (match.group(1).lower() in PLACEHOLDERS or match.group(1).lower().startswith("your_")):
                continue
            raise SyncError("Possível segredo recusado; conteúdo omitido.")


def canonical(value):
    secret_check(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SyncError("JSON contém chave duplicada.")
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise SyncError("JSON inválido; conteúdo omitido.") from None
    secret_check(result)
    return result


def absolute(value):
    path = Path(os.path.abspath(Path(value).expanduser()))
    secret_check(str(path))
    # Do not canonicalize a caller-controlled symlink into an allowed directory.
    for part in (path, *path.parents):
        if part.is_symlink():
            raise SyncError("Links simbólicos não são permitidos nos caminhos selecionados.")
    return path


def relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value)):
        raise SyncError("Caminho relativo inválido.")
    parts = value.split("/")
    if any(not p or p in {".", ".."} or p != p.strip() for p in parts) or PurePosixPath(value).is_absolute():
        raise SyncError("Caminho relativo fora do snapshot.")
    return value


def safe(root, rel):
    relative(rel)
    root = absolute(root)
    path = root
    parts = rel.split("/")
    for index, part in enumerate(parts):
        path /= part
        if path.is_symlink():
            raise SyncError("Link simbólico em caminho gerenciado.")
        if index < len(parts) - 1 and path.exists() and not path.is_dir():
            raise SyncError("Um arquivo ocupa o lugar de uma pasta gerenciada.")
    return path


def regular(info, *, private=False):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SyncError("Arquivo gerenciado deve ser regular e não pode ter hard links.")
    if private and os.name != "nt" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise SyncError("Configuração e estado local devem pertencer ao usuário e ter permissão 0600.")


@contextlib.contextmanager
def directory(path, *, create=False):
    """Pin each POSIX ancestor: replacing a directory cannot redirect writes.

    Windows lacks dir_fd. There, reject every observed symlink and use exclusive
    file creation; hostile simultaneous filesystem changes remain out of scope.
    """
    path = absolute(path)
    if os.open not in os.supports_dir_fd:
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        absolute(path)
        if not path.is_dir():
            raise SyncError("Pasta gerenciada ausente.")
        yield None
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_bytes(path, *, private=False, maximum=MAX_FILE):
    path = absolute(path)
    with directory(path.parent) as parent:
        fd = os.open(path.name if parent is not None else path,
                     os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        regular(before, private=private)
        if before.st_size > maximum:
            raise SyncError("Arquivo excede o limite do snapshot.")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        if len(data) > maximum or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise SyncError("Arquivo mudou durante a leitura; repita o snapshot.")
    return data


def fsync_directory(path):
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bytes(path, data):
    path = absolute(path)
    with directory(path.parent, create=True) as parent:
        name = path.name if parent is not None else path
        if path.exists() and read_bytes(path) == data:
            return False
        temporary = ".hebe-sync-" + uuid.uuid4().hex
        if parent is None:
            temporary = path.parent / temporary
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            if parent is not None:
                os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    return True


def create_bytes(path, data):
    """Atomically install a complete file, failing if any destination exists."""
    path = absolute(path)
    with directory(path.parent, create=True) as parent:
        temporary = ".hebe-sync-" + uuid.uuid4().hex
        name = path.name if parent is not None else path
        if parent is None:
            temporary = path.parent / temporary
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.unlink(temporary, dir_fd=parent)
            if parent is not None:
                os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


@contextlib.contextmanager
def lock(path, *, wait=False):
    path = absolute(path)
    with directory(path.parent, create=True) as parent:
        fd = os.open(path.name if parent is not None else path,
                     os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent)
    try:
        regular(os.fstat(fd), private=True)
        try:
            if fcntl:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            else:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
        except (OSError, BlockingIOError):
            raise SyncError("Outra operação usa este Brain ou checkout; tente novamente depois.") from None
        yield
    finally:
        os.close(fd)


def git(checkout, *args, check=True):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", GIT_SSH_COMMAND="ssh -oBatchMode=yes",
               GIT_ATTR_NOSYSTEM="1")
    result = subprocess.run(["git", "--literal-pathspecs", "-c", "core.hooksPath=" + os.devnull,
                             "-c", "protocol.ext.allow=never", "-c", "push.followTags=false",
                             "-c", "core.attributesFile=" + os.devnull,
                             "-c", "core.autocrlf=false",
                             "-C", str(checkout), *args], capture_output=True, timeout=60, env=env)
    if check and result.returncode:
        raise SyncError("Operação Git falhou; diagnóstico externo omitido para proteger dados.")
    return result


def compatible_roots(checkout, roots):
    for root in roots:
        if checkout == root or checkout in root.parents or root in checkout.parents:
            raise SyncError("O checkout deve ser dedicado e separado da central e de todos os projetos.")


def remote_url(checkout, remote):
    raw = git(checkout, "remote", "get-url", "--push", "--all", remote).stdout.decode("utf-8").splitlines()
    if len(raw) != 1 or not raw[0] or any(ord(c) < 32 for c in raw[0]):
        raise SyncError("Configure exatamente um destino de push para o remoto.")
    url = raw[0]
    secret_check(url)
    if url.startswith("-") or "::" in url:
        raise SyncError("Protocolo Git não permitido.")
    if "://" in url:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"https", "ssh", "file"} or parsed.password or parsed.query or parsed.fragment
                or (parsed.username and not (parsed.scheme == "ssh" and parsed.username == "git"))):
            raise SyncError("Remoto não pode conter credenciais; use o helper Git ou agente SSH.")
    elif ":" in url and not (os.name == "nt" and Path(url).is_absolute()):
        if not re.fullmatch(r"(?:git@)?[A-Za-z0-9.-]+:[A-Za-z0-9._/~/-]+", url):
            raise SyncError("Remoto SSH inválido ou com usuário não permitido.")
    return url


def destination_kind(url):
    if "://" in url:
        return "local" if urlsplit(url).scheme == "file" else "remote"
    return "remote" if ":" in url and not (os.name == "nt" and Path(url).is_absolute()) else "local"


def authorized_destination(config):
    """Return the checked URL itself, never a mutable remote name for push."""
    checkout = absolute(config["checkout"])
    url = remote_url(checkout, config["remote"])
    if (hashlib.sha256(url.encode("utf-8")).hexdigest() != config["destination_url_sha256"]
            or destination_kind(url) != config["destination_kind"]):
        raise SyncError("Destino Git mudou; configure novamente e confirme a autorização para o novo destino.")
    # get-url has already applied Git's URL rewriting. Passing that URL to push
    # applies rewriting again, so a chained insteadOf rule could change the
    # approved destination. Refuse any applicable non-identity second rewrite;
    # this conservative check also covers pushInsteadOf without contacting Git.
    rules = git(checkout, "config", "--null", "--get-regexp", r"^url\..*\.(pushinsteadof|insteadof)$", check=False)
    if rules.returncode not in (0, 1):
        raise SyncError("Não foi possível conferir as reescritas do destino Git.")
    for record in rules.stdout.decode("utf-8").split("\0"):
        if not record:
            continue
        key, separator, prefix = record.partition("\n")
        if not separator:
            raise SyncError("Regra de reescrita Git inválida.")
        suffix = ".pushinsteadof" if key.endswith(".pushinsteadof") else ".insteadof"
        base = key[len("url."):-len(suffix)]
        if url.startswith(prefix) and base + url[len(prefix):] != url:
            raise SyncError("Reescritas Git encadeadas alteram o destino; configure a URL final antes do sync.")
    return url


def validate_checkout(config, *, check_destination=True):
    checkout = absolute(config["checkout"])
    if not checkout.is_dir() or not safe(checkout, ".git").is_dir():
        raise SyncError("Selecione a raiz de um checkout Git dedicado; worktrees não são aceitas.")
    top = git(checkout, "rev-parse", "--show-toplevel").stdout.decode("utf-8").strip()
    if absolute(top) != checkout:
        raise SyncError("Destino deve ser a raiz do checkout Git dedicado.")
    branch = git(checkout, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.decode("utf-8").strip()
    if branch != config["branch"]:
        raise SyncError("O checkout precisa estar na branch configurada.")
    allowed = {".git", "snapshots", "CURRENT.json"}
    if any(p.name not in allowed or p.is_symlink() for p in checkout.iterdir()):
        raise SyncError("Checkout exclusivo aceita somente .git, snapshots e CURRENT.json.")
    tracked = git(checkout, "ls-files", "-z").stdout.decode("utf-8").split("\0")
    if any(p and p != "CURRENT.json" and not p.startswith("snapshots/") for p in tracked):
        raise SyncError("Há arquivos de outro escopo rastreados no checkout.")
    if (any(".gitattributes" in p.split("/") for p in tracked)
            or safe(checkout, "snapshots/.gitattributes").exists()):
        raise SyncError("Checkout de backup não pode conter regras .gitattributes.")
    attributes = safe(checkout, ".git/info/attributes")
    if attributes.exists() and read_bytes(attributes).strip():
        raise SyncError("Checkout de backup não pode aplicar filtros Git locais aos snapshots.")
    if check_destination:
        authorized_destination(config)
    else:
        remote_url(checkout, config["remote"])
    return checkout


def default_config():
    return Path.home() / ".config/hebe-brain/sync.json"


def validate_config(data):
    keys = {"schema_version", "brain_home", "checkout", "remote", "branch", "interval_seconds",
            "destination_kind", "destination_url_sha256", "private_destination_confirmed"}
    if (not isinstance(data, dict) or set(data) != keys
            or type(data["schema_version"]) is not int or data["schema_version"] != VERSION):
        raise SyncError("Configuração de sync desconhecida; tokens e campos adicionais não são aceitos.")
    secret_check(data)
    if (not isinstance(data["remote"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", data["remote"])
            or not isinstance(data["branch"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", data["branch"])):
        raise SyncError("Nome de remoto ou branch inválido.")
    if type(data["interval_seconds"]) is not int or not 30 <= data["interval_seconds"] <= 86400:
        raise SyncError("Intervalo deve estar entre 30 e 86400 segundos.")
    if (data["destination_kind"] not in {"local", "remote"} or type(data["private_destination_confirmed"]) is not bool
            or not isinstance(data["destination_url_sha256"], str) or not DIGEST.fullmatch(data["destination_url_sha256"])):
        raise SyncError("Política do destino Git inválida.")
    if data["destination_kind"] == "remote" and not data["private_destination_confirmed"]:
        raise SyncError("Destino remoto exige confirmação explícita de privacidade; o CLI não verifica visibilidade.")
    for key in ("brain_home", "checkout"):
        if not isinstance(data[key], str) or not Path(data[key]).is_absolute():
            raise SyncError("Configuração exige caminhos absolutos.")
        absolute(data[key])
    compatible_roots(absolute(data["checkout"]), [absolute(data["brain_home"])])
    return data


def load_config(path=None):
    return validate_config(parse_json(read_bytes(absolute(path or default_config()), private=True, maximum=16384)))


def configure(path, brain_home, checkout, remote="origin", branch="main", interval_seconds=300, *, confirm_private=False):
    target = absolute(path or default_config())
    config = validate_config({"schema_version": VERSION, "brain_home": str(absolute(brain_home)),
                              "checkout": str(absolute(checkout)), "remote": remote,
                              "branch": branch, "interval_seconds": interval_seconds,
                              "destination_kind": "local", "destination_url_sha256": "0" * 64,
                              "private_destination_confirmed": False})
    repo = validate_checkout(config, check_destination=False)
    url = remote_url(repo, remote)
    config.update(destination_kind=destination_kind(url), destination_url_sha256=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                  private_destination_confirmed=bool(confirm_private) if destination_kind(url) == "remote" else False)
    validate_config(config)
    home = absolute(config["brain_home"])
    if not safe(home, ".state/brain.sqlite3").is_file():
        raise SyncError("Central precisa estar inicializada antes da configuração do sync.")
    with source_locks(home):
        data = database_export(safe(home, ".state/brain.sqlite3"), "brain")
        roots = [home, *(absolute(row["path"]) for row in data["tables"]["projects"])]
        compatible_roots(repo, roots)
    if any(target == root or root in target.parents for root in [repo, *roots]):
        raise SyncError("Guarde a configuração privada fora do checkout, da central e dos projetos.")
    if target.exists():
        read_bytes(target, private=True)
    write_bytes(target, canonical(config))
    return {"configured": True, "config": str(target), "scheduler_active": False,
            "destination_kind": config["destination_kind"],
            "private_destination_confirmed_by_user": config["private_destination_confirmed"],
            "privacy_verified_by_cli": False}


@contextlib.contextmanager
def source_locks(home, *, create=False):
    # Same ordering as orchestrator.checkpoint -> Brain.record/consolidate.
    if not create and not safe(home, ".state/brain.sqlite3").is_file():
        raise SyncError("Central ausente ou não inicializada.")
    with lock(safe(home, ".state/orchestrator.lock")), lock(safe(home, ".state/writer.lock")):
        yield


def validate_database_data(data, name):
    if (not isinstance(data, dict) or set(data) != {"schema_version", "database", "tables", "sequences"}
            or type(data["schema_version"]) is not int or data["schema_version"] != VERSION or data["database"] != name
            or not isinstance(data["tables"], dict) or set(data["tables"]) != set(TABLES[name])):
        raise SyncError("Estado do banco usa formato ou versão desconhecidos.")
    for table, columns in TABLES[name].items():
        rows = data["tables"][table]
        if not isinstance(rows, list) or len(rows) > 100000:
            raise SyncError("Tabela de estado excede o limite.")
        for row in rows:
            if (not isinstance(row, dict) or set(row) != set(columns)
                    or any(value is not None and type(value) not in (str, int) for value in row.values())):
                raise SyncError("Registro de estado inválido.")
            for column, value in row.items():
                if value is None and column in {"parent_id", "applied_at"}:
                    continue
                if column in {"seq", "last_seq", "revision"}:
                    if type(value) is not int or not 0 <= value <= 9223372036854775807:
                        raise SyncError("Número de sequência ou revisão inválido.")
                elif not isinstance(value, str):
                    raise SyncError("Tipo de campo de estado inválido.")
                if column.endswith("_json"):
                    parse_json(value)
    sequences = data["sequences"]
    if (not isinstance(sequences, dict) or set(sequences) - ({"events"} if name == "brain" else set())
            or any(type(value) is not int or not 0 <= value <= 9223372036854775807 for value in sequences.values())):
        raise SyncError("Sequência SQLite inválida.")
    if name == "brain":
        for row in data["tables"]["projects"]:
            try:
                if str(uuid.UUID(row["project_id"])) != row["project_id"]:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise SyncError("Identidade de projeto inválida no snapshot.") from None
            if not isinstance(row["path"], str) or not Path(row["path"]).is_absolute():
                raise SyncError("Registro de projeto exige origem absoluta.")
            for key in ("brain_rel", "vault_rel", "index_rel", "decisions_rel"):
                relative(row[key])
                if any(part.startswith(".") for part in row[key].split("/")):
                    raise SyncError("Layout de estado não pode apontar para arquivos ocultos.")
            if row["vault_rel"] not in {"vault", "brain"}:
                raise SyncError("Layout de vault desconhecido.")
            if row["brain_rel"] != "Brain.md" and not row["brain_rel"].startswith(row["vault_rel"] + "/"):
                raise SyncError("Entrada Brain está fora do layout permitido.")
            for key in ("index_rel", "decisions_rel"):
                if not row[key].startswith(row["vault_rel"] + "/") or not row[key].endswith(".md"):
                    raise SyncError("Índice e decisões devem permanecer no vault documental.")
    secret_check(data)
    return data


def database_export(path, name):
    """Copy through no-follow descriptors before allowing SQLite to reopen.

    Callers hold the source runtime locks. SQLite's path-based API cannot accept
    those descriptors, so use a private copy of the main file and transaction
    files, then check that every original still has the same identity/version.
    This also limits disk/memory use before SQLite examines external state.
    """
    path = absolute(path)
    with tempfile.TemporaryDirectory(prefix="hebe-database-export-") as temporary:
        copied = Path(temporary).resolve() / path.name
        signatures = {}
        total = 0
        for suffix in ("", "-wal", "-shm", "-journal"):
            source = absolute(str(path) + suffix)
            try:
                before = source.lstat()
            except FileNotFoundError:
                if not suffix:
                    raise
                signatures[source] = None
                continue
            regular(before)
            data = read_bytes(source)
            total += len(data)
            if total > MAX_TOTAL:
                raise SyncError("Banco e arquivos de transação excedem o limite do snapshot.")
            signatures[source] = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            create_bytes(Path(str(copied) + suffix), data)
        for source, before in signatures.items():
            try:
                after = absolute(source).lstat()
                observed = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            except FileNotFoundError:
                observed = None
            if before != observed:
                raise SyncError("Banco mudou durante a cópia; repita o snapshot.")
        return _database_export_copy(copied, name)


def _database_export_copy(path, name):
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.execute("BEGIN")
        if conn.execute("PRAGMA user_version").fetchone()[0] != VERSION:
            raise SyncError("Versão SQLite não suportada; exportação recusada.")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone():
            raise SyncError("Banco de origem falhou na verificação de integridade.")
        tables = conn.execute("SELECT name,type,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','view','trigger')").fetchall()
        if (set(row["name"] for row in tables) != set(TABLES[name])
                or any(row["type"] != "table" or "VIRTUAL" in row["sql"].upper() for row in tables)):
            raise SyncError("Banco tem estruturas desconhecidas; atualização do exportador necessária.")
        result = {"schema_version": VERSION, "database": name, "tables": {}, "sequences": {}}
        for table, columns in TABLES[name].items():
            observed = tuple(row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")'))
            if observed != columns:
                raise SyncError("Colunas SQLite desconhecidas; exportação recusada.")
            result["tables"][table] = [dict(row) for row in conn.execute(
                f'SELECT * FROM "{table}" ORDER BY ' + ",".join('"' + col + '"' for col in columns) + " LIMIT 100001")]
            if len(result["tables"][table]) > 100000:
                raise SyncError("Tabela de estado excede o limite.")
        if name == "brain":
            result["sequences"] = dict(conn.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name"))
        return validate_database_data(result, name)
    finally:
        conn.close()


def database_import(path, data, name):
    validate_database_data(data, name)
    if path.exists():
        raise SyncError("Restauração não substitui um banco existente.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMAS[name])
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA defer_foreign_keys=ON")
        for table, columns in TABLES[name].items():
            parameters = ",".join("?" for _ in columns)
            conn.executemany(f'INSERT INTO "{table}" VALUES ({parameters})',
                             [tuple(row[col] for col in columns) for row in data["tables"][table]])
        if name == "brain":
            conn.execute("DELETE FROM sqlite_sequence")
            conn.executemany("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", data["sequences"].items())
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise SyncError("Relações do estado não passaram na verificação.")
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SyncError("Banco restaurado não passou na verificação.")
    finally:
        conn.close()
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def documents(root, brain_rel, vault_rel):
    selected, excluded, signatures = {}, 0, {}
    total = 0
    def visit(path):
        nonlocal excluded, total
        path = absolute(path)
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            signatures[path] = (info.st_ino, info.st_mtime_ns, info.st_size)
            for child in sorted(path.iterdir()):
                if child.is_symlink():
                    raise SyncError("Vault contém link simbólico; exportação recusada.")
                if child.name.startswith(".") or SECRET_NAME.search(child.name):
                    excluded += 1
                    continue
                visit(child)
        elif stat.S_ISREG(info.st_mode):
            if path.suffix.lower() not in DOC_EXTENSIONS or SECRET_NAME.search(path.name):
                excluded += 1
                return
            regular(info)
            raw = read_bytes(path)
            total += len(raw)
            if total > MAX_TOTAL or len(selected) >= MAX_FILES:
                raise SyncError("Vault excede o limite de arquivos ou tamanho.")
            secret_check(raw.decode("utf-8") if path.suffix.lower() in TEXT_EXTENSIONS else raw.decode("latin1"))
            selected[path.relative_to(root).as_posix()] = raw
            signatures[path] = (info.st_ino, info.st_mtime_ns, info.st_size)
        else:
            raise SyncError("Vault contém arquivo especial; exportação recusada.")
    entry, vault = safe(root, brain_rel), safe(root, vault_rel)
    if not entry.is_file() or not vault.is_dir():
        raise SyncError("Brain ou vault registrado está ausente; snapshot incompleto recusado.")
    visit(entry)
    visit(vault)
    return selected, excluded, signatures


def manifest_project(row):
    return {key: row[key] for key in ("project_id", "brain_rel", "vault_rel")}


def _export(config):
    checkout = validate_checkout(config)
    home = absolute(config["brain_home"])
    excluded, signatures = 0, {}
    manifest = {"schema_version": VERSION, "format": FORMAT,
                "central": {"brain_rel": "Brain.md", "vault_rel": "vault"}, "projects": [], "files": []}
    with tempfile.TemporaryDirectory(prefix="hebe-snapshot-", dir=safe(checkout, ".git")) as temporary:
        stage = Path(temporary)
        total = 0
        def add(rel, data):
            nonlocal total
            relative(rel)
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL or len(manifest["files"]) >= MAX_FILES:
                raise SyncError("Snapshot excede os limites de tamanho ou de arquivos.")
            write_bytes(safe(stage, rel), data)
            manifest["files"].append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        with source_locks(home):
            brain_data = database_export(safe(home, ".state/brain.sqlite3"), "brain")
            rows = sorted(brain_data["tables"]["projects"], key=lambda row: row["project_id"])
            compatible_roots(checkout, [home, *(absolute(row["path"]) for row in rows)])
            roots = [("central", home, "Brain.md", "vault")]
            roots += [("projects/" + row["project_id"], absolute(row["path"]), row["brain_rel"], row["vault_rel"]) for row in rows]
            manifest["projects"] = [manifest_project(row) for row in rows]
            for prefix, root, brain_rel, vault_rel in roots:
                selected, skipped, observed = documents(root, brain_rel, vault_rel)
                excluded += skipped
                signatures.update(observed)
                for rel, data in sorted(selected.items()):
                    add(prefix + "/" + rel, data)
            add("state/brain.json", canonical(brain_data))
            orch = safe(home, ".state/orchestrator.sqlite3")
            if orch.exists():
                add("state/orchestrator.json", canonical(database_export(orch, "orchestrator")))
            for path, before in signatures.items():
                after = absolute(path).stat()
                if before != (after.st_ino, after.st_mtime_ns, after.st_size):
                    raise SyncError("Origem mudou durante a exportação; snapshot anterior preservado.")
        manifest["files"].sort(key=lambda item: item["path"])
        encoded = canonical(manifest)
        snapshot = hashlib.sha256(encoded).hexdigest()
        write_bytes(stage / "manifest.json", encoded)
        verify(stage)
        destination = safe(checkout, "snapshots/" + snapshot)
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        if destination.exists():
            existing = verify(destination)
            if existing["snapshot"] != snapshot:
                raise SyncError("Snapshot de destino corrompido; exportação interrompida.")
        else:
            with directory(stage.parent) as source_fd, directory(destination.parent) as target_fd:
                os.replace(stage.name if source_fd is not None else stage,
                           destination.name if target_fd is not None else destination,
                           src_dir_fd=source_fd, dst_dir_fd=target_fd)
                if target_fd is not None:
                    os.fsync(target_fd)
        changed = write_bytes(safe(checkout, "CURRENT.json"), canonical({"schema_version": VERSION, "snapshot": snapshot}))
    return {"snapshot": snapshot, "path": str(destination), "changed": changed,
            "files": len(manifest["files"]), "bytes": total, "excluded_entries": excluded}


def export(config_path=None):
    path = absolute(config_path or default_config())
    config = load_config(path)
    with lock(path.with_suffix(".lock")), lock(safe(config["checkout"], ".git/hebe-brain-sync.lock")):
        return _export(config)


def resolve_snapshot(path):
    root = absolute(path)
    current = safe(root, "CURRENT.json")
    if current.exists():
        pointer = parse_json(read_bytes(current, maximum=4096))
        if (not isinstance(pointer, dict) or set(pointer) != {"schema_version", "snapshot"}
                or pointer["schema_version"] != VERSION or not isinstance(pointer["snapshot"], str)
                or not DIGEST.fullmatch(pointer["snapshot"])):
            raise SyncError("Ponteiro de snapshot inválido.")
        root = safe(root, "snapshots/" + pointer["snapshot"])
    return root


def _verified(path):
    root = resolve_snapshot(path)
    raw = read_bytes(safe(root, "manifest.json"), maximum=16 * 1024 * 1024)
    manifest = parse_json(raw)
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "format", "central", "projects", "files"}
            or manifest["schema_version"] != VERSION or manifest["format"] != FORMAT
            or manifest["central"] != {"brain_rel": "Brain.md", "vault_rel": "vault"}
            or not isinstance(manifest["projects"], list) or not isinstance(manifest["files"], list)
            or len(manifest["files"]) > MAX_FILES or raw != canonical(manifest)):
        raise SyncError("Manifesto inválido ou versão desconhecida.")
    digest = hashlib.sha256(raw).hexdigest()
    if root.parent.name == "snapshots" and root.name != digest:
        raise SyncError("Hash do manifesto não corresponde ao diretório do snapshot.")
    files, seen, total = {}, set(), 0
    for item in manifest["files"]:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}
                or not isinstance(item["sha256"], str) or not DIGEST.fullmatch(item["sha256"])
                or type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_FILE):
            raise SyncError("Entrada de manifesto inválida.")
        rel = relative(item["path"])
        collision = unicodedata.normalize("NFC", rel).casefold()
        if collision in seen:
            raise SyncError("Manifesto contém caminhos duplicados ou ambíguos.")
        seen.add(collision)
        data = read_bytes(safe(root, rel))
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise SyncError("Snapshot corrompido: tamanho ou hash divergente.")
        total += len(data)
        if total > MAX_TOTAL:
            raise SyncError("Snapshot excede o limite total.")
        files[rel] = data
    actual = set()
    def walk(folder):
        for item in folder.iterdir():
            if item.is_symlink():
                raise SyncError("Snapshot contém link simbólico.")
            if item.is_dir():
                walk(item)
            else:
                regular(item.lstat())
                actual.add(item.relative_to(root).as_posix())
    walk(root)
    if actual != set(files) | {"manifest.json"}:
        raise SyncError("Snapshot contém arquivos ausentes ou não declarados.")
    if "state/brain.json" not in files:
        raise SyncError("Snapshot não contém o registro necessário para restauração.")
    states = {"brain": validate_database_data(parse_json(files["state/brain.json"]), "brain")}
    if "state/orchestrator.json" in files:
        states["orchestrator"] = validate_database_data(parse_json(files["state/orchestrator.json"]), "orchestrator")
    # Verification also proves the data can be reconstructed under the known
    # constraints, without executing any SQL supplied by the snapshot.
    with tempfile.TemporaryDirectory(prefix="hebe-state-verify-") as temporary:
        for name, data in states.items():
            database_import(Path(temporary).resolve() / (name + ".sqlite3"), data, name)
    projects = sorted(states["brain"]["tables"]["projects"], key=lambda row: row["project_id"])
    if manifest["projects"] != [manifest_project(row) for row in projects]:
        raise SyncError("Identidades do manifesto divergem do registro.")
    layouts = {"central": ("Brain.md", "vault")}
    layouts.update({"projects/" + row["project_id"]: (row["brain_rel"], row["vault_rel"]) for row in projects})
    for rel, data in files.items():
        if rel in {"state/brain.json", "state/orchestrator.json"}:
            continue
        accepted = False
        for prefix, (brain_rel, vault_rel) in layouts.items():
            if rel.startswith(prefix + "/"):
                inside = rel[len(prefix) + 1:]
                accepted = (inside == brain_rel or inside.startswith(vault_rel + "/"))
                accepted = accepted and all(not p.startswith(".") and not SECRET_NAME.search(p) for p in inside.split("/"))
                break
        if not accepted or Path(rel).suffix.lower() not in DOC_EXTENSIONS:
            raise SyncError("Manifesto tenta restaurar arquivo fora do escopo documental.")
        secret_check(data.decode("utf-8") if Path(rel).suffix.lower() in TEXT_EXTENSIONS else data.decode("latin1"))
    for prefix, (brain_rel, _) in layouts.items():
        if prefix + "/" + brain_rel not in files:
            raise SyncError("Entrada Brain ausente no snapshot.")
    return root, manifest, files, states, digest


def verify(path):
    _, manifest, files, _, digest = _verified(path)
    return {"verified": True, "snapshot": digest, "files": len(manifest["files"]),
            "bytes": sum(len(data) for data in files.values()), "authenticated": False}


def relocated_files(files, states, destination):
    result = {rel: raw for rel, raw in files.items() if not rel.startswith("state/")}
    result["central/.gitignore"] = b"# HeBe Brain: registro e eventos locais fora do Git\n/.state/\n"
    brain = json.loads(json.dumps(states["brain"]))
    rows = brain["tables"]["projects"]
    # Only rewrite generated central project links, preserving prose and notes.
    for rel in ("central/Brain.md", "central/vault/00-Indice.md"):
        if rel not in result:
            continue
        text = result[rel].decode("utf-8")
        start, end = "<!-- hebe-brain:projects:start -->", "<!-- hebe-brain:projects:end -->"
        if start in text and end in text and text.count(start) == text.count(end) == 1:
            left, rest = text.split(start, 1)
            block, right = rest.split(end, 1)
            lines = ["\n## Projetos registrados\n"]
            for row in sorted(rows, key=lambda row: (row["name"], row["project_id"])):
                label = row["name"].replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
                target = destination / "projects" / row["project_id"] / row["brain_rel"]
                link = quote(os.path.relpath(target, (destination / rel).parent), safe="/.-_")
                lines.append(f"- [{label}]({link}) — `{row['project_id']}`")
            if not rows:
                lines.append("Nenhum projeto registrado.")
            lines += ["", "O registro e os eventos locais vivem em `.state/brain.sqlite3`.",
                      "Cada projeto mantém seus próprios documentos. Não há sincronização remota ativa.", ""]
            result[rel] = (left + start + "\n".join(lines) + end + right).encode("utf-8")
    for row in rows:
        row["path"] = str(destination / "projects" / row["project_id"])
    rewritten = dict(states, brain=brain)
    return result, rewritten


def restore(snapshot, destination, *, apply=False):
    root, _, files, states, digest = _verified(snapshot)
    destination = absolute(destination)
    if destination == root or destination in root.parents or root in destination.parents:
        raise SyncError("Restaure em diretório separado do snapshot.")
    documents_to_write, rewritten = relocated_files(files, states, destination)
    # Validate all relational constraints before touching the destination.
    with tempfile.TemporaryDirectory(prefix="hebe-restore-check-") as temp:
        staged = Path(temp).resolve()
        for name, data in rewritten.items():
            database_import(staged / (name + ".sqlite3"), data, name)
        expected = set(documents_to_write) | {"central/.state/" + name + ".sqlite3" for name in rewritten}
        changes, conflicts, unchanged = [], [], 0
        for rel in sorted(expected):
            path = safe(destination, rel)
            if path.exists():
                regular(path.lstat())
                if rel in documents_to_write:
                    equal = read_bytes(path) == documents_to_write[rel]
                else:
                    name = path.stem
                    for suffix in ("-wal", "-shm", "-journal"):
                        if absolute(str(path) + suffix).exists():
                            raise SyncError("Banco de destino tem arquivos de transação; pare o runtime antes de restaurar.")
                    equal = database_export(path, name) == rewritten[name]
                if equal:
                    unchanged += 1
                else:
                    conflicts.append(rel)
            else:
                changes.append(rel)
        extras = []
        if destination.exists():
            def walk(folder):
                for item in folder.iterdir():
                    rel = item.relative_to(destination).as_posix()
                    if item.is_symlink():
                        raise SyncError("Destino contém link simbólico; restauração recusada.")
                    if item.is_dir():
                        walk(item)
                    elif rel not in expected:
                        extras.append(rel)
            walk(destination)
        secret_check(extras)
        result = {"snapshot": digest, "dry_run": not apply, "destination": str(destination),
                  "create": changes, "conflicts": conflicts, "unchanged": unchanged,
                  "extras_preserved": sorted(extras), "applied": False}
        if not apply:
            return result
        if conflicts:
            raise SyncError("Restauração tem conflitos; nenhum arquivo foi alterado. Use outro destino ou resolva manualmente.")
        # Apply is exclusive with the destination runtime. Individual file writes
        # are atomic; an interrupted multi-file restore is completed by re-running.
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        with source_locks(safe(destination, "central"), create=True):
            for rel in changes:
                path = safe(destination, rel)
                if path.exists():
                    raise SyncError("Destino mudou após o planejamento; restauração interrompida sem sobrescrever.")
                data = documents_to_write[rel] if rel in documents_to_write else read_bytes(staged / (path.stem + ".sqlite3"))
                create_bytes(path, data)
        result["applied"] = True
        return result


def status_path(config_path):
    return absolute(config_path).with_name(absolute(config_path).stem + "-status.json")


def verified_git_tree(checkout, snapshot):
    """Freeze the index and compare its immutable blobs with the verified data."""
    prefix = "snapshots/" + snapshot + "/"
    _, manifest, files, _, digest = _verified(safe(checkout, prefix[:-1]))
    if digest != snapshot:
        raise SyncError("Snapshot mudou antes do commit.")
    expected = {prefix + rel: raw for rel, raw in files.items()}
    expected[prefix + "manifest.json"] = canonical(manifest)
    expected["CURRENT.json"] = canonical({"schema_version": VERSION, "snapshot": snapshot})
    tree = git(checkout, "write-tree").stdout.decode("ascii").strip()
    algorithm = git(checkout, "rev-parse", "--show-object-format").stdout.decode("ascii").strip()
    if algorithm not in {"sha1", "sha256"} or not re.fullmatch(r"[0-9a-f]{40,64}", tree):
        raise SyncError("Formato de objeto Git desconhecido.")
    entries = git(checkout, "ls-tree", "-r", "-z", tree, "--", "CURRENT.json", prefix[:-1]).stdout.split(b"\0")
    observed = set()
    for entry in entries:
        if not entry:
            continue
        metadata, separator, encoded_path = entry.partition(b"\t")
        rel = encoded_path.decode("utf-8")
        if not separator or rel not in expected or rel in observed:
            raise SyncError("Árvore Git contém arquivos inesperados para o snapshot.")
        raw = expected[rel]
        blob = hashlib.new(algorithm, b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if metadata != ("100644 blob " + blob).encode("ascii"):
            raise SyncError("Bytes no Git divergem do snapshot verificado; commit recusado.")
        observed.add(rel)
    if observed != set(expected):
        raise SyncError("Árvore Git não contém todos os arquivos do snapshot.")
    return tree


def sync(config_path=None):
    path = absolute(config_path or default_config())
    config = load_config(path)
    checkout = validate_checkout(config)
    with lock(path.with_suffix(".lock")), lock(safe(checkout, ".git/hebe-brain-sync.lock")):
        state = {"schema_version": VERSION, "phase": "snapshot", "started_at": now(), "finished_at": None,
                 "snapshot": None, "local_commit": None, "pushed_commit": None, "error": None}
        def save():
            write_bytes(status_path(path), canonical(state))
        save()
        try:
            if git(checkout, "diff", "--cached", "--quiet", check=False).returncode:
                raise SyncError("O índice Git deve estar vazio antes do sync.")
            modified = [p for p in git(checkout, "diff", "--name-only", "-z").stdout.decode("utf-8").split("\0") if p]
            if modified and (modified != ["CURRENT.json"] or not verify(checkout)["verified"]):
                raise SyncError("Há alterações rastreadas pendentes no checkout; revise antes do sync.")
            result = _export(config)
            state.update(phase="commit", snapshot=result["snapshot"])
            save()
            paths = ["CURRENT.json", "snapshots/" + result["snapshot"]]
            git(checkout, "add", "--", *paths)
            staged = git(checkout, "diff", "--cached", "--name-only", "-z").stdout.decode("utf-8").split("\0")
            if any(p and p != paths[0] and not p.startswith(paths[1] + "/") for p in staged):
                raise SyncError("Índice Git contém arquivos de outro escopo; commit recusado.")
            tree = verified_git_tree(checkout, result["snapshot"])
            head = git(checkout, "rev-parse", "--verify", "--quiet", "HEAD", check=False)
            if head.returncode not in (0, 1):
                raise SyncError("Não foi possível confirmar o histórico local do checkout.")
            parent = head.stdout.decode("ascii").strip() if head.returncode == 0 else None
            previous_tree = git(checkout, "rev-parse", parent + "^{tree}").stdout.decode("ascii").strip() if parent else None
            changed = tree != previous_tree
            if changed:
                # Commit the frozen, verified tree rather than rereading a
                # mutable index. Compare-and-swap refuses a concurrent branch
                # update; push below also uses this exact immutable revision.
                parents = ["-p", parent] if parent else []
                revision = git(checkout, "-c", "commit.gpgsign=false", "commit-tree", tree, *parents,
                               "-m", "HeBe Brain snapshot " + result["snapshot"][:12]).stdout.decode("ascii").strip()
                git(checkout, "update-ref", "refs/heads/" + config["branch"], revision,
                    parent or "0" * len(revision))
            else:
                revision = parent
            if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
                raise SyncError("Revisão Git inválida.")
            state.update(phase="push", local_commit=revision)
            save()
            # An explicit non-force refspec cannot overwrite diverging history.
            pushed = git(checkout, "push", "--no-verify", "--porcelain", authorized_destination(config),
                         revision + ":refs/heads/" + config["branch"], check=False)
            if pushed.returncode:
                raise SyncError("Push falhou; commit local preservado. Verifique acesso e divergência no remoto; nenhum force-push foi executado.")
            state.update(phase="complete", pushed_commit=revision, finished_at=now())
            save()
            return dict(result, committed=changed, local_commit=revision, pushed_commit=revision)
        except (SyncError, OSError, sqlite3.Error, subprocess.SubprocessError, ValueError, UnicodeError) as exc:
            state.update(failed_phase=state["phase"], phase="failed", finished_at=now(),
                         error=str(exc) if isinstance(exc, SyncError) else "Operação indisponível; diagnóstico externo omitido.")
            save()
            if isinstance(exc, SyncError):
                raise
            raise SyncError(state["error"]) from None


def status(config_path=None):
    path = absolute(config_path or default_config())
    if not path.exists():
        return {"configured": False, "scheduler_installed": False, "last_run": None}
    config = load_config(path)
    saved = status_path(path)
    last = parse_json(read_bytes(saved, private=True, maximum=16384)) if saved.exists() else None
    plist = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    return {"configured": True, "config": str(path), "checkout": config["checkout"],
            "branch": config["branch"], "remote": config["remote"], "interval_seconds": config["interval_seconds"],
            "destination_kind": config["destination_kind"],
            "private_destination_confirmed_by_user": config["private_destination_confirmed"],
            "privacy_verified_by_cli": False,
            "scheduler_installed": plist.exists() and not plist.is_symlink(),
            "scheduler_active": None, "last_run": last}


def run(config_path=None, *, once=False, max_runs=None):
    path = absolute(config_path or default_config())
    count = 0
    while True:
        try:
            outcome = sync(path)
            print(json.dumps({"event": "sync.completed", "snapshot": outcome["snapshot"], "pushed_commit": outcome["pushed_commit"]}), flush=True)
        except (SyncError, OSError, sqlite3.Error, subprocess.SubprocessError, ValueError, UnicodeError):
            print(json.dumps({"event": "sync.failed", "detail": "Consulte status; conteúdo e diagnóstico Git omitidos."}), flush=True)
            if once:
                return 2
        count += 1
        if once or (max_runs is not None and count >= max_runs):
            return 0
        interval = load_config(path)["interval_seconds"]
        for _ in range(interval):
            time.sleep(1)


def install_launchd(config_path=None, *, activate=False):
    if sys.platform != "darwin":
        raise SyncError("launchd está disponível no macOS; use run em primeiro plano neste sistema.")
    path = absolute(config_path or default_config())
    config = load_config(path)
    validate_checkout(config)
    plist = absolute((Path.home() / "Library/LaunchAgents" if activate else path.parent / "launchd-preview") / (LABEL + ".plist"))
    data = {"Label": LABEL, "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "--config", str(path), "run", "--once"],
            "StartInterval": config["interval_seconds"], "RunAtLoad": True,
            "ProcessType": "Background", "EnvironmentVariables": {"PATH": os.defpath + ":/opt/homebrew/bin:/usr/local/bin"}}
    # launchd receives no credentials or stdout/stderr paths. Operational state
    # lives in the private JSON status file, so logs cannot copy notes or secrets.
    encoded = plistlib.dumps(data, sort_keys=True)
    secret_check(encoded.decode("utf-8"))
    if plist.exists() and read_bytes(plist, private=True) != encoded:
        raise SyncError("Já existe um job diferente; desinstale explicitamente antes de substituir.")
    write_bytes(plist, encoded)
    active = False
    if activate:
        result = subprocess.run(["launchctl", "bootstrap", "gui/" + str(os.getuid()), str(plist)], capture_output=True, timeout=30)
        if result.returncode:
            raise SyncError("Plist instalado, mas launchd não confirmou a ativação.")
        active = True
    return {"prepared": True, "installed": activate, "plist": str(plist), "active": active}


def uninstall_launchd():
    if sys.platform != "darwin":
        raise SyncError("launchd está disponível somente no macOS.")
    plist = absolute(Path.home() / "Library/LaunchAgents" / (LABEL + ".plist"))
    if not plist.exists():
        return {"installed": False, "active": False}
    data = plistlib.loads(read_bytes(plist, private=True))
    if data.get("Label") != LABEL or "brain_sync.py" not in " ".join(data.get("ProgramArguments", [])):
        raise SyncError("Plist não pertence a este sincronizador.")
    result = subprocess.run(["launchctl", "bootout", "gui/" + str(os.getuid()) + "/" + LABEL], capture_output=True, timeout=30)
    if result.returncode:
        observed = subprocess.run(["launchctl", "print", "gui/" + str(os.getuid()) + "/" + LABEL], capture_output=True, timeout=30)
        if observed.returncode == 0:
            raise SyncError("launchd ainda mostra o job ativo; plist preservado.")
    plist.unlink()
    return {"installed": False, "active": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Configuração privada; padrão ~/.config/hebe-brain/sync.json.")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("configure", help="Seleciona explicitamente um checkout já existente; não cria repositório.")
    setup.add_argument("--brain-home", required=True)
    setup.add_argument("--checkout", required=True)
    setup.add_argument("--remote", default="origin")
    setup.add_argument("--branch", default="main")
    setup.add_argument("--interval-seconds", type=int, default=300)
    setup.add_argument("--confirm-private-destination", action="store_true",
                       help="Confirma que você verificou a privacidade do destino remoto; o CLI não a verifica.")
    for command in ("status", "export", "sync"):
        sub.add_parser(command)
    check = sub.add_parser("verify")
    check.add_argument("--snapshot", required=True, help="Snapshot ou checkout com CURRENT.json.")
    recovery = sub.add_parser("restore")
    recovery.add_argument("--snapshot", required=True)
    recovery.add_argument("--destination", required=True, help="Central e projetos serão criados abaixo desta pasta.")
    recovery.add_argument("--apply", action="store_true", help="Aplica o plano sem sobrescrever arquivos divergentes.")
    daemon = sub.add_parser("run", help="Executa em primeiro plano, com tentativas no intervalo configurado.")
    daemon.add_argument("--once", action="store_true")
    scheduler = sub.add_parser("install-launchd", help="Prepara preview privado; --activate instala em LaunchAgents e inicia o job.")
    scheduler.add_argument("--activate", action="store_true")
    sub.add_parser("uninstall-launchd")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            result = configure(args.config, args.brain_home, args.checkout, args.remote, args.branch, args.interval_seconds,
                               confirm_private=args.confirm_private_destination)
        elif args.command == "verify":
            result = verify(args.snapshot)
        elif args.command == "restore":
            result = restore(args.snapshot, args.destination, apply=args.apply)
        elif args.command == "run":
            return run(args.config, once=args.once)
        elif args.command == "install-launchd":
            result = install_launchd(args.config, activate=args.activate)
        elif args.command == "uninstall-launchd":
            result = uninstall_launchd()
        else:
            result = {"status": status, "export": export, "sync": sync}[args.command](args.config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SyncError as exc:
        message = str(exc)
    except (OSError, sqlite3.Error, ValueError, TypeError, UnicodeError, RecursionError, subprocess.SubprocessError):
        message = "Sync indisponível; confira configuração, arquivos e Git local. Conteúdo omitido."
    except KeyboardInterrupt:
        return 130
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
