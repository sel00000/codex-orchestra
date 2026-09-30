# Native Codex compatibility

Characterized target: Ubuntu WSL, Codex CLI **0.157.1**, Python **3.12.3**. Helpers require Python 3.11+ and only the standard library.

Model discovery for Orchestra 1.1.0 was also checked with CLI **0.159.2**. That metadata check does not characterize its complete agent runtime. Known family versions are discovered from the current catalog, not a pinned ID list. Native tool schemas, effective settings, capacity and termination semantics still require current evidence.

## Supported management mode

Orchestra is a **workflow-policy skill**, explicitly approved after a native probe demonstrated that PreToolUse hook errors can allow tool execution to continue. It does not install or depend on a hook for enforcement.

`native.py` retains that strict diagnostic. `strict_enforcement_compatible=false` in `orchestra.py inspect` does not disable the approved workflow mode. Assignment checks and honest reporting still apply. The pinned source agrees with the observed error behavior. [Codex 0.157.1 source](https://raw.githubusercontent.com/openai/codex/rust-v0.157.1/codex-rs/hooks/src/events/pre_tool_use.rs)

## Actual tool surface

- Use the schema in the current context, not an API copied from another surface. Observed V2 spawn uses task_name, model, reasoning_effort, fork_turns and message; its response identifies a task such as /root/worker.
- Missing per-child overrides mean automatic model routing is unavailable. Writing the desired model in a prompt is not a model change.
- Full-history forks can prohibit overrides; use fresh packets with fork_turns=none when supported.
- Catalog metadata can select a backend even when its feature flag is false. Do not infer the actual backend from one flag.
- The tool can accept fewer models than the catalog. Intersect both before selecting a child.

## Leader selection and observed settings

The observed pre-tool hook exposes caller model, session/turn IDs and requested child values, but not caller reasoning effort. Temporary probe transcript paths were null. Config defaults do not prove the current UI selection.

Use current runtime information when available. Otherwise use the user's explicit confirmation as selection_source=user_confirmed with evidence. Do not label it runtime-verified. Reuse the confirmation within the task unless settings change or become unclear. Changes require a new local selection_id, which is a consistency token rather than a native identity attestation.

A creation response containing only a task name does not establish effective child model/effort. Preserve requested values separately; use null actual fields and configuration_source=unverified.

## Capacity and preparation

The requested child cap is 5–20, excluding the leader. The native session must permit at least that many. Local records count reserved, running, waiting/idle, stopping and unknown children, releasing only with evidence.

The characterized schema includes agents.max_concurrent_threads_per_session; older paths also use agents.max_threads. To prepare a **new** WSL Codex session, per-invocation settings can be used, for example:

```bash
codex -c 'agents.enabled=true' -c 'agents.max_concurrent_threads_per_session=20' -c 'agents.max_threads=20'
```

These arguments leave the configured model/effort untouched. Choose the intended leader in the new session and invoke the skill. This is configuration, not proof that 20 models ran. It does not change a running session. If a setting is rejected or the runtime exposes a smaller cap, report the mismatch. Do not change global config, force a restart or silently lower the user's requested cap.

The old max_depth setting does not constrain V2 the same way as V1. Do not claim it prevents nested spawning on every backend; tell children to return work to the leader.

## Completion and cleanup

Use an explicit native close operation when available. An operation that interrupts work while leaving an agent available for follow-up is not termination: record IDLE or STOPPING. A final answer alone is not termination evidence.

Completed artifacts can coexist with CLEANUP_REQUIRED. List remaining owned identifiers. Do not free uncertain slots or kill unrelated processes. Session exit may dispose of a task-scoped team, but report only lifecycle evidence actually exposed by the host.

## Verification limits

Local helper tests exercise capacities 5 and 20, racing reservations, lost replies, retries, ownership, selection changes and evidence handling. Actual native concurrency and termination must be reported separately. A configurable 20-slot ledger is not a 20-model concurrency or performance claim.

For an uncharacterized CLI version, re-check its schema and a bounded native call; leave unknown details explicit. The strict diagnostic treats unknown versions as unverified.
