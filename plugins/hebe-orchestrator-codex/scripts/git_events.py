#!/usr/bin/env python3
"""Emit local Git history as HeBe Brain events, scoped to one project directory.

Read-only: does not stage, commit, push, fetch or write to the Brain. Pipe the
JSON array into brain.py record after checking the project identity.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

from brain import Brain, BrainError, contains_secret, valid_uuid


def git(path, *arguments, check=True):
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(path), *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if check and result.returncode:
        # Git diagnostics can contain repository URLs, filenames or credentials.
        raise BrainError("Não foi possível ler o histórico Git local deste projeto.")
    return result


def collect(path, project_id, limit=50, since=None):
    valid_uuid(project_id)
    root = Path(path).expanduser().resolve()
    if not root.is_dir() or not 1 <= limit <= 500:
        raise BrainError("Informe pasta existente e limite entre 1 e 500.")
    if since:
        try:
            parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            raise BrainError("--since exige data ISO-8601 com fuso horário.") from None
    repo = Path(git(root, "rev-parse", "--show-toplevel").stdout.decode("utf-8").strip()).resolve()
    try:
        relative = root.relative_to(repo).as_posix()
    except ValueError:
        raise BrainError("O projeto não pertence ao repositório encontrado.") from None
    revision = git(repo, "rev-parse", "--verify", "HEAD", check=False)
    if revision.returncode:
        # An unborn branch has no commits. Other corrupt HEAD states are errors.
        symbolic = git(repo, "symbolic-ref", "-q", "HEAD", check=False)
        if symbolic.returncode:
            raise BrainError("HEAD local inválido.")
        return []
    head = revision.stdout.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise BrainError("Revisão Git inválida.")
    arguments = ["rev-list", f"--max-count={limit}"]
    if since:
        arguments.append(f"--since={since}")
    arguments.extend([head, "--", relative])
    hashes = git(repo, *arguments).stdout.decode("ascii").splitlines()
    events = []
    for sha in reversed(hashes):
        if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise BrainError("Histórico Git contém revisão inválida.")
        metadata = git(repo, "show", "--no-patch", "--format=%cI%x00%s", sha).stdout.decode("utf-8").rstrip("\n")
        timestamp, subject = metadata.split("\x00", 1)
        raw_paths = git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", sha, "--", relative).stdout
        paths = [name.decode("utf-8") for name in raw_paths.split(b"\x00") if name]
        payload = {
            "title": subject[:240] or f"Commit {sha[:12]}",
            "body": "Commit observado no Git local. Este evento não comprova push nem publicação remota.",
            "sha": sha,
            "paths": paths,
        }
        if subject != payload["title"]:
            payload["subject"] = subject
        event = {
            "schema_version": 1,
            "event_id": f"git:{project_id}:{sha}",
            "project_id": project_id,
            "kind": "commit.created",
            "occurred_at": timestamp,
            "source": "git",
            "source_ref": sha,
            "payload": payload,
        }
        if contains_secret(event):
            raise BrainError("Histórico recusado: possível segredo em metadados; conteúdo omitido.")
        Brain.validate_event(event)
        events.append(event)
    encoded = json.dumps(events, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
        raise BrainError("Histórico excede 2 MiB; reduza --limit.")
    return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Raiz do projeto/subprojeto; filtra commits por este caminho.")
    parser.add_argument("--project", required=True, help="UUID já registrado no Brain.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--since", help="Filtro opcional ISO-8601 com fuso.")
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.path, args.project, args.limit, args.since), ensure_ascii=False))
        return 0
    except BrainError as exc:
        message = str(exc)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        message = "Leitura Git indisponível; confira a pasta e a instalação local, sem expor conteúdo."
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
