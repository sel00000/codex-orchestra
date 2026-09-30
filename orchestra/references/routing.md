# Task-level routing

The leader makes the decision; the helper checks its constraints. Do not ask the user to pick each worker's model unless they request that control.

## Evaluate each task

| Criterion | Lower effort/model may suffice | Stronger reasoning or independent review is justified |
|---|---|---|
| Clarity | Fixed inputs, explicit transformation | Ambiguous requirements or competing interpretations |
| Complexity | Local change, few dependencies | Cross-module/system interactions, difficult inference |
| Error impact | Easily reversible draft | Design choice affects downstream implementation, costly experiment or fabrication |
| Verifiability | Objective inexpensive checks | Evidence conflicts, weak oracle, assumptions drive the conclusion |
| Tools and data | Required tools and inputs available | Missing tools, inaccessible sources, unsupported format |

Missing CAD tools, unavailable research sources or absent measurements are not solved by choosing a larger model. First obtain the required input/tool within the authorized scope, or bound the deliverable honestly.

## Discover candidates at execution time

Model IDs are not an allowlist in the skill. `codex debug models` requests a refreshed catalog from Codex; the helper uses that response as availability metadata and intersects it with the current spawn tool's accepted overrides. Service availability can still differ from catalog metadata. A failed catalog read clears availability for new assignments rather than reusing a stored list.

| Family | Starting use |
|---|---|
| Luna | Bounded extraction, inventory, routine changes |
| Sol | General implementation, debugging, connected analysis |
| Astra | Consequential design, difficult synthesis or independent review |
| Terra | Balanced alternative for straightforward work |
| Legacy | Older fallback when available and appropriate |
| Unclassified | Read the current model description and explain the task fit; do not invent a role or performance ranking |

Within a known family, candidates are ordered by numeric generation, for example `gpt-6.1-sol` before `gpt-6-sol`. Prefer the current generation when it fits the task; the ordering is not a cost or accuracy benchmark. Future versions and new families do not require another hardcoded-name patch. Select only a candidate in the filtered `catalog`, with a concrete rationale.

Hidden/deprecated models and those absent from the current response are excluded. If `upgrade.retirement_at` has passed, exclude the model even if a cached response still lists it. Upcoming retirement and the named replacement remain metadata for the leader. An invalid retirement date excludes that entry pending clarification. Do not change the chosen leader automatically.

The approved effort range remains Low, Medium, High, Extra high (`xhigh`), Max. Ultra and unfamiliar effort names are excluded even when the catalog lists them. A model only receives an effort supported by both its metadata and the native tool, at or below the leader ceiling.

Live runs retain `catalog_id` as a consistency token. Changed model/effort availability invalidates prepared requests. This token is not proof of a live service or authentication of the catalog.

## Select effort independently of model

1. Start at low for explicit, easy-to-check work; medium for ordinary multi-step work.
2. Use high for interdependent reasoning, consequential choices or difficult review when the leader ceiling allows it.
3. Use xhigh/max only with a specific difficulty or diagnosis, within both the model's supported range and the leader ceiling.
4. If the desired effort exceeds the ceiling, reformulate the assignment, gather better evidence, or use a stronger allowed model at an allowed effort. Do not silently increase the leader's setting or weaken verification.

Example: leader Sol/High → worker Luna/Low, implementer Sol/Medium, advisor Astra/High. Leader Astra/Low → no child above Low; Astra/High is unavailable under that ceiling.

Record the decisive facts, for example: “Astra/High for a mechanism choice affecting three CAD assemblies; alternatives conflict and there is no direct fit test.” Avoid fabricated scores, confidence percentages, price tables or claims that one model guarantees accuracy.

## Evidence by domain

- Coding: inspect the changed behavior and run proportionate tests/builds. A passing syntax check does not establish application behavior.
- CAD/hardware: check units, coordinate conventions, source files and available open/edit/save/reopen tools. A parts inventory or software simulation does not establish fit, strength, fabrication or electrical performance.
- Research: distinguish primary-source observations, interpretations and proposed experiments. Preserve source conflicts. Do not claim a paper was read from a search snippet.
- Documents/data: separate file creation from formula/content/render checks. Use actual values and inspect representative output when relevant.
