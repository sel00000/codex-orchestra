"""Hand-checked fixtures for workflow-policy tests."""
from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestra/scripts"))
sys.path.insert(0, str(ROOT / "tools"))


def module(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name == name:
            raise AssertionError(f"Missing implementation: {name}") from error
        raise


def snapshot():
    return {"session_id": "s1", "selection_id": "sel1", "model": "gpt-6-sol", "effort": "high",
            "selection_source": "user_confirmed", "selection_evidence": "User selected Sol / High",
            "native_cap": 20, "native_cap_source": "launch_config",
            "native_cap_evidence": "Scoped test invocation with cap 20"}


def catalog():
    return {"gpt-6-astra": ["low", "medium", "high", "xhigh", "max"],
            "gpt-6-sol": ["low", "medium", "high", "xhigh", "max"],
            "gpt-6-luna": ["low", "medium", "high", "xhigh", "max"],
            "gpt-5.5": ["low", "medium", "high", "xhigh"]}


def task(i="t1", **updates):
    value = {"task_id": i, "depends_on": [], "write_paths": [], "acceptance": "Return checked result",
             "needs_review": False}
    value.update(updates)
    return value


def request(i="t1", **updates):
    value = {**task(i), "run_id": "r1", "attempt": 1, "role": "worker", "model": "gpt-6-luna",
             "effort": "low", "selection_id": "sel1", "rationale": "Clear bounded task, readily checked",
             "deadline_at": "2099-01-01T00:00:00Z"}
    value.update(updates)
    return value


def run(project, limit=5):
    return {"run_id": "r1", "goal": "A bounded test", "project": str(project), "max_agents": limit,
            "snapshot": snapshot(), "catalog": catalog(), "policy_version": "workflow-1"}


def result():
    return {"summary": "Checked", "artifacts": [], "sources": [], "unresolved": [],
            "checks": [{"name": "acceptance", "status": "PASS", "evidence": "Independent fixture check"}]}
