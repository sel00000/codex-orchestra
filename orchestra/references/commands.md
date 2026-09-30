# Helper commands

Only the leader uses these helpers. They never dispatch models or stop native agents. The database is a local task ledger, not a trusted runtime identity service.

All commands accept a JSON object via stdin or `--input FILE` and emit JSON. Exit **0** is a successful helper operation; exit **2** is a rejected operation or unavailable prerequisite. A report command can return 0 while reporting `BLOCKED` or `CLEANUP_REQUIRED`: read `outcome` too.

```bash
ORCHESTRA_SKILL="$HOME/.agents/skills/orchestra"
python3 "$ORCHESTRA_SKILL/scripts/orchestra.py" inspect --input inspect.json
python3 "$ORCHESTRA_SKILL/scripts/orchestra.py" init --db .orchestra/example/state.sqlite3 --input init.json
```

`inspect.json`: `{"project":"/absolute/project/path","native_catalog":{"gpt-6.1-sol":["low","medium","high"],"gpt-6-luna":["low","medium","high"]}}`. Replace this example with the models/efforts in the current native tool schema. Without `native_catalog`, inspection only discovers catalog entries and reports `native_schema_checked=false`. `check_updates=false` skips the optional network request for an offline diagnostic.

`init.json`, with values actually confirmed for this run:

```json
{
  "run_id": "example",
  "goal": "The user's concrete goal",
  "project": "/absolute/project/path",
  "max_agents": 5,
  "native_catalog": {
    "gpt-6.1-sol": ["low", "medium", "high"],
    "gpt-6-luna": ["low", "medium", "high"]
  },
  "snapshot": {
    "session_id": "current-native-session-id-or-explicitly-labelled-local-id",
    "model": "gpt-6-sol",
    "effort": "high",
    "selection_source": "user_confirmed",
    "selection_evidence": "User confirmed Sol / High in the current conversation",
    "native_cap": 5,
    "native_cap_source": "launch_config",
    "native_cap_evidence": "This session was started with the documented cap of 5"
  }
}
```

Replace examples with facts; do not manufacture confirmations. `init` generates `selection_id` if omitted, refreshes the Codex catalog, and intersects it with `native_catalog`. It returns `catalog_id` and the filtered candidates. Keep those IDs for subsequent requests. Supplying `catalog` directly remains available for offline fixtures and explicitly evidenced snapshots, but does not enable automatic refresh; use `sync-models` with current `native_catalog` to enable it.

Normal `inspect` also reports `skill_update` using the installed `release.json` and the upstream release number. `update_available` is an update notification; `unverified` is a failed/unavailable check. The helper never installs remote code. Model discovery uses Codex; the optional release check uses a four-second read-only request to the repository.

Each subsequent command uses the same `--db` and a JSON file with `run_id`. Default `actor` is `leader`; any other actor is rejected as workflow misuse. This flag does not authenticate a hostile caller.

| Command | Other fields | Effect |
|---|---|---|
| `plan` | `tasks` | Record validated dependency graph/contracts |
| `sync-models` | optional `native_catalog` if already recorded | Refresh model/effort availability and retirement metadata |
| `check` | `request` | Validate selection, model and effort without reservation |
| `reserve` | `request` | Atomically validate plan/dependencies/paths/cap and claim one slot |
| `bind` | `reservation_id`, `agent_id`, `actual` | Record creation result; mismatch blocks new assignments |
| `update` | `kind` and fields below | Record observed task/agent/selection state |
| `cleanup-plan` | none | List this run's bound agents and unknown reservations |
| `report` | optional `target` Markdown path | Return state and optionally save readable report |

A plan task:

```json
{"task_id":"inventory","depends_on":[],"write_paths":[],"acceptance":"Return a source-backed file inventory","needs_review":false}
```

A `request` uses exactly the task's `depends_on`, `write_paths` and `acceptance`, plus:

```json
{
  "run_id":"example",
  "task_id":"inventory",
  "attempt":1,
  "role":"researcher",
  "model":"gpt-6-luna",
  "effort":"low",
  "selection_id":"the-id-returned-by-init",
  "catalog_id":"the-id-returned-by-init-or-sync-models",
  "depends_on":[],
  "write_paths":[],
  "acceptance":"Return a source-backed file inventory",
  "rationale":"Bounded source inventory with direct checks",
  "deadline_at":"2099-01-01T00:00:00Z"
}
```

Replace the illustrative timestamp with a realistic task deadline. Expired requests fail. `reserve` returns `action=spawn` exactly once for a stored attempt. Duplicate requests return `wait_existing`; changed payloads under the same attempt are rejected. Never spawn again from a duplicate response.

For a live catalog run, `check` and a new `reserve` refresh models automatically. A changed `catalog_id` returns `CATALOG_STALE`; choose/recheck a request using the new ID. Existing reservations remain reconcilable even if their model has since disappeared. The refresh preserves leader selection, attempts, results and occupied slots. A failed catalog read leaves no candidates for a new dispatch. To reflect a changed native tool schema, include its new `native_catalog` in `check`, `reserve` or `sync-models`.

After the one native call, `bind.actual` can be:

```json
{"model":null,"effort":null,"configuration_source":"unverified","evidence":"Native spawn returned task /root/inventory; response saved at ..."}
```

If effective settings are observable, record them with `configuration_source="runtime_observed"` and a locator. Never copy requested values into actual fields just to fill them.

## Updates

- Task: `{"run_id":"example","kind":"task","task_id":"inventory","state":"REVIEW_PENDING","result":{...}}`. Use COMPLETE only after acceptance checks.
- Bound agent: `{"run_id":"example","kind":"agent","agent_id":"/root/inventory","state":"IDLE","evidence":"Native interrupt leaves this agent available"}`. CLOSED requires termination evidence.
- Unknown/failed creation: `{"run_id":"example","kind":"reservation","reservation_id":"...","state":"UNKNOWN","evidence":"Spawn reply was lost"}`. FAILED is only for definite creation failure without a bound child.
- Selection: `{"run_id":"example","kind":"snapshot","snapshot":{...}}`. Include all fields and a new `selection_id`. Only record the user's actual changed selection.

Result:

```json
{
  "summary":"What was completed",
  "artifacts":["/absolute/path/to/output"],
  "checks":[{"name":"source comparison","status":"PASS","evidence":"Source and comparison result locator"}],
  "sources":["Inspected source locator"],
  "unresolved":[]
}
```

Do not invent artifacts, sources or passing checks. Failed/unfinished work can be recorded with REWORK or BLOCKED. A `needs_review=true` task additionally needs the independent review structure in [workflow.md](workflow.md).

Get `cleanup-plan`, perform native cleanup, update its actual outcome, then `report` with a target path. Preserve the database and artifacts on completion or interruption. Do not erase records to free slots.
