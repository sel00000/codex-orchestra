"""Atomic local workflow records. Native calls remain the leader's responsibility."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from policy import normalize_limit, paths_overlap, text, validate_dispatch, validate_graph, validate_result, validate_selection

RELEASED = ("CLOSED", "FAILED")
AGENT_STATES = ("RESERVED", "RUNNING", "IDLE", "UNKNOWN", "STOPPING", "CLOSED", "FAILED")
TASK_STATES = ("WAITING", "READY", "RESERVED", "RUNNING", "REVIEW_PENDING", "COMPLETE", "REWORK", "BLOCKED", "CANCELLED")


class CapacityFull(ValueError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RunStore:
    def __init__(self, db):
        self.db = Path(db)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL, problem TEXT);
                CREATE TABLE IF NOT EXISTS tasks (run_id TEXT, id TEXT, data TEXT NOT NULL, state TEXT NOT NULL,
                    result TEXT, PRIMARY KEY(run_id,id));
                CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL, state TEXT NOT NULL, agent_id TEXT, request TEXT NOT NULL, actual TEXT,
                    evidence TEXT, UNIQUE(run_id,task_id,attempt), UNIQUE(run_id,agent_id));
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, run_id TEXT, at TEXT, kind TEXT, data TEXT);
            """)

    def connect(self):
        connection = sqlite3.connect(self.db, timeout=0.5)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def event(connection, run_id, kind, value):
        connection.execute("INSERT INTO events(run_id,at,kind,data) VALUES(?,?,?,?)",
                           (run_id, datetime.now(timezone.utc).isoformat(), kind, encode(value)))

    @staticmethod
    def get_run(connection, run_id):
        row = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("RUN_NOT_FOUND")
        return json.loads(row["data"]), row["problem"]

    @staticmethod
    def get_task(connection, run_id, task_id):
        row = connection.execute("SELECT * FROM tasks WHERE run_id=? AND id=?", (run_id, task_id)).fetchone()
        if row is None:
            raise ValueError("TASK_NOT_FOUND")
        return row

    @staticmethod
    def open_rows(connection, run_id):
        return connection.execute("SELECT * FROM agents WHERE run_id=? AND state NOT IN ('CLOSED','FAILED') ORDER BY rowid", (run_id,)).fetchall()

    def create_run(self, run):
        for key in ("run_id", "goal", "project"):
            if not text(run.get(key)):
                raise ValueError(key.upper() + "_REQUIRED")
        errors = validate_selection(run.get("snapshot"))
        if errors:
            raise ValueError(",".join(errors))
        limit = normalize_limit(run.get("max_agents"))
        if limit > run["snapshot"]["native_cap"]:
            raise ValueError("NATIVE_CAP_BELOW_REQUEST")
        if not isinstance(run.get("catalog"), dict) or not run["catalog"]:
            raise ValueError("CATALOG_REQUIRED")
        value = {**run, "max_agents": limit, "project": str(Path(run["project"]).resolve())}
        with self.transaction() as connection:
            connection.execute("INSERT INTO runs(id,data) VALUES(?,?)", (run["run_id"], encode(value)))
            self.event(connection, run["run_id"], "init", value)

    def put_tasks(self, run_id, tasks):
        with self.transaction() as connection:
            self.get_run(connection, run_id)
            existing = {row["id"]: row for row in connection.execute("SELECT * FROM tasks WHERE run_id=?", (run_id,))}
            errors = validate_graph(tasks)
            # New tasks may depend on previously recorded tasks.
            errors = [error for error in errors if error != "DEPENDENCY_MISSING"]
            combined = {key: json.loads(row["data"]) for key, row in existing.items()}
            combined.update({task["task_id"]: task for task in tasks if isinstance(task, dict) and text(task.get("task_id"))})
            errors += validate_graph(list(combined.values()))
            if errors:
                raise ValueError(",".join(sorted(set(errors))))
            for task in tasks:
                task_id = task["task_id"]
                if task_id in existing:
                    if json.loads(existing[task_id]["data"]) == task:
                        continue
                    attempts = connection.execute("SELECT COUNT(*) FROM agents WHERE run_id=? AND task_id=?", (run_id, task_id)).fetchone()[0]
                    if attempts or existing[task_id]["state"] not in ("WAITING", "READY"):
                        raise ValueError("ACTIVE_TASK_CONTRACT_IMMUTABLE")
                    connection.execute("UPDATE tasks SET data=? WHERE run_id=? AND id=?", (encode(task), run_id, task_id))
                else:
                    connection.execute("INSERT INTO tasks VALUES(?,?,?,?,NULL)", (run_id, task_id, encode(task), "WAITING"))
            self.refresh(connection, run_id)
            self.event(connection, run_id, "plan", tasks)

    @staticmethod
    def refresh(connection, run_id):
        rows = connection.execute("SELECT * FROM tasks WHERE run_id=?", (run_id,)).fetchall()
        states = {row["id"]: row["state"] for row in rows}
        changed = True
        while changed:
            changed = False
            for row in rows:
                current = states[row["id"]]
                if current not in ("WAITING", "READY"):
                    continue
                deps = json.loads(row["data"])["depends_on"]
                state = "READY" if all(states.get(dep) == "COMPLETE" for dep in deps) else "WAITING"
                if any(states.get(dep) in ("BLOCKED", "CANCELLED") for dep in deps):
                    state = "BLOCKED"
                if state != current:
                    states[row["id"]] = state
                    connection.execute("UPDATE tasks SET state=? WHERE run_id=? AND id=?", (state, run_id, row["id"]))
                    changed = True

    def update_snapshot(self, run_id, snapshot):
        errors = validate_selection(snapshot)
        if errors:
            raise ValueError(",".join(errors))
        with self.transaction() as connection:
            run, _ = self.get_run(connection, run_id)
            if snapshot["session_id"] != run["snapshot"]["session_id"]:
                raise ValueError("SESSION_MISMATCH")
            if snapshot == run["snapshot"]:
                return
            if snapshot["selection_id"] == run["snapshot"]["selection_id"]:
                raise ValueError("NEW_SELECTION_ID_REQUIRED")
            if snapshot["native_cap"] < run["max_agents"]:
                raise ValueError("NATIVE_CAP_BELOW_REQUEST")
            run["snapshot"] = snapshot
            connection.execute("UPDATE runs SET data=? WHERE id=?", (encode(run), run_id))
            self.event(connection, run_id, "selection_changed", snapshot)

    def update_catalog(self, run_id, catalog, details):
        """Update future assignments while preserving existing agents and results."""
        if not isinstance(catalog, dict) or not isinstance(details, dict):
            raise ValueError("CATALOG_REQUIRED")
        with self.transaction() as connection:
            run, _ = self.get_run(connection, run_id)
            previous = run.get("catalog_id")
            run.update(details)
            run["catalog"] = catalog
            connection.execute("UPDATE runs SET data=? WHERE id=?", (encode(run), run_id))
            if previous != run.get("catalog_id"):
                self.event(connection, run_id, "catalog_changed", {"previous": previous, **details, "catalog": catalog})

    def reserve(self, run_id, task_id, attempt, request):
        with self.transaction() as connection:
            run, problem = self.get_run(connection, run_id)
            if (request["run_id"], request["task_id"], request["attempt"]) != (run_id, task_id, attempt):
                raise ValueError("REQUEST_ID_MISMATCH")
            previous = connection.execute("SELECT * FROM agents WHERE run_id=? AND task_id=? AND attempt=?", (run_id, task_id, attempt)).fetchone()
            if previous:
                if json.loads(previous["request"]) != request:
                    raise ValueError("DISPATCH_CONFLICT")
                return {"reservation_id": previous["id"], "state": previous["state"], "agent_id": previous["agent_id"], "action": "wait_existing"}
            if problem:
                raise ValueError(problem)
            errors = validate_dispatch(request, run["snapshot"], run["catalog"], run.get("catalog_id"))
            if errors:
                raise ValueError(",".join(errors))
            task = self.get_task(connection, run_id, task_id)
            if task["state"] not in ("READY", "REWORK"):
                raise ValueError("TASK_NOT_READY")
            definition = json.loads(task["data"])
            if any(request[key] != definition[key] for key in ("depends_on", "write_paths", "acceptance")):
                raise ValueError("TASK_CONTRACT_MISMATCH")
            if any(self.get_task(connection, run_id, dep)["state"] != "COMPLETE" for dep in definition["depends_on"]):
                raise ValueError("DEPENDENCY_NOT_COMPLETE")
            maximum = connection.execute("SELECT COALESCE(MAX(attempt),0) FROM agents WHERE run_id=? AND task_id=?", (run_id, task_id)).fetchone()[0]
            if attempt != maximum + 1:
                raise ValueError("ATTEMPT_SEQUENCE_INVALID")
            active = self.open_rows(connection, run_id)
            if any(row["task_id"] == task_id for row in active):
                raise ValueError("PREVIOUS_ATTEMPT_STILL_OPEN")
            if len(active) >= run["max_agents"]:
                raise CapacityFull("CAPACITY_FULL")
            for row in active:
                paths = json.loads(row["request"])["write_paths"]
                if any(paths_overlap(a, b, run["project"]) for a in request["write_paths"] for b in paths):
                    raise ValueError("WRITE_CONFLICT")
            identifier = uuid.uuid4().hex
            connection.execute("INSERT INTO agents(id,run_id,task_id,attempt,state,request) VALUES(?,?,?,?,?,?)",
                               (identifier, run_id, task_id, attempt, "RESERVED", encode(request)))
            connection.execute("UPDATE tasks SET state='RESERVED' WHERE run_id=? AND id=?", (run_id, task_id))
            self.event(connection, run_id, "reserve", {"reservation_id": identifier, "request": request})
            return {"reservation_id": identifier, "state": "RESERVED", "agent_id": None, "action": "spawn"}

    def bind(self, reservation_id, agent_id, actual):
        if not text(agent_id) or not isinstance(actual, dict) or not text(actual.get("evidence")):
            raise ValueError("NATIVE_BIND_EVIDENCE_REQUIRED")
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM agents WHERE id=?", (reservation_id,)).fetchone()
            if row is None or row["state"] in RELEASED:
                raise ValueError("RESERVATION_NOT_OPEN")
            if row["agent_id"] and row["agent_id"] != agent_id:
                raise ValueError("AGENT_ALREADY_BOUND")
            requested = json.loads(row["request"])
            previous_actual = json.loads(row["actual"]) if row["actual"] else {}
            observed = {key: actual.get(key) if actual.get(key) is not None else previous_actual.get(key)
                        for key in ("model", "effort")}
            observed["configuration_source"] = (actual.get("configuration_source")
                if actual.get("configuration_source") not in (None, "unverified")
                else previous_actual.get("configuration_source", "unverified"))
            observed["evidence"] = actual["evidence"]
            mismatch = any(observed[key] is not None and observed[key] != requested[key] for key in ("model", "effort"))
            task = self.get_task(connection, row["run_id"], row["task_id"])
            agent_state = row["state"] if row["agent_id"] else ("RUNNING" if task["state"] == "RESERVED" else "STOPPING")
            connection.execute("UPDATE agents SET agent_id=?,actual=?,state=? WHERE id=?",
                               (agent_id, encode(observed), "UNKNOWN" if mismatch else agent_state, reservation_id))
            if task["state"] == "RESERVED" and not row["agent_id"]:
                connection.execute("UPDATE tasks SET state='RUNNING' WHERE run_id=? AND id=?", (row["run_id"], row["task_id"]))
            if mismatch:
                connection.execute("UPDATE runs SET problem='CONFIG_MISMATCH' WHERE id=?", (row["run_id"],))
            self.event(connection, row["run_id"], "bind", {"reservation_id": reservation_id, "agent_id": agent_id, "actual": observed})

    def mark_reservation_state(self, reservation_id, state, evidence):
        if state not in AGENT_STATES or not text(evidence):
            raise ValueError("STATE_AND_EVIDENCE_REQUIRED")
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM agents WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                raise ValueError("RESERVATION_NOT_FOUND")
            if row["state"] in RELEASED and state != row["state"]:
                raise ValueError("RELEASED_RESERVATION_IMMUTABLE")
            if state == "FAILED" and row["agent_id"]:
                raise ValueError("BOUND_AGENT_REQUIRES_CONFIRMED_CLOSE")
            connection.execute("UPDATE agents SET state=?,evidence=? WHERE id=?", (state, evidence, reservation_id))
            self.event(connection, row["run_id"], "agent_state", {"reservation_id": reservation_id, "state": state, "evidence": evidence})

    def mark_agent_state(self, run_id, agent_id, state, evidence):
        with self.connect() as connection:
            row = connection.execute("SELECT id FROM agents WHERE run_id=? AND agent_id=?", (run_id, agent_id)).fetchone()
        if row is None:
            raise ValueError("OWNED_AGENT_NOT_FOUND")
        self.mark_reservation_state(row["id"], state, evidence)

    def transition_task(self, run_id, task_id, state, result=None):
        if state not in TASK_STATES:
            raise ValueError("TASK_STATE_INVALID")
        with self.transaction() as connection:
            row = self.get_task(connection, run_id, task_id)
            if row["state"] in ("COMPLETE", "CANCELLED") and state != row["state"]:
                raise ValueError("TERMINAL_TASK_IMMUTABLE")
            allowed = {
                "WAITING": {"BLOCKED", "CANCELLED"}, "READY": {"BLOCKED", "CANCELLED"},
                "RESERVED": {"REWORK", "BLOCKED", "CANCELLED"},
                "RUNNING": {"REVIEW_PENDING", "REWORK", "BLOCKED", "CANCELLED"},
                "REVIEW_PENDING": {"COMPLETE", "REWORK", "BLOCKED", "CANCELLED"},
                "REWORK": {"BLOCKED", "CANCELLED"}, "BLOCKED": {"REWORK", "CANCELLED"},
            }
            if state != row["state"] and state not in allowed.get(row["state"], set()):
                raise ValueError("TASK_TRANSITION_INVALID")
            if state == "COMPLETE":
                errors = validate_result(result)
                if errors:
                    raise ValueError(",".join(errors))
                if json.loads(row["data"]).get("needs_review"):
                    review = result.get("review", {})
                    reviewer = connection.execute("SELECT task_id,request FROM agents WHERE run_id=? AND agent_id=?",
                                                  (run_id, review.get("agent_id"))).fetchone()
                    if (not reviewer or reviewer["task_id"] == task_id or json.loads(reviewer["request"])["role"] != "reviewer"
                            or review.get("status") != "PASS" or not text(review.get("evidence"))):
                        raise ValueError("INDEPENDENT_REVIEW_REQUIRED")
            if state == "REWORK":
                attempts = connection.execute("SELECT COALESCE(MAX(attempt),0) FROM agents WHERE run_id=? AND task_id=?", (run_id, task_id)).fetchone()[0]
                if attempts >= 3:
                    state = "BLOCKED"
            connection.execute("UPDATE tasks SET state=?,result=? WHERE run_id=? AND id=?", (state, encode(result), run_id, task_id))
            self.refresh(connection, run_id)
            self.event(connection, run_id, "task_state", {"task_id": task_id, "state": state, "result": result})

    def summary(self, run_id):
        with self.connect() as connection:
            run, problem = self.get_run(connection, run_id)
            tasks = [{**json.loads(row["data"]), "state": row["state"], "result": json.loads(row["result"]) if row["result"] else None}
                     for row in connection.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY rowid", (run_id,))]
            agents = [{**dict(row), "request": json.loads(row["request"]), "actual": json.loads(row["actual"]) if row["actual"] else None}
                      for row in connection.execute("SELECT * FROM agents WHERE run_id=? ORDER BY rowid", (run_id,))]
            events = [{**dict(row), "data": json.loads(row["data"])} for row in connection.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,))]
        open_agents = [row for row in agents if row["state"] not in RELEASED]
        terminal = bool(tasks) and all(task["state"] in ("COMPLETE", "BLOCKED", "CANCELLED") for task in tasks)
        outcome = "RUNNING"
        if open_agents and (terminal or problem):
            outcome = "CLEANUP_REQUIRED"
        elif problem or any(task["state"] == "BLOCKED" for task in tasks):
            outcome = "BLOCKED"
        elif terminal:
            outcome = "SUCCESS" if all(task["state"] == "COMPLETE" for task in tasks) else "CANCELLED"
        retry_counts = {task["task_id"]: max([row["attempt"] - 1 for row in agents if row["task_id"] == task["task_id"]] or [0]) for task in tasks}
        return {"run": run, "problem": problem, "occupied": len(open_agents), "retry_counts": retry_counts,
                "tasks": tasks, "agents": agents, "open_agents": open_agents, "events": events, "outcome": outcome}

    def list_open_agents(self, run_id):
        return self.summary(run_id)["open_agents"]
