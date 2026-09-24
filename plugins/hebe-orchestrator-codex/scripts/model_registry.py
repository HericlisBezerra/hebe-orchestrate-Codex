#!/usr/bin/env python3
"""Private catalog of observed host/provider models; never probes or invokes a provider."""

from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import math
import os
import re
import secrets
import stat
import sys

from brain import BrainError, contains_secret
from orchestrator import config_directory, regular_private


CATALOG = "model-catalog.json"
LOCK = ".model-catalog.lock"
MAX_INPUT = 8 * 1024 * 1024
MAX_MODELS = 10000
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}")
FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
SENSITIVE = re.compile(r"(?:secret|token|password|passwd|senha|credential|api.?key|private.?key|auth|cookie)", re.I)
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*")


class RegistryError(Exception):
    pass


def object_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise RegistryError("Estrutura JSON não suportada.")


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise RegistryError("Identificador inválido.")
    return value


def positive_int(value, ceiling=100000):
    if type(value) is not int or not 1 <= value <= ceiling:
        raise RegistryError("Limite inteiro inválido.")
    return value


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise RegistryError("Timestamp inválido.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RegistryError("Timestamp inválido.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RegistryError("Timestamp precisa de fuso horário.")
    return parsed


def metadata(value):
    if not isinstance(value, dict) or len(value) > 32:
        raise RegistryError("Metadata inválida.")
    for key, item in value.items():
        if not isinstance(key, str) or not FIELD.fullmatch(key) or SENSITIVE.search(key):
            raise RegistryError("Chave de metadata inválida ou sensível.")
        if item is not None and type(item) not in (str, int, float, bool):
            raise RegistryError("Metadata deve conter apenas valores escalares.")
        if isinstance(item, str) and (len(item) > 300 or any(ord(c) < 32 for c in item)):
            raise RegistryError("Texto de metadata inválido.")
        if type(item) in (int, float) and (abs(item) > 1e12 or not math.isfinite(item)):
            raise RegistryError("Número de metadata inválido.")
    if contains_secret(value):
        raise RegistryError("Possível segredo recusado; conteúdo omitido.")
    for key in ("quality", "latency_ms", "cost_per_million"):
        if key in value:
            metric = value[key]
            if type(metric) not in (int, float) or not math.isfinite(metric) or metric < 0:
                raise RegistryError("Métrica inválida.")
            if key == "quality" and metric > 1:
                raise RegistryError("Qualidade deve estar entre 0 e 1.")
    return value


def names(value, *, allow_empty=False):
    if not isinstance(value, list) or len(value) > 128 or (not allow_empty and not value):
        raise RegistryError("Lista de capacidades ou esforços inválida.")
    result = [name(item) for item in value]
    if len(set(result)) != len(result):
        raise RegistryError("Valor repetido em lista.")
    return sorted(result)


def validate_snapshot(value):
    object_keys(value, {"source", "observed_at", "models"})
    source = name(value["source"])
    timestamp(value["observed_at"])
    models = value["models"]
    if not isinstance(models, list) or len(models) > MAX_MODELS:
        raise RegistryError("Quantidade de modelos inválida.")
    normalized = []
    seen = set()
    for item in models:
        object_keys(item, {"id", "capabilities", "efforts", "max_parallel", "metadata"},
                    {"family", "version", "upgrade_to"})
        model_id = name(item["id"])
        if model_id in seen:
            raise RegistryError("Modelo duplicado no snapshot.")
        seen.add(model_id)
        for field in ("family", "upgrade_to"):
            if field in item:
                name(item[field])
        if "version" in item and (not isinstance(item["version"], str)
                                  or len(item["version"]) > 64
                                  or not VERSION.fullmatch(item["version"])
                                  or len(item["version"].split(".")) > 8
                                  or any(len(part) > 9 for part in item["version"].split("."))):
            raise RegistryError("Versão inválida; use sequência numérica pontuada.")
        normalized.append({"id": model_id, "capabilities": names(item["capabilities"]),
                           "efforts": names(item["efforts"], allow_empty=True),
                           "max_parallel": positive_int(item["max_parallel"]),
                           "metadata": metadata(item["metadata"]),
                           **{key: item[key] for key in ("family", "version", "upgrade_to") if key in item}})
    if contains_secret(value):
        raise RegistryError("Possível segredo recusado; conteúdo omitido.")
    return {"source": source, "observed_at": value["observed_at"],
            "models": sorted(normalized, key=lambda item: item["id"])}


def codex_snapshot(value, observed_at, max_parallel, source="codex.app-server"):
    """Normalize the documented model/list response emitted by Codex App Server.

    Slot capacity is session-owned and is therefore supplied from the observed
    host instead of being inferred from the model catalog.
    """
    timestamp(observed_at)
    source = name(source)
    max_parallel = positive_int(max_parallel)
    if not isinstance(value, dict) or not isinstance(value.get("data"), list):
        raise RegistryError("Resposta model/list do Codex inválida.")
    models = []
    for item in value["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RegistryError("Resposta model/list do Codex inválida.")
        if item.get("hidden") is True:
            continue
        efforts = item.get("supportedReasoningEfforts", [])
        if not isinstance(efforts, list):
            raise RegistryError("Esforços do catálogo Codex são inválidos.")
        effort_names = []
        for effort in efforts:
            if not isinstance(effort, dict) or not isinstance(effort.get("reasoningEffort"), str):
                raise RegistryError("Esforços do catálogo Codex são inválidos.")
            effort_names.append(effort["reasoningEffort"])
        modalities = item.get("inputModalities", ["text"])
        if not isinstance(modalities, list) or any(not isinstance(modality, str) for modality in modalities):
            raise RegistryError("Modalidades do catálogo Codex são inválidas.")
        capabilities = ["agentic", "codex"]
        capabilities.extend("input." + modality for modality in modalities)
        specialty = item.get("modelSpecialty")
        if isinstance(specialty, str) and specialty:
            normalized_specialty = re.sub(r"[^A-Za-z0-9_.+-]+", "-", specialty).strip("-")
            if normalized_specialty:
                capabilities.append("specialty." + normalized_specialty[:80])
        upgrade = item.get("upgradeInfo")
        upgrade_to = upgrade.get("model") if isinstance(upgrade, dict) else item.get("upgrade")
        record = {"id": item["id"], "capabilities": sorted(set(capabilities)),
                  "efforts": sorted(set(effort_names)), "max_parallel": max_parallel,
                  "metadata": {"is_default": bool(item.get("isDefault", False))}}
        if isinstance(item.get("multiAgentVersion"), str):
            record["metadata"]["multi_agent"] = item["multiAgentVersion"]
        if isinstance(upgrade_to, str) and upgrade_to:
            record["upgrade_to"] = upgrade_to
        models.append(record)
    return validate_snapshot({"source": source, "observed_at": observed_at, "models": models})


def read_json_file(path):
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    else:
        target = os.fspath(path)
        if not target or any(part == ".." for part in target.split(os.sep)):
            raise RegistryError("Caminho de entrada inválido.")
        parts = os.path.normpath(target).split(os.sep)
        directory = os.open(os.sep if os.path.isabs(target) else ".",
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            clean = [part for part in parts if part not in ("", ".")]
            if not clean:
                raise RegistryError("Caminho de entrada inválido.")
            for part in clean[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                os.close(directory)
                directory = child
            fd = os.open(clean[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise RegistryError("Entrada deve ser arquivo regular.")
                raw = stream.read(MAX_INPUT + 1)
        except OSError:
            raise RegistryError("Entrada deve ser arquivo regular sem symlinks.") from None
        finally:
            os.close(directory)
    if len(raw) > MAX_INPUT:
        raise RegistryError("Entrada JSON excede o limite.")
    return parse_json(raw)


def parse_json(raw):
    if len(raw) > MAX_INPUT:
        raise RegistryError("Entrada JSON excede o limite.")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RegistryError("Chave JSON duplicada.")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        pending = [(value, 0)]
        count = 0
        while pending:
            item, depth = pending.pop()
            count += 1
            if depth > 32 or count > 1000000:
                raise RegistryError("JSON excede o limite local de estrutura.")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
            elif isinstance(item, float) and not math.isfinite(item):
                raise RegistryError("JSON contém número não finito.")
        if contains_secret(value):
            raise RegistryError("Possível segredo recusado; conteúdo omitido.")
    except (ValueError, UnicodeError, RecursionError):
        raise RegistryError("JSON inválido; conteúdo omitido.") from None
    return value


def _read_catalog(directory):
    try:
        fd = os.open(CATALOG, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return {"schema_version": 1, "sources": {}}
    with os.fdopen(fd, "rb") as stream:
        regular_private(os.fstat(stream.fileno()))
        raw = stream.read(MAX_INPUT + 1)
    data = parse_json(raw)
    object_keys(data, {"schema_version", "sources"})
    if data["schema_version"] != 1 or not isinstance(data["sources"], dict):
        raise RegistryError("Catálogo incompatível.")
    for source, snapshot in data["sources"].items():
        if name(source) != validate_snapshot(snapshot)["source"]:
            raise RegistryError("Fonte do catálogo inconsistente.")
    return data


def load_catalog():
    try:
        with config_directory() as directory:
            return _read_catalog(directory)
    except FileNotFoundError:
        return {"schema_version": 1, "sources": {}}


def _write_catalog(directory, data):
    try:
        regular_private(os.stat(CATALOG, dir_fd=directory, follow_symlinks=False))
    except FileNotFoundError:
        pass
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(raw) > MAX_INPUT:
        raise RegistryError("Catálogo excede o limite.")
    temporary = ".model-catalog-" + secrets.token_hex(12) + ".tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CATALOG, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def version_tuple(value):
    parts = [int(part) for part in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def differences(previous, current):
    old = {item["id"]: item for item in previous["models"]} if previous else {}
    old_families = {}
    for item in old.values():
        if "family" in item and "version" in item:
            old_families.setdefault(item["family"], []).append(item)
    events = []
    for item in current["models"]:
        if item["id"] not in old:
            events.append({"kind": "new_model", "model": item["id"]})
        if "family" in item and "version" in item and item["family"] in old_families:
            maximum = max(version_tuple(old_item["version"])
                          for old_item in old_families[item["family"]])
            if version_tuple(item["version"]) > maximum:
                events.append({"kind": "higher_version", "model": item["id"],
                               "family": item["family"], "version": item["version"]})
        if item.get("upgrade_to") and item.get("upgrade_to") != old.get(item["id"], {}).get("upgrade_to"):
            events.append({"kind": "announced_upgrade", "model": item["id"],
                           "upgrade_to": item["upgrade_to"]})
    return events


def import_snapshot(snapshot):
    snapshot = validate_snapshot(snapshot)
    with config_directory(create=True) as directory:
        lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                          0o600, dir_fd=directory)
        try:
            regular_private(os.fstat(lock_fd))
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            data = _read_catalog(directory)
            previous = data["sources"].get(snapshot["source"])
            if previous and timestamp(snapshot["observed_at"]) < timestamp(previous["observed_at"]):
                raise RegistryError("Snapshot anterior ao catálogo atual.")
            events = differences(previous, snapshot)
            data["sources"][snapshot["source"]] = snapshot
            _write_catalog(directory, data)
        finally:
            os.close(lock_fd)
    return {"source": snapshot["source"], "observed_at": snapshot["observed_at"],
            "model_count": len(snapshot["models"]), "changes": events,
            "recommendation": "Avaliar modelos novos ou versões superiores antes de promover preferências." if events else None}


def remove_source(source):
    source = name(source)
    with config_directory(create=True) as directory:
        lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                          0o600, dir_fd=directory)
        try:
            regular_private(os.fstat(lock_fd))
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            data = _read_catalog(directory)
            removed = data["sources"].pop(source, None) is not None
            if removed:
                _write_catalog(directory, data)
        finally:
            os.close(lock_fd)
    return {"source": source, "removed": removed}


def validate_policy(value):
    object_keys(value, set(), {"quality_weight", "latency_weight", "cost_weight",
                               "min_quality", "max_latency_ms", "max_cost_per_million"})
    result = {"quality_weight": 0.0, "latency_weight": 0.0, "cost_weight": 0.0}
    result.update(value)
    for key, number in result.items():
        if type(number) not in (int, float) or not 0 <= number <= 1e12 or not math.isfinite(number):
            raise RegistryError("Política de métricas inválida.")
        if key == "min_quality" and number > 1:
            raise RegistryError("Qualidade deve estar entre 0 e 1.")
        if key.endswith("weight") and number > 1000000:
            raise RegistryError("Peso da política excede o limite.")
    return result


def recommend(capabilities, effort=None, policy=None, catalog=None):
    requested = names(capabilities)
    if effort is not None:
        name(effort)
    policy = validate_policy(policy or {})
    catalog = load_catalog() if catalog is None else catalog
    ranked = []
    for source, snapshot in catalog["sources"].items():
        for model in snapshot["models"]:
            if not set(requested) <= set(model["capabilities"]) or (effort and effort not in model["efforts"]):
                continue
            metrics = model["metadata"]
            if "min_quality" in policy and ("quality" not in metrics or metrics["quality"] < policy["min_quality"]):
                continue
            if "max_latency_ms" in policy and ("latency_ms" not in metrics or metrics["latency_ms"] > policy["max_latency_ms"]):
                continue
            if "max_cost_per_million" in policy and ("cost_per_million" not in metrics or metrics["cost_per_million"] > policy["max_cost_per_million"]):
                continue
            if any(weight > 0 and metric not in metrics for weight, metric in
                   ((policy["quality_weight"], "quality"), (policy["latency_weight"], "latency_ms"),
                    (policy["cost_weight"], "cost_per_million"))):
                continue
            score = (policy["quality_weight"] * metrics.get("quality", 0)
                     - policy["latency_weight"] * metrics.get("latency_ms", 0) / 1000
                     - policy["cost_weight"] * metrics.get("cost_per_million", 0))
            ranked.append({"source": source, "id": model["id"], "observed_at": snapshot["observed_at"],
                           "efforts": model["efforts"], "max_parallel": model["max_parallel"],
                           "score": round(score, 8),
                           "scored_metrics": [metric for weight, metric in
                                              ((policy["quality_weight"], "quality"),
                                               (policy["latency_weight"], "latency_ms"),
                                               (policy["cost_weight"], "cost_per_million")) if weight > 0],
                           "metrics": {key: metrics[key] for key in ("quality", "latency_ms", "cost_per_million") if key in metrics},
                           "missing_metrics": [key for key in ("quality", "latency_ms", "cost_per_million") if key not in metrics]})
    ranked.sort(key=lambda item: (-item["score"], item["source"], item["id"]))
    return {"capabilities": requested, "effort": effort, "policy": policy, "candidates": ranked}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    imported = sub.add_parser("import", help="Importa snapshot JSON observado; substitui a fonte.")
    imported.add_argument("--file", required=True, help="Arquivo JSON regular ou - para stdin.")
    codex = sub.add_parser("import-codex", help="Normaliza uma resposta model/list observada do Codex App Server.")
    codex.add_argument("--file", required=True, help="Resposta JSON regular ou - para stdin.")
    codex.add_argument("--observed-at", required=True)
    codex.add_argument("--max-parallel", required=True, type=int,
                       help="Limite de agentes delegados observado nesta sessão.")
    codex.add_argument("--source", default="codex.app-server")
    sub.add_parser("list", help="Mostra o catálogo privado atual.")
    removed = sub.add_parser("remove", help="Remove uma fonte observada do catálogo privado.")
    removed.add_argument("--source", required=True)
    ranked = sub.add_parser("recommend", help="Classifica candidatos observados por capacidades e política.")
    ranked.add_argument("--capability", action="append", required=True)
    ranked.add_argument("--effort")
    ranked.add_argument("--policy-file", help="Objeto JSON de pesos e limites; arquivo regular ou -.")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = import_snapshot(read_json_file(args.file))
        elif args.command == "import-codex":
            result = import_snapshot(codex_snapshot(read_json_file(args.file), args.observed_at,
                                                    args.max_parallel, args.source))
        elif args.command == "list":
            result = load_catalog()
        elif args.command == "remove":
            result = remove_source(args.source)
        else:
            result = recommend(args.capability, args.effort,
                               read_json_file(args.policy_file) if args.policy_file else None)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (RegistryError, BrainError, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, RegistryError) else "Entrada ou catálogo inválido; conteúdo omitido."},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
