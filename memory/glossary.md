# Quick glossary

| Term | Meaning |
|---|---|
| FaultLab / Gatekeeper | Product / team name. Builders: Shree Bohara and Aryan Bhusari. |
| Actor | Model performing the order task. |
| Explorer | Model proposing fault schedules and challenges. |
| Mechanic | Model proposing a bounded recovery policy. |
| Referee / C1–C8 | Fixed correctness checks against original report, delivered evidence and private truth. |
| F1 | Response lost/delayed after a write commits. |
| F2 | Accepted operation completes later, possibly with terminal failure. |
| F3 | Stale public read. |
| F4 | Transient service failure. |
| B0 / L | Empty/incumbent baseline / learned candidate comparison arm. |
| P1 | Changed-Actor-context arm of a context study. Same policy and tools as B0; only the per-turn context protocol differs. |
| `faultlab-compact-evidence/v1` | Default compressed evidence the Mechanic and Explorer read. Episode rows carry only `report_row` and `check_row`. |
| `faultlab-compact-evidence/v2-task-outcome` | Phase 8 variant used only by the completion study. Adds `task_outcome` per episode — the same adjudicated verdict already supplied in grouped `observed_outcomes`. Presentation, not disclosure. |
| Actor context protocol | Declared shape of the per-turn user message. `v1` is the preserved default; `v2`/`v3` add an attempted-write summary. Frozen in the configuration and stamped on every actor output. |
| REGRESSION | Context-study decision: the changed arm failed a check or lost a case's best safe outcome. |
| policy-v0 | Empty recovery policy, still active everywhere at handoff. |
| SAFE_UNRESOLVED | Honest unfinished task; not automatically a safety violation or a success. |
| NO_CHANGE | No improvement qualified within declared experiment bounds. |
| INCOMPLETE | Experiment stopped before its evidence requirements were met. |
| OBSERVED_IMPROVEMENT | Separate completion study's development result; never ordinary policy acceptance. None recorded yet. |
| ACCEPTED / promotion | Original repair gate passed and policy activation is authorized by fixed code. None recorded yet. |
| Weave verified | Remote trace was read back and matched to exact local evidence. |
| Conservative charge | Worst allowed request cost counted against authorization; different from known-token estimate and actual invoice. |
| Phase 3 B2 | The alternate-Mechanic configuration; stopped during Actor controls before requesting any repair. |
| Phase 4 | Two live Actor-context comparisons, 120 episodes. Both ended REGRESSION; nothing adopted. |
