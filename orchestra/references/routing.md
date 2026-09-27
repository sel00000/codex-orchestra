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

## Candidate models

Use the intersection of this list, the live catalog, and the current spawn tool's accepted overrides. No implicit fallback to an unlisted model. If the preferred candidate is unavailable, pick another supported candidate and record why; if none fits, report the limitation.

| Candidate | Starting use, based on the user's model descriptions |
|---|---|
| `gpt-6-luna` | Bounded extraction, inventory, routine changes |
| `gpt-6-sol` | General implementation, debugging, connected analysis |
| `gpt-6-astra` | Consequential design, difficult synthesis or independent review |
| `gpt-5.6-luna` | Older lightweight alternative when available/suitable |
| `gpt-5.6-sol` | Older coding alternative when available/suitable |
| `gpt-5.6-terra` | Older straightforward-work alternative |
| `gpt-5.5` | Legacy alternative; do not use Max unless the approved policy is explicitly changed |

The approved effort range is Low, Medium, High, Extra high (`xhigh`), Max. The seven-model policy excludes Ultra even when the catalog lists it. The observed GPT-5.5 catalog supports only through `xhigh`.

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
