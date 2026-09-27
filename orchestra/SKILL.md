---
name: orchestra
description: Coordinate a task-scoped Codex agent team when the user invokes orchestra or asks to use this orchestration skill. Select child models and reasoning for each task while preserving the user's leader selection, with a configurable 5–20 child limit, review, and recorded cleanup.
---

# Orchestra

Use this skill when explicitly requested: `$orchestra [5–20] <goal>`.
The optional number is the maximum concurrent children, default **5**, not a target headcount. The leader is excluded; advisors and reviewers count.

This is a skill using the host's native agent tools. Its Python helpers validate proposals and keep local records. They do not call models, launch another Codex session, install hooks, or provide runtime-wide enforcement. Keep existing OMC/OMX installations and user configuration untouched; neither is a dependency.

## Start with the user's actual task

1. Preserve the chosen leader model and reasoning. Obtain the current selection and native capacity from exposed runtime information or an explicit user confirmation already in this conversation. Do not substitute config defaults, model self-identification, or an old session's settings. If missing, ask once for only the missing values while doing independent preparation.
2. Read [native-compatibility.md](references/native-compatibility.md) for the current host's tools, setup, capacity and lifecycle limits. A native cap below the user's requested cap is a setup mismatch; explain it rather than silently lowering the request. A missing per-child model/effort override means automatic model routing is unavailable on that tool surface.
3. Use `scripts/orchestra.py inspect` to obtain available model metadata. Intersect it with models and efforts accepted by the **current native tool schema**. Do not select a model merely because it is listed in a catalog. Restrict efforts to `low < medium < high < xhigh < max`; use only the seven user-approved candidates in [routing.md](references/routing.md).
4. Make a small dependency graph with concrete outputs, acceptance checks, write ownership and a deadline for each assignment. Use only as many children as useful. Keep final integration and user communication with the leader. For a trivial task, complete it directly rather than fabricating five jobs; explain that no team was needed.

## Choose models automatically

Read [routing.md](references/routing.md). Assess clarity, complexity, consequences of error, verifiability and tool/data readiness **per subtask**, not just by project domain.

- Straightforward extraction or routine changes: start from an available Luna with low/medium effort.
- Ordinary implementation and connected analysis: start from an available Sol with medium/high effort.
- Important design choices or difficult review: consider Astra/high when within the leader's ceiling.
- A stronger model than the leader is allowed. Every child effort must remain at or below the leader's selected effort. Specify **both model and effort**; never silently inherit defaults.
- Use `fork_turns="none"` (or the native equivalent for a fresh task) when specifying overrides, and supply a compact task packet. Full-history forks can forbid overrides. Follow the actual tool's contract.

Record one concrete reason for each assignment. These are starting policies, not measured price/performance guarantees. Model escalation needs a failure diagnosis or task reason; it must not lower the acceptance standard.

## Record before dispatch

Use the helper relative to this skill's installed location; do not assume the source workspace path. Read [workflow.md](references/workflow.md) and [commands.md](references/commands.md) for schemas and executable command examples.

Keep one database per user task, normally `<project>/.orchestra/<run-id>/state.sqlite3`, plus JSON inputs and a readable result report. Choose unique run IDs. Preserve these artifacts on completion.

1. `init`: record the confirmed leader selection, native capacity and their evidence. `selection_id` is a local consistency token, not a native identity attestation.
2. `plan`: record tasks with dependencies and non-overlapping concurrent write scopes. A task contract cannot be silently changed after its first attempt. Make a new task for an actual scope change.
3. `check`, then `reserve`: check the selected model/effort and reserve a slot atomically. A storage error or rejected check means **do not dispatch**. Only `action="spawn"` permits one native spawn; `wait_existing` means reconcile the existing call. Never interpret a lost response as a failed spawn.
4. Call the **native** spawn tool yourself. Children must return their result; they must not create additional agents, update the run database, or change leader settings.
5. `bind`: record the native child identifier/task name and the creation response evidence. Record effective model/effort only when actually observable. Otherwise use null values and `configuration_source="unverified"`; retain requested values separately.
6. Check returned work and record `REVIEW_PENDING`, followed by verified `COMPLETE`, diagnosed `REWORK`, or `BLOCKED`. Use a separate reviewer for important decisions; mark those tasks `needs_review=true`. An independent reviewer is not proof of truth without evidence.

Only three total attempts per task are allowed. Never reset attempts by re-planning the same task. Failed dependencies do not authorize dependent work. Root-only helper checks are workflow safeguards, not authentication against an uncooperative process.

## Changes, interruption and cleanup

If the user changes the leader selection, update the snapshot with a new selection ID before any new dispatch. Discard prepared requests using the old ID. Inspect already-sent work; stop/reassign affected work where the native tools permit it. The skill does not promise automatic detection of every out-of-band UI change.

Waiting, unknown, stopping, and idle child records still hold a slot. A returned answer alone is not confirmed termination. Before reusing a slot, observe a native close/terminal state with the semantics described by that tool. If only an interrupt-to-idle tool exists, record IDLE and explain cleanup remains unconfirmed; do not invent a close API or call it CLOSED.

On completion or cancellation, get `cleanup-plan`, stop/close **only this run's owned agents and known long-running tool processes**, record the actual results, and write `report`. Preserve outputs and logs. Do not restart WSL, kill unrelated Codex processes, or discard results to obtain a clean status.

If the native surface cannot confirm termination, leave `CLEANUP_REQUIRED` and list the remaining identifiers. If all available slots remain occupied, finish what the leader can do without additional children and report the remaining delegation limitation; do not bypass the cap through another session.

## Report clearly

Return the requested artifact, what was verified, unresolved items, model/effort choices with reasons, and cleanup status. Separate:

- requested settings from observed effective settings;
- helper tests from actual native concurrency;
- source inspection, calculations/simulations, and physical validation;
- file creation, content verification, and actual CAD/research tool execution.

A 20-slot configuration is not evidence that 20 models ran concurrently. Never claim validation that was not performed. Keep routine user-facing updates short and avoid exposing implementation detail unless it explains a decision or limitation.
