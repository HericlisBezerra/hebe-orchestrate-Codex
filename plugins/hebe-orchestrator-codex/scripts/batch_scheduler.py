#!/usr/bin/env python3
"""Deterministic, declarative DAG wave planner. It never launches work."""

from __future__ import annotations

import argparse
from collections import deque
import heapq
import json
import sys

from model_registry import RegistryError, load_catalog, name, positive_int, read_json_file, timestamp


MAX_TASKS = 20000
MAX_EDGES = 200000
STATES = {"pending", "succeeded", "failed", "cancelled"}


class ScheduleError(Exception):
    pass


def keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ScheduleError("Estrutura do plano inválida.")


def validate(document):
    keys(document, {"limits", "tasks"}, {"retry_policy"})
    limits = document["limits"]
    keys(limits, {"source", "observed_at", "global_slots", "model_slots"}, {"registry_source"})
    name(limits["source"])
    if "registry_source" in limits:
        name(limits["registry_source"])
    timestamp(limits["observed_at"])
    global_slots = positive_int(limits["global_slots"], MAX_TASKS)
    model_slots = limits["model_slots"]
    if not isinstance(model_slots, dict) or not model_slots or len(model_slots) > MAX_TASKS:
        raise ScheduleError("Slots por modelo inválidos.")
    for model, count in model_slots.items():
        name(model)
        positive_int(count, MAX_TASKS)
        if count > global_slots:
            raise ScheduleError("Slot por modelo excede o limite global declarado.")
    retry = document.get("retry_policy", {"max_attempts": 1, "retry_failed": False,
                                           "retry_cancelled": False})
    keys(retry, {"max_attempts", "retry_failed", "retry_cancelled"})
    positive_int(retry["max_attempts"], 100)
    if type(retry["retry_failed"]) is not bool or type(retry["retry_cancelled"]) is not bool:
        raise ScheduleError("Política de retry inválida.")
    tasks = document["tasks"]
    if not isinstance(tasks, list) or len(tasks) > MAX_TASKS:
        raise ScheduleError("Quantidade de tarefas inválida.")
    by_id = {}
    edges = 0
    for item in tasks:
        keys(item, {"id", "model", "depends_on"}, {"status", "attempts", "max_attempts"})
        task_id = name(item["id"])
        if task_id in by_id:
            raise ScheduleError("ID de tarefa duplicado.")
        model = name(item["model"])
        if model not in model_slots:
            raise ScheduleError("Tarefa usa modelo sem limite declarado.")
        dependencies = item["depends_on"]
        if not isinstance(dependencies, list) or len(dependencies) > MAX_TASKS:
            raise ScheduleError("Dependências inválidas.")
        dependencies = [name(dep) for dep in dependencies]
        if len(set(dependencies)) != len(dependencies):
            raise ScheduleError("Dependência repetida.")
        edges += len(dependencies)
        if edges > MAX_EDGES:
            raise ScheduleError("Quantidade de dependências excede o limite.")
        status = item.get("status", "pending")
        attempts = item.get("attempts", 0)
        maximum = item.get("max_attempts", retry["max_attempts"])
        if not isinstance(status, str) or status not in STATES or type(attempts) is not int or not 0 <= attempts <= 100:
            raise ScheduleError("Estado ou tentativas inválidas.")
        positive_int(maximum, 100)
        if status == "failed" and attempts == 0:
            raise ScheduleError("Tarefa falha precisa registrar ao menos uma tentativa.")
        by_id[task_id] = {"id": task_id, "model": model, "depends_on": dependencies,
                          "status": status, "attempts": attempts, "max_attempts": maximum}
    for item in by_id.values():
        if any(dep not in by_id for dep in item["depends_on"]):
            raise ScheduleError("Dependência desconhecida.")
    return limits, retry, by_id


