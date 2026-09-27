"""Read-only capability diagnostics, not a dispatch or enforcement runtime.

Historical strict-mode diagnostics. The tested native hook fails open on
errors. The approved workflow-policy skill uses policy.py and state.py;
this strict predicate is not that mode's execution gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any

EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODELS = (
    "gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol",
    "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5",
)
CHECKS = (
    "active_selection", "pre_dispatch_guard", "effective_values", "native_cap",
    "root_only_dispatch", "lifecycle", "config_isolation",
)
TESTED_VERSION = "0.157.1"
GUARD_SOURCE = (
    "https://raw.githubusercontent.com/openai/codex/rust-v0.157.1/"
    "codex-rs/hooks/src/events/pre_tool_use.rs"
)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_snapshot(snapshot: dict, session_id: str, turn_id: str) -> list[str]:
    """Compare a runtime snapshot to independently supplied session/turn IDs.

    This checks the data contract; it cannot establish the origin of a dict.
    Config defaults and model self-reports are never live selection evidence.
    """
    if not isinstance(snapshot, dict):
        return ["SNAPSHOT_MISSING"]
    errors = []
    if not _text(session_id) or snapshot.get("session_id") != session_id:
        errors.append("SESSION_MISMATCH")
    if not _text(turn_id) or snapshot.get("turn_id") != turn_id:
        errors.append("TURN_STALE")
    if not _text(snapshot.get("model")):
        errors.append("MODEL_UNKNOWN")
    if snapshot.get("effort") not in EFFORTS:
        errors.append("EFFORT_UNKNOWN")
    capacity = snapshot.get("native_cap")
    if type(capacity) is not int or capacity < 1:
        errors.append("CAPACITY_UNKNOWN")
    if snapshot.get("backend") not in ("v1", "v2"):
        errors.append("BACKEND_UNKNOWN")
    if snapshot.get("selection_source") != "live_turn" or snapshot.get("verified") is not True:
        errors.append("SELECTION_UNVERIFIED")
    return errors


def is_compatible(report: dict) -> bool:
    """Evaluate an already evidenced report; never manufacture PASS evidence.

    This is a structural predicate, not authentication of user-supplied JSON
    or a replacement for validating a snapshot against the current live turn.
    The live inspector below never returns a compatible report on 0.157.1.
    """
    if not isinstance(report, dict) or report.get("codex_version") != TESTED_VERSION:
        return False
    python_version = report.get("python_version")
    if not isinstance(python_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", python_version):
        return False
    if tuple(map(int, python_version.split("."))) < (3, 11, 0):
        return False
    checks = report.get("checks")
    if not isinstance(checks, dict) or any(checks.get(key) != "PASS" for key in CHECKS):
        return False
    snap = report.get("snapshot")
    if not isinstance(snap, dict) or validate_snapshot(snap, snap.get("session_id"), snap.get("turn_id")):
        return False
    catalog = report.get("catalog")
    if not isinstance(catalog, dict) or snap["model"] not in MODELS:
        return False
    supported = catalog.get(snap["model"])
    if not isinstance(supported, list) or snap["effort"] not in supported:
        return False
    evidence = report.get("evidence_paths")
    return isinstance(evidence, list) and bool(evidence) and all(_text(item) for item in evidence)


def normalize_event(raw: dict, backend: str) -> dict:
    """Normalize the observed V2 hook envelope without inventing effective values.

    A missing agent_id remains unknown. It does not mean the caller is root.
    The parent effort and child effective configuration are absent from the
    pre-tool hook; requested values in tool_input are not those missing facts.
    """
    if backend != "v2" or not isinstance(raw, dict):
        raise ValueError("UNSUPPORTED_EVENT_BACKEND")
    event = {"PreToolUse": "pre_tool_use", "PostToolUse": "post_tool_use"}.get(raw.get("hook_event_name"))
    if event is None:
        raise ValueError("UNSUPPORTED_CONTROL_EVENT")
    required = ("session_id", "turn_id", "tool_name", "tool_use_id")
    if any(not _text(raw.get(key)) for key in required) or not isinstance(raw.get("tool_input"), dict):
        raise ValueError("INCOMPLETE_EVENT")
    if event == "post_tool_use" and "tool_response" not in raw:
        raise ValueError("MISSING_TOOL_RESPONSE")
    actor = raw.get("agent_id")
    if actor is not None and not _text(actor):
        raise ValueError("INVALID_ACTOR_ID")
    return {
        "event": event, "session_id": raw["session_id"], "turn_id": raw["turn_id"],
        "actor_id": actor, "tool_name": raw["tool_name"], "tool_use_id": raw["tool_use_id"],
        "input": raw["tool_input"], "output": raw.get("tool_response") if event == "post_tool_use" else None,
        "backend": backend,
    }


def inspect_environment(project: Path, session_id: str | None = None) -> dict:
    """Inspect CLI version/catalog only. Never spawn models or edit config.

    No supported reader of the live parent effort was established at the
    compatibility gate. The supplied session ID is merely the requested ID;
    it is not sufficient to construct a verified live snapshot.
    """
    report = {
        "codex_version": "unknown", "python_version": platform.python_version(),
        "catalog": {}, "snapshot": None,
        "checks": {key: "UNVERIFIED" for key in CHECKS}, "evidence_paths": [],
        "requested_session_id": session_id, "diagnostics": [],
    }
    directory = Path(project).resolve()
    if not directory.is_dir():
        report["diagnostics"].append("PROJECT_DIRECTORY_MISSING")
        return report
    executable = shutil.which("codex")
    if executable is None:
        local_binary = Path.home() / ".local/bin/codex"
        if local_binary.is_file():
            executable = str(local_binary)
    if executable is None:
        report["diagnostics"].append("CODEX_NOT_FOUND")
        return report
    report["executable"] = executable
    try:
        version = subprocess.run([executable, "--version"], cwd=directory, capture_output=True,
                                 text=True, check=True, timeout=15)
        match = re.fullmatch(r"codex-cli (\d+\.\d+\.\d+)", version.stdout.strip())
        if match:
            report["codex_version"] = match.group(1)
        else:
            report["diagnostics"].append("VERSION_FORMAT_UNRECOGNIZED")
    except (OSError, subprocess.SubprocessError) as error:
        report["diagnostics"].append("VERSION_READ_FAILED:" + type(error).__name__)
        return report
    if report["codex_version"] == TESTED_VERSION:
        report["checks"]["pre_dispatch_guard"] = "FAIL"
        report["diagnostics"].append("KNOWN_01571_PRETOOLUSE_ERROR_CONTINUES_TOOL_EXECUTION")
        report["source_references"] = [GUARD_SOURCE]
    else:
        report["diagnostics"].append("VERSION_NOT_CHARACTERIZED")
    try:
        result = subprocess.run([executable, "debug", "models"], cwd=directory,
                                capture_output=True, text=True, check=True, timeout=25)
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ValueError("Unexpected catalog envelope")
        for model in data["models"]:
            if not isinstance(model, dict) or model.get("slug") not in MODELS:
                continue
            levels = model.get("supported_reasoning_levels", [])
            if not isinstance(levels, list):
                continue
            available = {level.get("effort") for level in levels
                         if isinstance(level, dict) and isinstance(level.get("effort"), str)}
            report["catalog"][model["slug"]] = [effort for effort in EFFORTS if effort in available]
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        report["diagnostics"].append("CATALOG_READ_FAILED:" + type(error).__name__)
    report["diagnostics"].append("LIVE_PARENT_EFFORT_AND_TURN_NOT_VERIFIED")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--session-id")
    args = parser.parse_args()
    report = inspect_environment(args.project, args.session_id)
    report["compatible"] = is_compatible(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["compatible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
