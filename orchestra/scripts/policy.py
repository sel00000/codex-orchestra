"""Deterministic checks for the leader's proposed assignments; no model calls."""
from datetime import datetime, timezone
from pathlib import Path
import re

from catalog import EFFORTS, model_name


def text(value):
    return isinstance(value, str) and bool(value.strip())


def normalize_limit(value, project_default=None):
    value = (5 if project_default is None else project_default) if value is None else value
    if type(value) is not int or not 5 <= value <= 20:
        raise ValueError("MAX_AGENTS_MUST_BE_INTEGER_5_TO_20")
    return value


def validate_selection(value):
    if not isinstance(value, dict):
        return ["SELECTION_MISSING"]
    errors = []
    for key in ("session_id", "selection_id", "selection_evidence", "native_cap_evidence"):
        if not text(value.get(key)):
            errors.append(key.upper() + "_REQUIRED")
    if not model_name(value.get("model")) or value.get("effort") not in EFFORTS:
        errors.append("LEADER_SELECTION_INVALID")
    if value.get("selection_source") not in ("runtime_observed", "user_confirmed"):
        errors.append("SELECTION_UNCONFIRMED")
    if type(value.get("native_cap")) is not int or value["native_cap"] < 1:
        errors.append("NATIVE_CAP_UNKNOWN")
    if value.get("native_cap_source") not in ("runtime_observed", "launch_config", "user_confirmed"):
        errors.append("NATIVE_CAP_UNCONFIRMED")
    return errors


def validate_dispatch(request, snapshot, catalog, catalog_id=None):
    errors = validate_selection(snapshot)
    if not isinstance(request, dict):
        return errors + ["REQUEST_REQUIRED"]
    if errors:
        return errors
    for key in ("run_id", "task_id", "selection_id", "rationale", "acceptance"):
        if not text(request.get(key)):
            errors.append(key.upper() + "_REQUIRED")
    if request.get("selection_id") != snapshot["selection_id"]:
        errors.append("SELECTION_STALE")
    if catalog_id is not None and request.get("catalog_id") != catalog_id:
        errors.append("CATALOG_STALE")
    model, effort = request.get("model"), request.get("effort")
    if not isinstance(catalog, dict) or not model_name(model) or model not in catalog:
        errors.append("MODEL_UNAVAILABLE")
    elif not isinstance(catalog[model], list) or effort not in catalog[model]:
        errors.append("EFFORT_UNSUPPORTED")
    if effort not in EFFORTS:
        errors.append("EFFORT_REQUIRED")
    elif EFFORTS.index(effort) > EFFORTS.index(snapshot["effort"]):
        errors.append("EFFORT_CAP_EXCEEDED")
    if type(request.get("attempt")) is not int or request["attempt"] not in (1, 2, 3):
        errors.append("ATTEMPT_INVALID")
    if request.get("role") not in ("worker", "researcher", "advisor", "reviewer"):
        errors.append("ROLE_INVALID")
    for key in ("write_paths", "depends_on"):
        if not isinstance(request.get(key), list) or not all(text(item) for item in request[key]):
            errors.append(key.upper() + "_INVALID")
    try:
        deadline = datetime.fromisoformat(request["deadline_at"].replace("Z", "+00:00"))
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            errors.append("DEADLINE_TIMEZONE_REQUIRED")
        elif deadline <= datetime.now(timezone.utc):
            errors.append("DEADLINE_EXPIRED")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("DEADLINE_INVALID")
    return errors


def validate_graph(tasks):
    if not isinstance(tasks, list) or not tasks:
        return ["TASKS_REQUIRED"]
    errors, graph = [], {}
    for task in tasks:
        if not isinstance(task, dict) or not text(task.get("task_id")):
            errors.append("TASK_ID_REQUIRED")
            continue
        task_id = task["task_id"]
        if task_id in graph:
            errors.append("TASK_DUPLICATE")
        deps = task.get("depends_on")
        if not isinstance(deps, list) or not all(text(dep) for dep in deps):
            errors.append("DEPENDENCIES_INVALID")
            deps = []
        paths = task.get("write_paths")
        if not isinstance(paths, list) or not all(text(path) for path in paths):
            errors.append("WRITE_PATHS_INVALID")
        if not text(task.get("acceptance")) or type(task.get("needs_review", False)) is not bool:
            errors.append("TASK_CONTRACT_INVALID")
        graph[task_id] = deps
    if any(dep not in graph for deps in graph.values() for dep in deps):
        errors.append("DEPENDENCY_MISSING")
    visited, visiting = set(), set()

    def visit(node):
        if node in visiting:
            return False
        if node in visited or node not in graph:
            return True
        visiting.add(node)
        valid = all(visit(dep) for dep in graph[node])
        visiting.remove(node)
        visited.add(node)
        return valid

    if not all(visit(node) for node in graph):
        errors.append("DEPENDENCY_CYCLE")
    return sorted(set(errors))


def canonical_path(value, project):
    if not text(value):
        raise ValueError("PATH_REQUIRED")
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
    if match:
        value = "/mnt/" + match.group(1).lower() + "/" + match.group(2).replace("\\", "/")
    path = Path(value)
    normalized = str((path if path.is_absolute() else Path(project) / path).resolve())
    if re.match(r"^/mnt/[a-zA-Z](?:/|$)", normalized):
        normalized = normalized.casefold()
    return normalized.rstrip("/") or "/"


def paths_overlap(a, b, project):
    left, right = Path(canonical_path(a, project)), Path(canonical_path(b, project))
    return left == right or left in right.parents or right in left.parents


def validate_result(value):
    if not isinstance(value, dict):
        return ["RESULT_REQUIRED"]
    errors = []
    if not text(value.get("summary")):
        errors.append("RESULT_SUMMARY_REQUIRED")
    for key in ("artifacts", "sources", "unresolved"):
        if not isinstance(value.get(key), list):
            errors.append(key.upper() + "_REQUIRED")
    if value.get("unresolved"):
        errors.append("UNRESOLVED_ITEMS")
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks or any(
        not isinstance(check, dict) or check.get("status") != "PASS" or not text(check.get("evidence"))
        for check in (checks if isinstance(checks, list) else [])
    ):
        errors.append("VERIFICATION_EVIDENCE_REQUIRED")
    return errors
