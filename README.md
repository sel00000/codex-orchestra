**English** | [한국어](README.ko.md)

Give Orchestra a try. I'd like you to see how it works for yourself.

Orchestra coordinates multiple agents in Codex. The lead model chooses both the model and reasoning effort for each subtask.

It assigns lighter settings to straightforward tasks and higher settings to complex implementation or important reviews, always within the leader's reasoning effort cap. This directs more reasoning effort toward the work that needs it.

The goal is to maintain output quality while reducing unnecessary token use. Adjusting the model and reasoning effort to each task is expected to help reduce token use.

If you try it and find it useful, please leave a **GitHub Star ⭐**. Every star is encouraging.

# Orchestra for Codex

Orchestra is a Codex skill that builds an agent team for the task at hand. It automatically selects a model and reasoning effort for each subtask.

It uses Codex's native agent tools in Ubuntu WSL to delegate work, review results, and report back. Helper scripts built with the Python standard library check assignments and keep task records.

```text
$orchestra 5 Investigate and fix the errors in this project, then review the results.
```

The leader keeps the model and reasoning effort you selected. It chooses settings for each child task, reviews the results, and combines them into the final output. No separate background service or model API key is required, and Orchestra does not depend on OMC or OMX.

## How it works

- The number sets the maximum number of child agents that can run at once, excluding the leader. Choose 5 to 20; the default is 5. Advisors and reviewers count toward this limit, and Orchestra uses only as many agents as the work needs.
- For each assignment, the leader considers clarity, complexity, the consequences of errors, verifiability, and whether the necessary tools and source material are available.
- An advisor can use a stronger model than the leader. A child's reasoning effort must stay at or below the leader's setting.
- Orchestra tracks task dependencies, write boundaries, and retries. It records requested settings separately from values actually observed during execution.
- Invoke it with `$orchestra`. It does not create an unnecessary team for a simple task.

| Example subtask | Starting choice |
|---|---|
| Simple extraction, file listings, clearly defined small changes | An available Luna / Low or Medium |
| General implementation, analysis with several steps | An available Sol / Medium or High |
| Important design decisions, difficult result reviews | An available Astra / High, within the leader's effort cap |

For example, a Sol / High leader can combine a Luna / Low worker, a Sol / Medium implementer, and an Astra / High advisor. With an Astra / Low leader, every child task must also use Low.

The models in the table are candidates for assignment. Availability depends on your account and Codex environment. Orchestra refreshes Codex's catalog and uses only combinations allowed by both that catalog and the actual agent creation tool. See the [model selection policy](orchestra/references/routing.md) for details.

## Model changes and skill updates

Orchestra 1.1.0 follows model changes without a fixed list of model IDs. New versions such as `gpt-6.1-sol` become candidates when both Codex and the native tool support them. Within a known family, newer generations appear first; the leader still chooses according to the task.

Before new assignments, the helper checks the catalog again. It excludes models that disappear, become hidden or deprecated, or reach their published retirement time. Supported reasoning efforts come from the model metadata and the tool schema. The leader's chosen model and effort ceiling stay under your control.

Each skill invocation also checks the repository's release number. If a newer skill version is available, Orchestra reports the installed and latest versions. This is a notification on invocation; it does not install code or run a background watcher. An unavailable update check is recorded as `unverified`.

## Installation

Use Ubuntu WSL with Python 3.11 or later. Codex's agent creation tool must support setting the model and reasoning effort for each child agent. Model discovery for this release was checked with Codex CLI 0.159.2 / Python 3.12.3; the initial native task trial used CLI 0.157.1. For other versions or tool environments, check the [compatibility guide](orchestra/references/native-compatibility.md) first.

Run these commands in your WSL terminal:

```bash
git clone https://github.com/sel00000/codex-orchestra.git
cd codex-orchestra
python3 tools/install_orchestra.py
```

The installer places the skill in `~/.agents/skills/orchestra/`. If a skill with the same name already exists, it saves a backup beside the existing folder before installing. It leaves your Codex configuration and other skills unchanged. If the new skill does not appear in an open session, invoke it in a new Codex session.

To create a ZIP without installing:

```bash
python3 tools/install_orchestra.py --zip dist/orchestra.zip
```

The ZIP contains only the skill's 13 files. Tests, local run databases, and caches are excluded.

## Usage examples

```text
$orchestra Find the cause of the error in this code and verify the fix.
$orchestra 8 Map the relationships between these CAD files and identify what needs review.
$orchestra 10 Cross-check the evidence in these research materials and draft an experimental plan.
```

If the requested team limit exceeds the current session's actual agent capacity, Orchestra explains the setup needed. The number in the skill invocation does not increase Codex's own limit. See the [usage guide (Korean)](docs/usage.ko.md) for instructions on preparing a new session.

## Validation and current limitations

The **81 local tests** covering model discovery and retirement, update notifications, policy, state, commands, and packaging passed. The earlier installed-skill trial created two native child tasks whose code fix and source review results were checked. This release's model sync was checked against the actual CLI catalog; the native task trial was not repeated for this update.

- **Actual concurrent runs with 5 or 20 agents have not been verified.** Local reservation boundary tests for 5/20 slots are separate from tests of real agents running at the same time.
- If the creation tool does not expose the final effective model and reasoning effort, the actual values remain `unverified`.
- The skill manages child tasks through workflow rules and local checks. It does not enforce restrictions across the entire Codex runtime or authenticate hostile callers.
- Even when the output is complete, Orchestra reports `CLEANUP_REQUIRED` if the tools cannot confirm that the agents have terminated.
- Organizing CAD file listings does not establish that CAD editing or physical validation occurred. Summaries of research material are kept distinct from verification against full papers or experimental results.

The [validation record (Korean)](docs/validation.md) describes the scope of the reproducible local tests and the actual model runs.

## Development and testing

Run the tests on WSL/Linux without installing additional Python packages. These tests do not call models.

```bash
python3 -m unittest discover -s tests -v
```

| Path | Contents |
|---|---|
| [orchestra/SKILL.md](orchestra/SKILL.md) | Skill entry point read by Codex |
| `orchestra/references/` | Model selection, workflow, compatibility, and helper commands |
| `orchestra/scripts/` | Policy checks, atomic reservations, state records, and reporting |
| `tools/install_orchestra.py` | Installation with backups and ZIP creation |
| `tests/` | Regression tests without model calls |
| `docs/` | Korean usage guide and validation scope |

Orchestra keeps task records in `.orchestra/<run-id>/` inside the project where it runs. This repository does not include personal run records.