def _graph(by_id):
    children = {task_id: [] for task_id in by_id}
    indegree = {task_id: len(item["depends_on"]) for task_id, item in by_id.items()}
    for item in by_id.values():
        for dep in item["depends_on"]:
            children[dep].append(item["id"])
    for successors in children.values():
        successors.sort()
    ready = [task_id for task_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    visited = 0
    while ready:
        task_id = heapq.heappop(ready)
        visited += 1
        for child in children[task_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if visited != len(by_id):
        raise ScheduleError("Ciclo de dependências detectado.")
    return children


def plan(document, catalog=None):
    limits, retry, by_id = validate(document)
    if "registry_source" in limits:
        catalog = load_catalog() if catalog is None else catalog
        snapshot = catalog.get("sources", {}).get(limits["registry_source"])
        if snapshot is None:
            raise ScheduleError("Fonte do catálogo não encontrada.")
        observed = {item["id"]: item["max_parallel"] for item in snapshot["models"]}
        for model, slots in limits["model_slots"].items():
            if model not in observed or slots > observed[model]:
                raise ScheduleError("Slot de modelo excede o catálogo observado ou modelo ausente.")
    children = _graph(by_id)
    terminal = set()
    for task_id, item in by_id.items():
        if item["status"] in {"failed", "cancelled"}:
            enabled = retry["retry_failed"] if item["status"] == "failed" else retry["retry_cancelled"]
            if not enabled or item["attempts"] >= item["max_attempts"]:
                terminal.add(task_id)
    blocked_by = {task_id: task_id for task_id in terminal}
    queue = deque(sorted(terminal))
    while queue:
        parent = queue.popleft()
        for child in children[parent]:
            if child not in blocked_by:
                blocked_by[child] = blocked_by[parent]
                queue.append(child)
    completed = sorted(task_id for task_id, item in by_id.items() if item["status"] == "succeeded")
    if any(task_id in blocked_by for task_id in completed):
        raise ScheduleError("Estado inconsistente: tarefa concluída depende de falha terminal.")
    actionable = set(by_id) - set(blocked_by) - set(completed)
    remaining = {task_id: sum(dep in actionable for dep in by_id[task_id]["depends_on"])
                 for task_id in actionable}
    ready_by_model = {model: [] for model in limits["model_slots"]}
    candidates = []
    paused = set()

    def add_ready(task_id):
        model = by_id[task_id]["model"]
        items = ready_by_model[model]
        old_head = items[0] if items else None
        heapq.heappush(items, task_id)
        if model not in paused and (old_head is None or items[0] != old_head):
            heapq.heappush(candidates, (items[0], model))

    for task_id in sorted(actionable):
        if remaining[task_id] == 0:
            add_ready(task_id)
    waves = []
    conditional = set()
    planned = set()
    while len(planned) < len(actionable):
        for model in sorted(paused):
            if ready_by_model[model]:
                heapq.heappush(candidates, (ready_by_model[model][0], model))
        paused.clear()
        used = {}
        wave = []
        while candidates and len(wave) < limits["global_slots"]:
            task_id, model = heapq.heappop(candidates)
            items = ready_by_model[model]
            if not items or items[0] != task_id or model in paused:
                continue
            if used.get(model, 0) >= limits["model_slots"][model]:
                paused.add(model)
                continue
            heapq.heappop(items)
            item = by_id[task_id]
            is_retry = item["status"] in {"failed", "cancelled"}
            is_conditional = is_retry or any(dep in conditional for dep in item["depends_on"])
            if is_conditional:
                conditional.add(task_id)
            wave.append({"id": task_id, "model": model, "attempt": item["attempts"] + 1,
                         "retry": is_retry, "conditional": is_conditional})
            planned.add(task_id)
            used[model] = used.get(model, 0) + 1
            if items:
                if used[model] < limits["model_slots"][model]:
                    heapq.heappush(candidates, (items[0], model))
                else:
                    paused.add(model)
        if not wave:
            raise ScheduleError("Não foi possível alocar tarefas com os limites declarados.")
        waves.append(wave)
        for scheduled in wave:
            for child in children[scheduled["id"]]:
                if child in remaining:
                    remaining[child] -= 1
                    if remaining[child] == 0:
                        add_ready(child)
    if planned != actionable:
        raise ScheduleError("Plano incompleto apesar de DAG válido.")
    return {"limits": limits, "retry_policy": retry, "waves": waves,
            "completed": completed,
            "blocked": [{"id": task_id, "by": blocked_by[task_id],
                         "reason": by_id[blocked_by[task_id]]["status"]}
                        for task_id in sorted(blocked_by)],
            "summary": {"tasks": len(by_id), "planned": len(planned), "waves": len(waves),
                        "completed": len(completed), "blocked": len(blocked_by)},
            "execution": "planning_only; replan after each observed wave"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Plano JSON em arquivo regular ou - para stdin.")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(plan(read_json_file(args.file)), ensure_ascii=False, indent=2))
        return 0
    except (ScheduleError, RegistryError, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, ScheduleError) else "Plano inválido; conteúdo omitido."},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
