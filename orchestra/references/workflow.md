# Work packets and lifecycle

Use the native tools available in the current host. This skill provides procedures, not a new tool server.

## Packet sent to a child

Include task ID, exact question/goal, relevant source paths, allowed writes, exclusions, dependencies already checked, expected artifacts, acceptance checks, deadline, and return format. Supply enough context to use a fresh task without copying unrelated conversation history. Explicitly say:

> Work only on this packet. Do not spawn agents or use the Orchestra bookkeeping helper. Return results, evidence, unresolved issues and any running tool-process identifiers. Do not change leader or global settings.

| Role | Expected output |
|---|---|
| worker | Changed artifacts, behavior checks, residual issues |
| researcher | Sources inspected, evidence vs inference, conflicts/gaps |
| advisor | Answer to a bounded decision, alternatives, assumptions and tradeoffs |
| reviewer | Independent acceptance assessment, actionable findings and evidence |

For a reviewed task, schedule a separate review task after the candidate artifact exists. The review task need not depend on `COMPLETE` of the task it is reviewing: that would deadlock completion. Give it the candidate result after `REVIEW_PENDING`; dependencies on other completed prerequisites can still be recorded. Do not dispatch its ready row before its packet is actually ready. Its role must be `reviewer` and its native ID must differ from the original worker's ID.

## Task and agent state are separate

Normal task flow: `WAITING → READY → RESERVED → RUNNING → REVIEW_PENDING → COMPLETE`.
Failures can become `REWORK`, `BLOCKED` or `CANCELLED`. Total attempts are 1, 2, 3. Re-planning does not erase attempts or modify an already-attempted task's contract. Dependent tasks start only after all declared dependencies are `COMPLETE`.

Agent reservation flow: `RESERVED → RUNNING`, with `IDLE`, `UNKNOWN` and `STOPPING` still occupied. `FAILED` means definite creation failure with no bound child. `CLOSED` requires native termination evidence, or definite confirmation that an unbound request was never sent. An ambiguous request retains its slot. Do not label a bound agent FAILED to release it.

Changing selection invalidates older prepared requests. Already-created children retain their recorded requested settings until actually changed or stopped; do not rewrite history. A discovered effective-setting mismatch blocks new dispatch in that run. Preserve the run and reconcile/clean up before starting a separately identified, corrected run.

## Results and independent review

Use `summary`, `artifacts`, `checks`, `sources`, `unresolved`. Each passing check includes evidence, such as a test log path, a calculated value and method, or an inspected source with a locator. A self-assigned PASS with no evidence is insufficient. Any unresolved acceptance item prevents `COMPLETE`.

For `needs_review=true`, include:

```json
"review": {"agent_id": "<owned independent reviewer ID>", "status": "PASS", "evidence": "<review output path or native message locator>"}
```

The helper checks that this is a distinct task's bound reviewer. The leader still inspects the review; a populated JSON field cannot establish truth by itself.

## Failure handling

- No available native model/effort override: do not simulate routing in prose; explain the host limitation.
- Failed check, locked database or unreadable state: do not call spawn. Keep existing agents/results intact.
- Lost spawn response: mark UNKNOWN; reconcile the native agent list and logs before retrying.
- Repeated failed acceptance: diagnose, revise the packet within its existing contract or define a new scope transparently. At the third failed attempt, BLOCKED.
- Changed scope: preserve the original task and its history; record the distinct new work. Do not invent a new ID just to bypass retry limits.
- Cancellation: stop new work; update tasks and inspect owned agents/tool sessions. Preserve partial output. Only confirmed terminal states release slots.
- No native close operation: report the idle/unconfirmed identifiers and `CLEANUP_REQUIRED`. An interrupt response that leaves an agent available is not a close confirmation.

The leader should remain the only writer of the bookkeeping database and integration files. Parallel workers must have disjoint write ownership. Store large data in files and send paths plus concise findings between agents.
