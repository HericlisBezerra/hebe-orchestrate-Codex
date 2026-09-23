#!/usr/bin/env python3
"""Create or inspect portable agent instructions and an optional Playwright kit."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import stat
import sys


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PLUGIN_ROOT / "templates"
PLAYWRIGHT_CONFIGS = (
    "playwright.config.ts",
    "playwright.config.js",
    "playwright.config.mts",
    "playwright.config.mjs",
    "playwright.config.cts",
    "playwright.config.cjs",
)


class ContextError(Exception):
    pass


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def project_root(value):
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ContextError("A raiz informada não é uma pasta acessível.")
    return root


def inside(root, target):
    try:
        target.resolve().relative_to(root)
    except ValueError:
        raise ContextError("O destino precisa permanecer dentro do projeto.") from None


def existing_file(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ContextError(f"Destino inseguro ou incompatível: {path}")
    return True


def write_new(root, relative, content):
    target = root / relative
    inside(root, target)
    if existing_file(target):
        return "preserved"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.resolve() != root and root not in target.parent.resolve().parents:
        raise ContextError("A pasta de destino saiu da raiz do projeto.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o644)
    except FileExistsError:
        return "preserved"
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return "created"


def template(relative):
    path = TEMPLATES / relative
    if not path.is_file():
        raise ContextError(f"Template ausente no plugin: {relative}")
    return path.read_text(encoding="utf-8")


def has_agents_import(path):
    if not existing_file(path):
        return False
    try:
        return any(line.strip() == "@AGENTS.md" for line in path.read_text(encoding="utf-8").splitlines())
    except UnicodeError:
        raise ContextError("CLAUDE.md não está em UTF-8.") from None


def nearest_playwright_config(root):
    return next(((folder, name) for folder in (root, *root.parents)
                 for name in PLAYWRIGHT_CONFIGS if existing_file(folder / name)), None)


def status(root):
    agents = root / "AGENTS.md"
    claude = root / "CLAUDE.md"
    playwright_info = nearest_playwright_config(root)
    package_file = next((folder / "package.json" for folder in (root, *root.parents)
                         if existing_file(folder / "package.json")), None)
    dependency = None
    scripts = []
    if package_file:
        if package_file.stat().st_size > 1024 * 1024:
            raise ContextError("package.json excede 1 MiB para inspeção local.")
        try:
            package = json.loads(package_file.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise ContextError("package.json inválido ou fora de UTF-8.") from None
        if not isinstance(package, dict):
            raise ContextError("package.json precisa ser um objeto JSON.")
        dependency = any(isinstance(package.get(section), dict) and "@playwright/test" in package[section]
                         for section in ("dependencies", "devDependencies", "optionalDependencies"))
        declared_scripts = package.get("scripts", {})
        if isinstance(declared_scripts, dict):
            scripts = sorted(name for name, command in declared_scripts.items()
                             if isinstance(name, str) and isinstance(command, str) and "playwright" in command.lower())
    brain_markers = [name for name in ("Brain.md", "brain/INDEX.md", "vault/00-Indice.md")
                     if existing_file(root / name)]
    applicable_agents = [str(folder / "AGENTS.md") for folder in reversed((root, *root.parents))
                         if existing_file(folder / "AGENTS.md")]
    return {
        "project": str(root),
        "agents_md": existing_file(agents),
        "applicable_agents": applicable_agents,
        "host_loaded": "unknown",
        "claude_md": existing_file(claude),
        "claude_imports_agents": has_agents_import(claude) if claude.exists() else False,
        "playwright_config": playwright_info[1] if playwright_info else None,
        "playwright_config_path": str(playwright_info[0] / playwright_info[1]) if playwright_info else None,
        "package_json_path": str(package_file) if package_file else None,
        "playwright_dependency": dependency,
        "playwright_scripts": scripts,
        "brain_markers": brain_markers,
    }


def initialize(root, name, claude_bridge):
    agents_text = template("AGENTS.md").replace("{{PROJECT_NAME}}", name).replace("{{DATE}}", date.today().isoformat())
    actions = {"AGENTS.md": write_new(root, "AGENTS.md", agents_text)}
    if claude_bridge:
        actions["CLAUDE.md"] = write_new(root, "CLAUDE.md", template("CLAUDE.md"))
        if actions["CLAUDE.md"] == "preserved" and not has_agents_import(root / "CLAUDE.md"):
            actions["CLAUDE.md"] = "preserved_import_missing"
    return {"project": str(root), "actions": actions, "status": status(root)}


def web_initialize(root):
    if not existing_file(root / "package.json"):
        raise ContextError("web-init requer um projeto Node com package.json; adapte Playwright manualmente para outra stack.")
    config = nearest_playwright_config(root)
    if config:
        config_action = "preserved_existing:" + os.path.relpath(config[0] / config[1], root)
        smoke_action = "not_created_existing_config"
    else:
        config_action = write_new(root, "playwright.config.ts", template("playwright/playwright.config.ts"))
        smoke_action = write_new(root, "tests/e2e/smoke.spec.ts", template("playwright/smoke.spec.ts"))
    return {
        "project": str(root),
        "actions": {"playwright_config": config_action, "tests/e2e/smoke.spec.ts": smoke_action},
        "dependency": "Use o gerenciador do projeto para adicionar @playwright/test e instalar Chromium.",
        "next": "Adapte o smoke test às rotas e critérios do produto antes de executar.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("status", help="Inspeciona AGENTS.md, Claude, Playwright e marcadores do Brain.")
    check.add_argument("--path", required=True, help="Raiz do projeto.")

    init = sub.add_parser("init", help="Cria contrato portátil sem sobrescrever arquivos existentes.")
    init.add_argument("--path", required=True, help="Raiz do projeto.")
    init.add_argument("--name", help="Nome exibido no contrato; padrão: nome da pasta.")
    init.add_argument("--no-claude-bridge", action="store_true", help="Não cria CLAUDE.md com @AGENTS.md.")

    web = sub.add_parser("web-init", help="Cria config e smoke test Playwright sem instalar dependências.")
    web.add_argument("--path", required=True, help="Raiz de um projeto Node.")

    args = parser.parse_args()
    try:
        root = project_root(args.path)
        if args.command == "status":
            emit(status(root))
        elif args.command == "init":
            emit(initialize(root, args.name or root.name, not args.no_claude_bridge))
        else:
            emit(web_initialize(root))
        return 0
    except ContextError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print(json.dumps({"error": "Não foi possível concluir a operação; conteúdo local omitido."}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
