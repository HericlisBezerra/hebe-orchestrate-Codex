#!/usr/bin/env python3
"""Explicitly rerank a local JSON shortlist with TypeSafe/Jev.

``preview`` is entirely local. ``evaluate --send`` is the only network path.
Neither command prints candidate text, query text, metadata, or credentials.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

if __package__:
    from . import jev
else:
    import jev


DEFAULT_THRESHOLD = 0.65
MAX_CANDIDATES = 64
MAX_TEXT = 16000
BAD_RESPONSE = "Resposta TypeSafe incompatível com a shortlist; conteúdo omitido."
SECRET_FIELD = re.compile(r"(?:^|[_-])(api[_-]?key|secret|password|passwd|token|authorization|cookie|credential|private[_-]?key)(?:$|[_-])", re.I)
SECRET_VALUE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/-]{8,}|"
    r"\b(?:sk[-_]|gh[pousr]_|github_pat_|xox[baprs]-|AKIA|AIza)[A-Za-z0-9_/-]{12,}|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@|"
    r"\b(?:api[_-]?key|password|secret|token|authorization)[\"']?\s*[:=]\s*[^\s,;]{8,})"
)


def _read_regular_nosymlink(filename):
    """Open every path component with O_NOFOLLOW, including parent directories."""
    path = Path(filename)
    parts = path.parts[1:] if path.is_absolute() else path.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise jev.JevError("Caminho da shortlist inválido.")
    directory = os.open("/" if path.is_absolute() else ".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise jev.JevError("Shortlist exige arquivo JSON regular.")
            return jev.strict_json(stream.read(jev.MAX_INPUT + 1), jev.MAX_INPUT)
    except OSError:
        raise jev.JevError("Não foi possível ler a shortlist; symlinks não são aceitos.") from None
    finally:
        os.close(directory)


def _scan_secrets(value, field=""):
    compact = re.sub(r"[^a-z0-9]", "", field.casefold())
    if SECRET_FIELD.search(field) or compact.endswith(("apikey", "password", "privatekey", "accesstoken", "refreshtoken", "sessiontoken")):
        raise jev.JevError("Shortlist contém campo de credencial; conteúdo omitido.")
    if isinstance(value, str):
        if SECRET_VALUE.search(value):
            raise jev.JevError("Shortlist parece conter segredo; conteúdo omitido.")
    elif isinstance(value, dict):
        for key, item in value.items():
            _scan_secrets(item, key)
    elif isinstance(value, list):
        for item in value:
            _scan_secrets(item)


def _text(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and not any(
        ord(char) < 32 and char not in "\t\n\r" for char in value
    )


def load_shortlist(filename, model_override=None, threshold_override=None):
    data = _read_regular_nosymlink(filename)
    if not isinstance(data, dict) or set(data) - {"query", "candidates", "model", "threshold"}:
        raise jev.JevError("Shortlist exige query, candidates e opcionais model e threshold.")
    if not _text(data.get("query"), MAX_TEXT):
        raise jev.JevError("query deve ser texto não vazio de até 16000 caracteres.")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise jev.JevError("candidates deve conter entre 1 e 64 itens.")
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) - {"id", "text", "metadata"}:
            raise jev.JevError("Candidato exige id, text e metadata opcional.")
        identity = candidate.get("id")
        if not _text(identity, 128) or identity != identity.strip():
            raise jev.JevError("ID de candidato inválido.")
        if identity in seen:
            raise jev.JevError("Shortlist contém ID duplicado.")
        seen.add(identity)
        if not _text(candidate.get("text"), MAX_TEXT):
            raise jev.JevError("Texto de candidato inválido.")
        if "metadata" in candidate and not isinstance(candidate["metadata"], dict):
            raise jev.JevError("metadata deve ser objeto JSON.")
    model = model_override if model_override is not None else data.get("model", jev.DEFAULT_MODEL)
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
        raise jev.JevError("Identificador de modelo inválido.")
    threshold = threshold_override if threshold_override is not None else data.get("threshold", DEFAULT_THRESHOLD)
    if not jev.probability(threshold):
        raise jev.JevError("threshold deve ser número entre 0 e 1.")
    _scan_secrets(data)
    return {"query": data["query"], "candidates": candidates, "model": model,
            "threshold": threshold}


def build_request(shortlist):
    state = {"query": shortlist["query"], "candidates": shortlist["candidates"]}
    questions = {}
    for index in range(len(shortlist["candidates"])):
        questions[f"candidate_{index}"] = {
            "type": "noul",
            "instructions": (
                f"Does `candidates[{index}]` directly provide evidence that answers `query`? "
                "Judge this candidate independently of the other candidates."
            ),
            "criteria": {
                "true": "The candidate text directly and specifically answers the query with relevant evidence.",
                "false": "The candidate is only topically similar, incomplete, contradictory, or unrelated.",
            },
        }
    payload = {"model": shortlist["model"], "state": state, "questions": questions}
    # Match jev.request_api's wire encoding for the size check and fingerprint.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > jev.MAX_INPUT:
        raise jev.JevError("Pedido excede o limite local de 1 MiB.")
    return payload, "sha256:" + hashlib.sha256(encoded).hexdigest()


def preview(shortlist, payload, fingerprint):
    base = jev.evaluation_preview(payload)
    return {"valid": True, "network_used": False, "credential_used": False,
            "model": base["model"], "candidate_count": len(shortlist["candidates"]),
            "question_count": base["question_count"],
            "request_bytes": len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")),
            "threshold": shortlist["threshold"], "request_fingerprint": fingerprint}


def _validated_probabilities(raw, payload):
    if not isinstance(raw, dict) or set(raw) != {"model", "answers", "usage"}:
        raise jev.JevError(BAD_RESPONSE)
    model = raw.get("model")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
        raise jev.JevError(BAD_RESPONSE)
    answers, usage = raw.get("answers"), raw.get("usage")
    if not isinstance(answers, dict) or set(answers) != set(payload["questions"]):
        raise jev.JevError(BAD_RESPONSE)
    if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}:
        raise jev.JevError(BAD_RESPONSE)
    if any(not isinstance(answer, dict) or set(answer) != {"type", "noul"}
           for answer in answers.values()):
        raise jev.JevError(BAD_RESPONSE)
    # Reuse the connector's typed response, probability, and token validation.
    validated = jev.evaluation_output(raw, payload["questions"])
    return model, [validated["answers"][f"candidate_{index}"]["noul"]
                   for index in range(len(answers))]


def rank(shortlist, payload, fingerprint, raw=None, failure=None):
    probabilities = None
    response_model = None
    reason = failure
    if raw is not None:
        response_model, probabilities = _validated_probabilities(raw, payload)
        if max(probabilities) < shortlist["threshold"]:
            reason = "below_threshold"
    abstained = reason is not None
    order = list(range(len(shortlist["candidates"])))
    if not abstained:
        order.sort(key=lambda index: -probabilities[index])
    ranked = []
    for position, index in enumerate(order, 1):
        item = {"rank": position, "id": shortlist["candidates"][index]["id"],
                "original_rank": index + 1}
        if probabilities is not None:
            item["probability"] = probabilities[index]
        ranked.append(item)
    return {
        "mode": "local_fallback" if abstained else "jev",
        "abstained": abstained, "reason": reason, "threshold": shortlist["threshold"],
        "ranked": ranked,
        "provenance": {"source": "local_shortlist", "candidate_count": len(order),
                       "requested_model": shortlist["model"], "response_model": response_model,
                       "processed_at": jev.timestamp(), "request_fingerprint": fingerprint},
    }


def evaluate(shortlist, payload, fingerprint):
    try:
        key, _ = jev.active_credentials(required=True)
    except jev.JevError:
        return rank(shortlist, payload, fingerprint, failure="credential_unavailable")
    try:
        raw = jev.request_api("systemone", key, payload)
    except jev.JevError:
        return rank(shortlist, payload, fingerprint, failure="service_unavailable")
    return rank(shortlist, payload, fingerprint, raw=raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "evaluate"):
        cli = sub.add_parser(command)
        cli.add_argument("--file", required=True, help="Shortlist local em JSON regular (até 1 MiB).")
        cli.add_argument("--model", help="Modelo TypeSafe; padrão jev-latest.")
        cli.add_argument("--threshold", type=float, help="Probabilidade mínima para aceitar o primeiro resultado.")
        if command == "evaluate":
            cli.add_argument("--send", action="store_true", required=True,
                             help="Autoriza o envio desta shortlist à TypeSafe.")
    args = parser.parse_args(argv)
    try:
        shortlist = load_shortlist(args.file, args.model, args.threshold)
        payload, fingerprint = build_request(shortlist)
        output = preview(shortlist, payload, fingerprint) if args.command == "preview" else evaluate(
            shortlist, payload, fingerprint)
        print(json.dumps(output, ensure_ascii=False, allow_nan=False))
        return 0
    except jev.JevError as exc:
        message = str(exc)
    except (OSError, ValueError, RecursionError):
        message = "Operação indisponível; conteúdo omitido."
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
