"""Orchestra skill helper: JSON input/output, local validation and records only."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import uuid

from native import inspect_environment, is_compatible
from catalog import catalog_id, intersect_catalog
from policy import validate_dispatch
from state import RunStore
from update_check import check_update

COMMANDS = ("inspect", "init", "plan", "sync-models", "check", "reserve", "bind", "update", "cleanup-plan", "report")


def catalog_details(report, native_catalog):
    catalog = intersect_catalog(report.get("catalog", {}), native_catalog)
    excluded = report.get("excluded_models", []) + [{"model": name, "reason": "native_schema_unsupported"}
                                                  for name in report.get("catalog", {}) if name not in catalog]
    return catalog, {"catalog_id": catalog_id(catalog), "catalog_source": "codex_debug_models",
                     "native_catalog": native_catalog, "catalog_observed_at": report.get("catalog_observed_at"),
                     "model_metadata": {name: details for name, details in report.get("model_metadata", {}).items() if name in catalog},
                     "routing_candidates": {family: [name for name in names if name in catalog]
                                            for family, names in report.get("routing_candidates", {}).items()},
                     "excluded_models": excluded,
                     "catalog_diagnostics": report.get("diagnostics", [])}


def sync_models(store, run_id, native_catalog=None):
    run = store.summary(run_id)["run"]
    native_catalog = native_catalog if native_catalog is not None else run.get("native_catalog")
    if native_catalog is None:
        raise ValueError("NATIVE_CATALOG_REQUIRED")
    report = inspect_environment(Path(run["project"]))
    catalog, details = catalog_details(report, native_catalog)
    store.update_catalog(run_id, catalog, details)
    return {"ok": bool(catalog), "catalog": catalog, **details}


def owned_reservation(store, run_id, reservation_id):
    for agent in store.summary(run_id)["agents"]:
        if agent["id"] == reservation_id:
            return agent
    raise ValueError("RESERVATION_NOT_OWNED_BY_RUN")


def process_command(command, payload, store=None):
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    # A workflow check, not authentication of the process invoking this helper.
    if payload.get("actor", "leader") != "leader":
        raise ValueError("LEADER_ONLY")
    if command == "inspect":
        report = inspect_environment(Path(payload.get("project", ".")))
        if "native_catalog" in payload:
            report["catalog"], details = catalog_details(report, payload["native_catalog"])
            report.update(details)
        report["native_schema_checked"] = "native_catalog" in payload
        if payload.get("check_updates", True):
            report["skill_update"] = check_update()
        report["strict_enforcement_compatible"] = is_compatible(report)
        report["mode"] = "workflow_policy"
        report["workflow_prerequisites"] = "Confirmed leader selection, available native tools/models, and sufficient native capacity are still required."
        return {"ok": bool(report["catalog"]), **report}
    if store is None:
        raise ValueError("DATABASE_REQUIRED")
    if command == "init":
        value = dict(payload)
        value.pop("actor", None)
        value.setdefault("run_id", uuid.uuid4().hex)
        value.setdefault("policy_version", "workflow-2")
        value["snapshot"] = dict(value.get("snapshot", {}))
        value["snapshot"].setdefault("selection_id", uuid.uuid4().hex)
        if "native_catalog" in value:
            report = inspect_environment(Path(value["project"]))
            value["catalog"], details = catalog_details(report, value["native_catalog"])
            value.update(details)
        elif not value.get("catalog"):
            raise ValueError("NATIVE_CATALOG_REQUIRED")
        store.create_run(value)
        return {"ok": True, "run_id": value["run_id"], "selection_id": value["snapshot"]["selection_id"],
                "catalog_id": value.get("catalog_id"), "catalog": value["catalog"]}
    run_id = payload["run_id"]
    if command == "sync-models":
        return sync_models(store, run_id, payload.get("native_catalog"))
    if command == "plan":
        store.put_tasks(run_id, payload["tasks"])
        return {"ok": True, "tasks": store.summary(run_id)["tasks"]}
    if command == "check":
        summary = store.summary(run_id)
        if summary["run"].get("catalog_source") == "codex_debug_models":
            sync_models(store, run_id, payload.get("native_catalog"))
            summary = store.summary(run_id)
        request = payload["request"]
        errors = validate_dispatch(request, summary["run"]["snapshot"], summary["run"]["catalog"], summary["run"].get("catalog_id"))
        if isinstance(request, dict) and request.get("run_id") != run_id:
            errors.append("REQUEST_ID_MISMATCH")
        if summary["problem"]:
            errors.append(summary["problem"])
        return {"ok": not errors, "errors": errors, "catalog_id": summary["run"].get("catalog_id"),
                "catalog": summary["run"]["catalog"], "note": "A successful reserve is also required before native dispatch."}
    if command == "reserve":
        request = payload["request"]
        summary = store.summary(run_id)
        existing = any(row["task_id"] == request["task_id"] and row["attempt"] == request["attempt"] for row in summary["agents"])
        if summary["run"].get("catalog_source") == "codex_debug_models" and not existing:
            sync_models(store, run_id, payload.get("native_catalog"))
        return {"ok": True, **store.reserve(run_id, request["task_id"], request["attempt"], request)}
    if command == "bind":
        owned_reservation(store, run_id, payload["reservation_id"])
        store.bind(payload["reservation_id"], payload["agent_id"], payload["actual"])
        summary = store.summary(run_id)
        return {"ok": summary["problem"] is None, "problem": summary["problem"]}
    if command == "update":
        kind = payload["kind"]
        if kind == "snapshot":
            store.update_snapshot(run_id, payload["snapshot"])
        elif kind == "task":
            store.transition_task(run_id, payload["task_id"], payload["state"], payload.get("result"))
        elif kind == "agent":
            store.mark_agent_state(run_id, payload["agent_id"], payload["state"], payload["evidence"])
        elif kind == "reservation":
            owned_reservation(store, run_id, payload["reservation_id"])
            store.mark_reservation_state(payload["reservation_id"], payload["state"], payload["evidence"])
        else:
            raise ValueError("UPDATE_KIND_UNKNOWN")
        return {"ok": True, "outcome": store.summary(run_id)["outcome"]}
    if command == "cleanup-plan":
        opened = store.list_open_agents(run_id)
        return {"ok": True, "agent_ids": [row["agent_id"] for row in opened if row["agent_id"]],
                "unknown_reservations": [row["id"] for row in opened if not row["agent_id"]],
                "open_agents": opened, "note": "Use native tools, then record actual results. This command does not stop agents."}
    if command == "report":
        summary = store.summary(run_id)
        if payload.get("target"):
            write_report(store, run_id, Path(payload["target"]))
        return {"ok": True, **summary}
    raise ValueError("COMMAND_UNKNOWN")


def write_report(store, run_id, target):
    report = store.summary(run_id)
    run = report["run"]
    snapshot = run["snapshot"]
    lines = ["# Orchestra 실행 보고서", "", f"- 실행: {run_id}", f"- 목표: {run['goal']}",
             f"- 상태: {report['outcome']}", f"- 사용/예약 중인 자리: {report['occupied']} / {run['max_agents']}",
             f"- 총괄 선택: {snapshot['model']} / {snapshot['effort']}",
             f"- 선택 근거: {snapshot['selection_source']} — {snapshot['selection_evidence']}",
             "- 관리 방식: 스킬의 배정 규칙과 로컬 검사. Codex 내부 오류까지 강제 차단하는 기능은 아님.", "",
             "## 작업 결과", ""]
    if run.get("catalog_id"):
        lines[8:8] = [f"- 모델 목록 확인: {run.get('catalog_observed_at')} ({run['catalog_id']})"]
    for task in report["tasks"]:
        lines += [f"### {task['task_id']} — {task['state']}", "",
                  "```json", json.dumps(task.get("result"), ensure_ascii=False, indent=2), "```", ""]
    lines += ["## 배정과 관측", ""]
    for agent in report["agents"]:
        record = {"task_id": agent["task_id"], "attempt": agent["attempt"], "agent_id": agent["agent_id"],
                  "state": agent["state"], "requested_model": agent["request"]["model"],
                  "requested_effort": agent["request"]["effort"], "rationale": agent["request"]["rationale"],
                  "actual": agent["actual"], "lifecycle_evidence": agent["evidence"]}
        lines += ["```json", json.dumps(record, ensure_ascii=False, indent=2), "```", ""]
    lines += ["## 정리", "", "열린 자리의 종료를 확인하기 전에는 전체 정리 완료로 보고하지 않는다.", "",
              "```json", json.dumps([{"reservation_id": row["id"], "agent_id": row["agent_id"], "state": row["state"]}
                                     for row in report["open_agents"]], ensure_ascii=False, indent=2), "```", ""]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--input", type=Path, help="JSON file; default is stdin")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read())
        if args.command != "inspect" and args.db is None:
            raise ValueError("--db is required")
        store = RunStore(args.db) if args.db is not None else None
        answer = process_command(args.command, payload, store)
        print(json.dumps(answer, ensure_ascii=False, indent=2))
        return 0 if answer.get("ok") else 2
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        answer = {"ok": False, "error": str(error), "error_type": type(error).__name__}
        print(json.dumps(answer, ensure_ascii=False))
        print("Orchestra: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
