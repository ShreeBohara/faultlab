# Phase 31 — what FaultLab has shown

September 27, 2026. Event write-up for Shree and Aryan.
This completes the reporting asset in the [Phases 28–31 plan](EXPERIMENT_PROGRAM_PHASES_28-31.md).
It does not complete the original product acceptance checklist.

## The project in one paragraph

FaultLab tests AI agents before their mistakes reach a real customer. We built a small shop where
an agent must upgrade an order and send one truthful confirmation. FaultLab makes the shop
misbehave, records what the agent does, and checks the result with fixed rules. A second model
can propose a small recovery policy. We test that policy against the original agent and keep
the evidence, including failures.

For example, a request may succeed even though its reply is lost. Trying again carelessly could
create a duplicate action; giving up could leave the customer's task unfinished. The agent needs
to work out what actually happened.

## What runs today

The shop is a purpose-built test environment with real local HTTP requests and a fresh database
for each episode. It can lose a reply after committing a write, delay completion, return stale
information, or temporarily reject a request. Eight fixed checks judge the result. The Referee
is code, not another model deciding whether an answer sounds good.

The Actor performs the task. The Mechanic proposes recovery rules such as checking a receipt
or retrying the exact original request. These are bounded rules executed by an interpreter,
not arbitrary generated code and not model fine-tuning.

The implemented discovery workflow includes an Explorer, reproduction, diagnosis, repair,
challenge and promotion. The successful results below came from a **separate completion study**:
chosen source case → baseline controls → Mechanic proposal → source tests → development validation.
That study does not call the Explorer, run the original challenge/promotion sequence, or activate
a policy. We should show the path that actually ran.

This version tests one task in one shop. It does not automatically build a test environment for
any outside agent. A live smolagents baseline has been tested against the same shop; transfer of
an accepted learned repair to that agent is still unproven.

## How the work developed

| Stage | What we learned |
|---|---|
| Phase 16 | Separated completion improvement from the original acceptance gate. A completion study cannot write an `ACCEPTED` policy. |
| Phase 17 | The first development-qualified repair appeared on attempt nine. This first-success search does not estimate a general repair rate. |
| Phase 18 | That policy's separate unseen-case check returned **HARM**. A development success was not enough. |
| Phase 23 | Three of thirty studies qualified on notification-side development cases. |
| Phase 24 | The first routed Phase 23 policy returned **HARM** on its separate check: the Actor reported PENDING after observing UNKNOWN. The verdict remains recorded. |
| Phase 28 | Nine of forty-nine studies qualified on upgrade-side development cases, producing eight distinct policies. The run stopped at its declared spending guard. These policies were not evaluated on unseen cases. |
| Phases 29–30 | Phase 29 was cancelled. Phase 30 tested a reporting hint on saved turns; it recommended a later experiment. The hint was not adopted. |
| September 27 | We checked an existing repair on the corrected runtime, then separately generated a fresh repair and evaluated it on combinations reserved before generation. |

Sources: [Phase 16](PHASE16_RESULTS.md), [17](PHASE17_RESULTS.md), [18](PHASE18_RESULTS.md),
[23](PHASE23_RESULTS.md), [24](PHASE24_RESULTS.md), [28](PHASE28_RESULTS.md), and
[30](PHASE30_RESULTS.md). These were different experiments with different stopping rules.
Do not combine their study counts into one success rate. Earlier HARM results still stand;
they do not, by themselves, establish that a policy caused a failure.

## The latest result

The September 27 fresh-repair experiment ran ten development studies. The tenth produced the
first new policy meeting the unchanged strong development requirements.

| Measurement | Baseline | Selected repair |
|---|---:|---:|
| Completed tasks in development validation | 9 / 21 | **15 / 21** |
| Rule violations in that validation | 0 | 0 |
| Episodes executed in the reserved evaluation | 78 | 78 |
| Rule violations in the reserved evaluation | 1 | 0 |

The development result means **six more tasks completed in this measured comparison**.
Not every case was meant to complete: some deliberately required a safe unresolved outcome
or a correct rejection. The selected rule actually retried failed upgrade requests; the HTTP
journal and shop state confirmed those actions.

The reserved evaluation included three new fault combinations and three known guard cases.
All 156 episodes ran. But in one baseline episode the agent repeatedly checked a notification
it had never sent. The notification fault therefore never fired. The declared gate requires
complete exposure in every pair, so the formal result is **INCOMPLETE**. No trial was replaced.

The candidate had zero observed violations in those 78 episodes. This is useful evidence, but
it is **not a NO_HARM pass**, proof of general safety, or a reliable measured advantage on
unseen cases. The small differences between the arms do not establish such an advantage.
The partition is now spent.

The three decisions are:

- **Development:** qualified.
- **Reserved evaluation:** INCOMPLETE.
- **Active policy:** the empty baseline, `policy-v0`. No generated policy is `ACCEPTED`.

See the [full result](PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md) for all cases, failed attempts,
original answers, frozen identities and limitations. The earlier 42-episode compatibility
measurement also showed 15/21 versus 9/21, but tested an existing policy on known cases.
It is a separate result, not another newly learned repair.

## Evidence and sponsor use

**W&B Inference** served the actual model calls: DeepSeek-V3.1 for the Actor and
DeepSeek-V4-Pro-0813 for the Mechanic. **W&B Weave** recorded the executions; saved remote
readbacks were checked against local observations and original reports. The dashboard links
to those traces. Weave supplies evidence, not the fixed verdict or policy acceptance decision.

The fresh experiment retained 318 episodes across development and evaluation. Independent
checks reconstructed all 318 worlds, 2,544 rule checks and 318 saved Weave readbacks.
It used 1,783 model requests, with a conservatively carried charge of $37.68.
This is an upper-bound accounting figure, not a provider invoice.

**Aria remains deferred.** We have no verified automatic Aria analysis to demonstrate for this
experiment. The project was built for CoreWeave Hacks; the shop and dashboard ran locally.
Do not describe them as a deployed CoreWeave service.

Machine-readable sources are the saved `result.json`, attempt 10's completion-study record,
and `independent-accounting-audit.json`, linked in the [demo guide](PHASE31_DEMO_GUIDE.md).
They are local evidence, excluded from a normal source clone.

## What comes next

The report-hook failure found in a rejected development policy has now been corrected offline:
it closed business actions, then tried another business read before filing a report. That obscured
the actual cause behind a generic missing-report message. The original failures remain preserved.
The [fix and verification note](REPORT_FINALIZATION_FIX_2026-09-27.md) explains the narrow change.

The follow-up runtime correction is separate from the frozen live results above. Its offline
verification and new runtime identity belong in [current status](../../CURRENT_STATUS.md);
they do not constitute a fresh live result or retroactively repair old trials. The quoted live
measurements used runtime `3da193e3…`.

The [notification investigation](NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md) confirms repeated
polling of an operation the Actor never attempted. It does not establish the model's internal
reason. Earlier task-progress experiments had regressions, so adding more hints is not an
established solution. Any later experiment needs a declared treatment of agent-caused missed
faults and a fresh reserved partition.

The original promotion, transfer, sponsor/Aria and final-audit requirements remain open.
A second environment and general agent onboarding are future work. The event demo should
show the working test process, the measured development improvement, and the gate that refused
to turn incomplete evidence into a pass.
