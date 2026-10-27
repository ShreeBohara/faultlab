# FaultLab — current status

Updated **October 9, 2026 (Pacific)** (shared incident evidence milestone). This is the single current status and continuation page.
README, AGENTS, CLAUDE and memory entry points refer here. Historical reports describe
their own frozen experiments; their settings, budgets and next steps are not current instructions.

**Install and test:** [Setup](docs/setup.md#install-and-test-start-here) has the current commands,
timings and expected results for a fresh clone, and the port settings.

## Current product direction and build (October 9)

**Built: shared incident evidence for orders and a persisted synthetic payment task.**
FaultLab separates intended business actions, individual attempts, committed effects,
delivered observations and original reports. Each task keeps its own checks. New CLI
commands inspect data-only bundles, export selected offline orders episodes, and
explicitly replay installed candidates into fresh worlds.

The payment cases catch duplicate payments and falsely reused receipts. Corrected
candidates passed fresh replays of the same declared scenarios. Incomplete executions
retain known effects and failed checks; a native shutdown crash retained its original
report as WITHHELD. Start with [the guide](docs/incident-evidence.md),
[verification](docs/INCIDENT_EVIDENCE_2026-10-09.md) and
[design decision](docs/ADR_INCIDENT_EVIDENCE_2026-10-09.md).

**Verification:** the first frozen candidate's full backend suite finished with
**3,407 passed, 232 skipped and two warnings**, in 21 minutes 12 seconds.
After a small Unicode error-classification repair, all **248 incident tests** and
**26 CLI outcomes across 15 fresh worlds** passed on the final candidate. The full
backend suite was not repeated after that isolated repair; the verification record
keeps those source versions distinct. Frontend tests (373), build, 19 browser fixtures
and one real-backend browser check passed. Eight first-candidate reports were manually
reviewed; their rendering source is unchanged in the final candidate.

Runtime: `0beaf5a0f194870417a1796fe13f6c23be33ee772a63fa16a5176ddf401f325e`.
Orders algorithm, service, legacy contracts, scorer, interpreter, capabilities and
dependency identities are unchanged. Payment runtime identity has the bounded scope
documented in the guide. Existing native/local agent protocols and legacy bundle
inventories remain available. No check, threshold or gate was weakened.

This is offline synthetic engineering evidence. It does not establish production
payment behavior, customer adoption, generated repair, live-model reliability or an
ACCEPTED policy. Native user code remains trusted local code, not an OS sandbox.
Managed-provider calls and new managed-provider spend are zero; arbitrary native
user-code activity is unmetered. Carried conservative spend remains **$937.99**,
not a new billing query. Rule 2 remains deferred research.

**Next:** use an independently authored workflow to measure integration effort,
correction and repeat use; extend version compatibility as that workflow requires.
The narrow-screen report needs polish. F5/F6 customer validation remains open.
No workflow owner was contacted, and no hosted service or new framework adapter was added.

**Preservation:** main remains at `cbbf957`. Work is uncommitted and unpushed.
The release uses an explicit verified 22-path transfer, with backups and unchanged
Git index/history. See the transfer receipt in the verification record. The working
tree extends beyond backup `d022228`; that branch alone is not a current snapshot.

The following sections are dated earlier milestones. Their budgets, runtime hashes
and next-step statements do not override this section.

## Earlier milestone: native smolagents constructor (October 9)

**Built: test a user-owned smolagents constructor through its native execution loop.**
A developer supplies a trusted local `build_agent(model, tools)` file. FaultLab runs
fresh native trials, injects the existing rejected-upgrade fault, checks actual
business effects and the agent's report, and exports a regression that requires
explicit candidate selection. The earlier local `decide(request)` interface remains
available and unchanged.

Start with [the native-agent guide](docs/native-agent.md). The
[verification record](docs/NATIVE_AGENT_2026-10-09.md) and
[architecture decision](docs/ADR_NATIVE_AGENT_2026-10-09.md) record the design,
corrected findings, evidence and limits. One unchanged deterministic model double
proposes the unsafe action; the author's tool guard supplies the correction.
Separate-installation acceptance reproduced C3+C5 in 3/3 unsafe trials, passed 3/3
corrected trials, and completed one healthy upgrade and confirmation. A shutdown
crash retained the actual confirmation and withheld the provisional report; its
result stayed INCOMPLETE after 1 of 3 trials, with no retry.

**Release verification:** **3,177 backend tests passed**, with 234 existing skips
and 2 deprecation warnings, in 20 minutes 6 seconds. This includes all 36 native-agent tests.
Eight expected CLI/portable-test outcomes passed. Independent read-only SQLite
checks matched all eight new worlds; manual browser review matched all four reports.
Frontend tests (373), build, browser fixtures (19; one opt-in skip), and one real-backend
browser check passed. The application and test bytes match the frozen candidate.

Runtime: `274c0830b03338dc6a9dc4f4ed06f6306a5f1cc3327e986886c5fe35947bf3df`.
Runtime and algorithm identities changed with the new registered execution path.
The service, contract, scorer, interpreter, capability, dependency lock, earlier
rejection fixture and local callback worker remain unchanged. No gate was weakened.

This is native integration and authored-guard conformance under a deterministic
model double, not a production-model reliability result, generated repair or
ACCEPTED policy. Only the pinned framework and supplied task/tool contract are
supported. The worker executes trusted local code; it is not an operating-system
security sandbox. Managed provider calls and new provider spend are zero; arbitrary
user-code activity is unmetered. Rule 2 remains deferred research. Carried conservative
spend is still **$937.99**, not a new billing query.

**Next:** one independently authored workflow. Reproduce its owner's incident, verify
their correction, and measure integration effort and repeat use. Additional adapters,
a hosted system and generated repairs should follow that concrete evidence.

**Git and preservation:** main remains at `cbbf957`; this milestone is uncommitted and
unpushed. The original index and historical evidence are preserved. Development and
verification used isolated checkouts; only the explicit verified 25-path delta is
transferred to the original working tree. The working tree extends beyond backup
`d022228`; that branch alone is not a complete snapshot of current work.

The earlier milestone and experimental sections below describe their dated snapshots.
Their “next,” “newest build” and spending statements do not override this section.

## Earlier milestone: local Python decision agent (October 8)

**Built: test an explicitly selected local Python decision agent.** A developer can keep
`decide(request)` in a file outside FaultLab, run it through the existing orders tools and
checks, edit that file, and rerun the same portable scenario. Candidate source, execution
identity, observations, original reports, actual effects and incomplete attempts are saved.
The command and exported pytest both require the developer to select the agent explicitly.

Start with [the local-agent guide](docs/local-agent.md). The
[verification record](docs/LOCAL_AGENT_2026-10-08.md) and
[architecture decision](docs/ADR_LOCAL_AGENT_2026-10-08.md) describe the interface and limits.
The separate-checkout acceptance caught the unsafe candidate in 3/3 trials (C3+C5), passed
the corrected candidate in 3/3, and passed its healthy completion control. A shutdown crash
after both business actions correctly stayed INCOMPLETE; its provisional report was retained
as withheld. Independent read-only world checks matched all eight acceptance trials.

**Release verification:** **3,127 backend tests passed**, with 234 existing skips and two
deprecation warnings, in 20 minutes 15 seconds. This includes all 29 local-agent tests.
Eight expected separate-checkout acceptance outcomes and independent checks of all eight
saved worlds passed. Frontend tests (373), build, browser fixtures (19; one opt-in skip),
and a separate real-backend browser smoke (1) passed. The final application and test bytes
match the frozen candidate; the verification record distinguishes earlier attempts.

Runtime: `2d2a6ddb40b0f93b3c51daf122e57b1f7f623fa8edc5b76f0653da0e489ef0e6`.
The earlier offline fixture and all algorithm, service, contract, scorer, interpreter,
capability and dependency identities remain unchanged. No gate was weakened.

This is a trusted local decision adapter under FaultLab's Actor protocol, not unchanged
native-framework support or an operating-system security sandbox. Managed provider calls
are zero; arbitrary user-code activity and spend are unmetered. No generated repair,
live-model gain or ACCEPTED policy follows from this work. Rule 2 remains deferred research;
carried conservative spend is still **$937.99**, not a new billing query.

The next product decision is one independently authored workflow: reproduce an incident,
verify its owner's correction, and measure integration effort and repeat use. A bounded
local native-framework exercise is the fallback when no partner workflow is available.
The existing regression is the compatibility case; a broader hosted system remains later work.

**Git and preservation:** main remains at `cbbf957`; no commit or push is part of this work.
The existing index and historical evidence must remain unchanged. Development and verification
use isolated source copies; only the explicit verified delta may be copied into the original
working tree. The working tree already extends beyond backup `d022228`.

The earlier milestone and experimental sections below describe their dated snapshots.
Their “next,” “newest build” and spending statements do not override this section.

## Earlier milestone: portable regression completed (October 8)

The owner authorized implementation after the takeover audit and startup strategy review.
The immediate product priority is a portable, trustworthy regression workflow that another
engineer can run, followed by one external agent integration. The older handoff's request
for a paid Rule 2 probe is deferred research, not the next required product step. Its
preservation, evidence-integrity and protected-data boundaries still apply.

**Built: an offline rejected-upgrade regression.** It runs the real local simulator, Actor,
runner, fixed checks and regression compiler with explicitly scripted responses. Four unsafe
trials produce C3+C5 violations; three correct-rejection trials pass; a healthy control
completes the upgrade and confirmation. The exported bundle can run fresh behavioral checks
from a separate source checkout without credentials or historical stores.

Start with [the runnable guide](docs/offline-regression.md). The
[verification record](docs/OFFLINE_REGRESSION_2026-10-08.md) records results, scope and limits.
**Verification:** 3,098 backend tests passed (234 existing skips, 2 deprecation warnings),
373 frontend tests and the build passed, and 20 browser checks passed (1 opt-in browser
check skipped). The 17 new behavioral/CLI checks, fresh-install portable checks, and manual
report/database checks passed. The final source and fixture bytes match the tested candidate.

Runtime: `6174f241b59b236bf819d5e9855ecfc81a7f5e2321621c6c1cec1b25a22e4f79`.
The simulator service/contract, fixed scorer, policy interpreter and dependency lock retain
their previous identities. No gate was weakened. No provider call, billing change, commit or
push is part of this work; carried conservative spend remains **$937.99**, not a newly
queried billing balance. Live provider availability has not been rechecked.

This does **not** establish a generated repair, a live-model reliability gain or an ACCEPTED
policy. Rule 2 remains built but not offered. The next product milestone is connecting one
external agent to this same incident-to-regression path; broader scenarios and generated
repairs follow evidence from that integration.

**Git:** the original checkout remains on `main` at `cbbf957`; its existing index is preserved.
Development and validation used detached source copies of local backup `d022228`. This
milestone is uncommitted. Its files extend the working tree
beyond that backup branch; do not assume the working tree still matches the backup.
Historical artifacts and `/Users/shree/FaultLab_Runs/` are preserved.

The sections below retain the earlier handoff and experimental history. Their “newest build,”
“current total” and “next” statements describe their dated snapshots; this section is current.

## Earlier handoff (2026-10-08): [HANDOFF_2026-10-08.md](HANDOFF_2026-10-08.md)

Claude handed the project to another agent on 2026-10-08. The handoff page has the state, the open goal (first ACCEPTED
policy), next steps, hard rules and how live runs are done. **Provider status from the owner's billing screenshots
(2026-10-08):** CoreWeave Forge / W&B Academic plan free trial **ends 2026-10-12**; pay-as-you-go not active; inference
stops at the included $100/month allowance; October usage $0.00 / $100.00. The 402 below is consistent with the
September allowance being used up. Billing is the owner's job.

## Earlier blocker (2026-09-30 22:38 UTC): model provider refused calls

W&B Inference returned **HTTP 402 Payment Required** for every call from **2026-09-30 22:38:46 UTC**
(`artifacts/product-live-2026-09-30/diagnosis-probe2/answers.jsonl`). No paid run can succeed until the owner checks W&B
billing (credit or spending limit). Agents must not touch billing. Carried conservative total **$937.99**
(ledger `artifacts/product-live-2026-09-28/ledger.json`).

**Where the work stands (2026-09-30):** diagnosis rules committed (`7120def`, runtime `1abba8a6`): Rule 1
`faultlab-mechanic-diagnosis/v1-repair-and-record` is offered; Rule 2 `faultlab-diagnosis-guide/v1-kinds-and-checks`
is built but **not offered**. Probe 1 (`artifacts/product-live-2026-09-30/diagnosis-probe-decl/RESULT.md`): P1
UNINFORMATIVE (checker too narrow), P2 PASS, P3 strongly favours the guide (valid requests 40/40 vs 17/40); Rule 2 not
shipped under the declared rule. Probe 2 (`…/diagnosis-probe2-decl/RESULT.md`): INCOMPLETE (402), descriptively the
same. **Next once calls work again:** a fresh declared probe under P1b; if Rule 2 passes, offer it and run the next
history-replay Learn campaign on native v2.1 (store `native-v2b`).

## Historical live results (2026-09-28/29, Claude as PM)

Runtime `c9af0a47…` for the first four runs (local backup commit `9970718`+) and `08e4c20d…` for the v3 run.
**Newest build: `1abba8a6…`** (September 30, after the diagnosis analysis: the diagnosis repair-and-record rule
`faultlab-mechanic-diagnosis/v1-repair-and-record` in every new Learn plan, and the diagnosis guide
`faultlab-diagnosis-guide/v1-kinds-and-checks` built but **not offered**, plus the pre-registered probe harness,
**not run**; builder, two $0 reviews, fixer and verifier, then a $0 follow-up (the PM's F4 decision on the guide text and
pinned saved-store tests), all offline; **not yet committed, not run live**; the verified `c80d8632…` and the builder's
unreviewed `e3551ead…` are superseded; *Current work*, first paragraph). Before it, current code was **`49958e71…`** (September 30, after v2f: history fireability for Explorer picks,
`faultlab-explorer-selection/v3-history-fireability`, changed after review so that a pick is refused only when every one
of its faults is on a refused target, and evidence retry v3, 24 automatic retries per campaign; builder, two $0 reviews
and fixer, all offline; committed locally as `661e2d0` and **run live once, v2g**, row below; the rule change was signed off by Claude as PM (delegated) with its residual bias stated; *Current work*,
the paragraph after the newest build; the builder's unreviewed `07b8ccc4…` is superseded). Before it,
current code was **`95042e4d…`** (September 30, after v2e: native citation status in Mechanic and challenge Explorer
requests, `faultlab-mechanic-evidence/v2-native-citation-status`, native adapter v2 Learn plans only; builder, two $0
reviews and fixer, all offline; committed locally as `47b8f69` and **run live once, v2f**, row below; *Current work*,
the paragraph after the newest build; the header said "not yet committed, not run live" until this build corrected it).
Before that, current code was
**`f058c03c…`** (September 30, the Learn-loop limits after v2d: the Mechanic request-size rule, and the challenge-pick
rule withdrawn after review; committed locally as `884de24` and **run live once, v2e**, row below; *Current work*, the
paragraph after the newest build). Before that, current code was **`ee2d1df9…`** (September 30: discovery protocol v4, history replay; builder, two $0 reviews and
fixer, all offline; committed locally as `814a6e3` and **run live once, v2d**, row below; *Current work*, the paragraph after the newest build), built on `4553ebe7…` (lab-role
transport backoff and native adapter v2.1 labels, committed locally as `78878bb`; commit `4d1c21b` records its v2.1 live
runs; written up in `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md`), built on `ac7a12d2…` (native adapter v2 and its review fixes;
committed locally as `c9db705`). Nothing pushed. **Current carried conservative total: $923.53** (after v2g, $6.73; after v2f $916.80, $10.13; after v2e $906.67, $2.88; after v2d $903.79; before it, $898.58 (ledger
`artifacts/product-live-2026-09-28/ledger.json` as committed in `4d1c21b`: the native v2.1 runs added $4.72, $2.12
baseline study `c8063a11` + $2.60 Learn campaign `077b8434`)). The earlier figure $893.86 (after the native v2 run) is
superseded. Owner added funds 2026-09-28; the old $1,000 cap no longer binds.

| run | result | doc |
|---|---|---|
| Native smolagents baseline probe (18 native + 18 control episodes) | 8/18 violated, same as Phase 1; rejected upgrade → false confirmation (C3) 3/3 (6/6 over two days); delayed upgrade → no report 3/3 | `docs/PRODUCT_NATIVE_PROBE_2026-09-28.md` |
| Discovery v2 first run | INCOMPLETE 5/8 (Explorer connection error; no retry then) — led to the transport-retry fix | `docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-28.md` |
| Discovery v2 complete run (reference V3.1) | **8/8 slots fully fired vs v1 4/8** (p=0.038, not a concurrent control); 1 pick refused + re-planned; NO_CHANGE (no source) | `docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-29.md` |
| Original loop vs native agent | **First live reproduce → reduce → diagnose of real sources**: 2 C5 sources, each 3/3, both diagnosed INCONCLUSIVE → no candidate → NO_CHANGE. The repairable C3 failure was never exposed (Explorer never picked a rejected upgrade) | `docs/PRODUCT_NATIVE_LEARN_RUN_2026-09-29.md` |
| Native adapter v2, first live run (2026-09-29 23:36-23:44 UTC, runtime `ac7a12d2`) | Baseline probe: v2 clean on dev-1..dev-4 (12/12), dev-5 C3+C5 3/3, dev-6 C4+C5 2/3; 53 reports, 0 cited labels outside the labels shown. Learn campaign `b05ac280` (discovery v3-history): 3 C4 sources (F4 send failures); source 3 diagnosed: every citation was a label the agent had been shown, but after a broker-retried send the agent's labels had a gap (obs-1, obs-2, obs-4) and the report's cited rows did too (o1, o2, o4, …; o3 is the hidden first attempt); the Mechanic claimed a citation of an undelivered observation (CONTRACT_EVIDENCE_GAP) → INCONCLUSIVE; then Explorer selection 6 lost its connection twice ~130 ms apart → campaign **ERROR**. $6.47 conservative. Both led to the September 30 builder round below | `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md` |
| Native adapter v2.1 (2026-09-30 03:14-03:22 UTC, runtime `4553ebe7`) | Probe **NO_GO** under its declared rule (C5 3 of 15 outside dev-5); disclosed as a rule error: in 71 v2/v2.1 episodes every C5 was an untruthful report with C3/C4, 0 missing reports. Separately declared Learn `077b8434` (v3-history): **NO_CHANGE**, the Explorer never picked the reliable dev-5 failure | `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md` |
| **v2d: history replay** (2026-09-30 06:31-06:39 UTC, runtime `ee2d1df9`) | **Furthest a generated repair has got:** replay of dev-5 → source reproduced 3/3 → **first native source to survive reduction** → **POLICY_GAP** → candidate `policy-c65cc08e…` (block confirmation without an upgrade SUCCEEDED receipt; close business on a definite failure) **PASSED source validation** (baseline C3 3/3, candidate 0 violations) → challenge **0 failed checks in 9 pairs** but INCONCLUSIVE (a status-read fault the candidate makes unnecessary did not fire; *corrected September 30:* with a healthy upgrade neither arm needed that read, so it fired in 1 of 6 episodes) → next Mechanic request 33,223 > 32,000 tokens → **ERROR**. Integrity clean; both evidence waits cleared by the product's own automatic retry. $5.21 | `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md` |
| v2e (2026-09-30 10:11-10:15 UTC, runtime `f058c03c`, bounded Mechanic context) | dev-5 replay source reproduced 3/3 and reduced again → diagnosis **INCONCLUSIVE**: the Mechanic again claimed (falsely: 8 of 8 diagnosed episodes had every cited label shown and decoded) that the agent cited unshown labels, and this time requested no intervention → **NO_CHANGE**. The pre-registered misreading checker scored it NOT_CHECKED (its phrases miss "never shown"; PM error, disclosed); checker v2 (built after the run, **post-hoc**; the fixer's revision agrees) scores v2d and v2e MISREADING. $2.88; ledger **$906.67** | `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md` |
| **v2f** (2026-09-30 12:32-13:09 UTC, runtime `95042e4d`, citation status for the Mechanic) | dev-5 replay → **POLICY_GAP with a correct hypothesis** (no citation claim; checker v2 NOT_CHECKED) → **2 generated candidates each PASSED source validation and ran a full 4-schedule/12-pair challenge with 0 failed checks** → both INCONCLUSIVE because the Explorer's lone orders-status-read pick does not fire on a healthy upgrade (same pick ended v2d's challenge); 3rd candidate a repeat (NO_CHANGE); dev-6 replay C4 source 3/3; 10 evidence waits exhausted the retry caps → PM early stop (documented deviation, same STOPPED outcome) → **STOPPED**. Integrity clean. $10.13; ledger **$916.80** | `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md` |
| v2g (2026-09-30 16:22-16:30 UTC, runtime `49958e71`, history fireability + evidence retry v3) | dev-5 source reproduced and reduced → **diagnosis INCONCLUSIVE** (corrected: the Mechanic requested the intervention, but its 614-character hypothesis exceeded the 600 limit twice, so fixed code recorded INCONCLUSIVE by default); dev-6 C4 source reproduced and reduced (first C4 to survive) → POLICY_GAP → candidate SOURCE_FLAKY (incumbent 2/3, 1 candidate violation); the fireability rule refused nothing (the Explorer did not pick the refused target); 0 evidence waits → **NO_CHANGE**. Across v2d-v2g the dev-5 source reproduced and reduced 4/4 but the diagnosis gave POLICY_GAP only 2/4 (the Mechanic requested the intervention 3/4; one request was lost to the length limit): **the diagnosis step is now the binding step**. $6.73; ledger **$923.53** | `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md` |
| History-informed (v3) original loop vs native agent | **First live POLICY_GAP diagnosis, first live generated candidates, source validation and challenge.** 4 C5 sources (3/3 each); candidate 1 passed source validation, challenge found a counterexample → REJECTED; candidate 2 failed source validation. STOPPED at the 6 h limit during a Weave evidence wait (FaultLab gap: no automatic telemetry retry). Native agent's report-writing failures (hex evidence IDs, calls after final-report-required) are the binding limit | `docs/PRODUCT_NATIVE_LEARN_V3_RUN_2026-09-29.md` |

Carried total now **$898.58** ($893.86 after the native adapter v2 run, `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md`, plus $4.72 for the native v2.1 runs, evidence `artifacts/product-live-2026-09-30/native-v2b-run/` and `native-v2c-run/`). Still unproven live: promotion and ACCEPTED. The run's two FaultLab defects (no
automatic evidence retry; a stop during an evidence wait saved as UnexpectedError) are **fixed offline, not yet
run live** (*Current work*, first paragraph).
**Built after these runs ($0, not run live): discovery protocol v3 (history-informed)**, an opt-in answer to the
7ee35abe gap. Two $0 reviews found no leak and no gate change. All 9 of their findings are applied. It is
described under *Current work*.
Built and verified this session: bundle import → review → fresh rerun; discovery protocol v2 (reachability
pre-check); order-aware schedule identity; bounded transport retry (Explorer, Mechanic, native agent);
native report tick; dotenv credential guard; offline-test network silence.

## Current work

**Current priority: complete and improve a dependable product.** The owner clarified that they meant
“enhance,” not “announce.” The completed Phase 31 write-up/demo is a saved asset, not the end of the
project. Finishing Claude's experiment program did not establish full product acceptance.

**Newest build (September 30, after the diagnosis analysis; builder, two $0 reviews and fixer, all offline): diagnosis
repair-and-record (Rule 1), a diagnosis guide built but not offered (Rule 2), and the pre-registered request-only probe
harness; verified READY_WITH_NOTES, then a $0 follow-up. Not yet committed, not run live; the probe has not been run.**
Runtime `1abba8a6810b6bd6b47dd5887c6305052ca87d48660977fb6277a3ff81462b2f` (algorithm `0b34473c…`; the follow-up changed
only `diagnosis_guide.py` and one field of `run_plans.py` in `backend/app`), built on `49958e71`
(= `backup/part2-2026-09-22` at `626bae4`); superseded: the verified `c80d8632…` (algorithm `743a1520…`) and the
builder's unreviewed `e3551ead…` (algorithm `e4c47b4e…`). Design and PM decision:
[`artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md`](artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md);
what was built, tests, the fixer's changes and limits: [diagnosis rules note](docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md).
Evidence: `artifacts/product-diagnosis-rules-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`, `fixer/`,
`verify/`, `followup/`, `probe-inputs/`; current probe plan and declaration template in `followup/probe-plan/`; the
builder's `probe-plan/` and `fixer/probe-plan/` are superseded).
* **Why:** across v2d-v2g the dev-5 source reproduced and reduced 4/4 but the diagnosis gave POLICY_GAP 2/4. v2e
  declined on a citation theory; v2g requested the right intervention twice but its 614-character hypothesis failed the
  600-character limit both times, the repair message never named the limit, and INCONCLUSIVE was stored as a code default
  that no record distinguished from a model choice.
* **Rule 1, `faultlab-mechanic-diagnosis/v1-repair-and-record`** (plan field `mechanic_diagnosis`), frozen into **every
  new Learn plan, every agent**, and offered in run options:
  * a diagnosis request's one format-repair turn gives each `string_too_long` error `max_characters` and
    `your_characters` (v2g: 600 and 614) and appends one sentence to today's unchanged instruction (+47 tokens); the first
    turn, the model's text (never truncated), the 600 limit and candidate requests are unchanged;
  * after every diagnosis, before the POLICY_GAP gate, an immutable `diagnosis_requests/<diagnostic_id>` record:
    `VALID_REQUESTED` / `VALID_NO_REQUEST` / `INVALID_OUTPUT`, proposed_kind source `model` / `code_default`, every attempt
    by id with its errors, the options with their change strings, the requested id, whether the requested intervention ran
    **any fresh trial** (`intervention_ran`; fixer) and, if it ended before its three pairs, why (`early_end`, also in
    the record's sentence); the export of such a plan lists `diagnosis_requests` with every attempt embedded by id (v2f's
    attempt 0 included). The dashboard shows the rule in the Learn setup form and the saved plan (fixer), but not the
    record itself (follow-up; only the recording carries it).
    Replayed on the five saved diagnoses it says VALID_REQUESTED, VALID_NO_REQUEST, VALID_REQUESTED (attempt 0 rejected at
    743), INVALID_OUTPUT/code_default, VALID_REQUESTED.
* **Rule 2, `faultlab-diagnosis-guide/v1-kinds-and-checks`** (plan field `diagnosis_guide`): **built and tested, not
  offered** (`DIAGNOSIS_GUIDE_OFFERED = False` in `backend/app/lab/diagnosis_guide.py`; run options do not list it and no
  new plan freezes it). The block gives the task text, the C1-C8 public meanings verbatim (hash frozen), the kind
  definitions, the runtime-contract note, how the output is used and the length limit (+608 tokens); per the PM decisions
  the draft's interpretive C6 sentence is dropped and its two neutral `checks_note` sentences are kept word for word
  (review finding F4, follow-up); Rule 2 declaration `def60594…`. A plan that declares it is validated exactly and Start
  refuses it if its frozen text or C1-C8 hash differs from the installed one. Flip the constant only after the probe's P1
  and P2 pass.
* **Probe harness** `scripts/experiments/diagnosis_probe.py` (RECOMMENDATION.md section 7): dry run by default; 100
  first-turn calls (CONTROL/GUIDE, K=10, interleaved) + 40 repair calls = 140; maximum charge 140 × $0.04984 = $6.9776
  (cap $8), tighter bound $2.90; every call admitted and charged through `RuntimeProvider` and a `CampaignLedger` before it
  is sent; `--execute-live` refuses without a declaration whose sha256 is given, and (fixer) the declaration must carry the
  harness's exact scoring rules, the frozen temperature, how repeated answers will be read, and a clock-drift check.
  **Read before declaring it (PM decisions, doc section 5):** the frozen temperature is 0 and the declaration cannot change
  it, so K=10 repeats may be identical (scoring now reports distinct answers per request key). The `checks_note` scope
  (review finding F4) is decided: the two neutral sentences are back, GUIDE is +608 tokens. Plan hash `91ca47e4…`
  (`followup/probe-plan/`; tighter bound $2.9065, maximum $6.9776), harness `b1eb7cda…` (unchanged); after a run, add its
  charge to the carried total by hand (its ledger is its own).
* **Unchanged:** `referee/` (checks.py not opened), `lab/diagnosis.py`, `prompts/diagnosis.md`, `contracts/models.py`,
  `citation_status.py`, the `learning.py` gate line, reproduction/reduction/assess_pairs/source validation/challenge/
  promotion, the reference Actor prompt; service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer
  `19de811c…`, native v2.1 prompt `fff397c9…`; every saved plan (6/6 native-v2b plans byte for byte; 6/6 recordings
  byte-identical under the old and new exports.py). `gate_freeze.py`: only `mechanic.py` (the declared change) and the
  source fingerprints changed. The reference Actor source hash changed (`7f78de28…` → `eaffac74…`; `mechanic.py` is in the
  agents tree), so **register every agent again before a live run**.
* **Checks ($0):** 83 new tests from the builder, 97 backend and 5 frontend after the fixer (T1-T9 of the memo, the loop's
  wrapper order, Rule 1 through two evidence waits with the real Diagnostician and Mechanic, the probe harness with a
  scripted provider, cap enforcement and refusal without a declaration); two existing test harnesses whose Diagnostician
  is a stage double switch Rule 1 off (the record needs a real Mechanic call). The builder's one `scripts/test.sh` run
  **exited 1**: backend 2 failed, 3,119 passed, 180 skipped (`builder/full-test-sh.log`). The two failures are
  `test_history_fireability` saved-store tests that pin the store's history before v2g was saved (30 → 36 verified
  episodes); that file was unchanged from `626bae4`. The fixer's and the verifier's runs had the same 2 failures
  (`fixer/full-test-sh.log`, `verify/full-test-sh.log`); the follow-up pinned those tests (below).
* **Reviews and fixer ($0):** no HIGH finding. Fixed with failing-then-passing tests: `intervention_ran` now means a fresh
  trial ran (it was true for an experiment that preflight rejected or a Stop ended before any trial); P1 counts GUIDE
  hypotheses a person flags but the checker misses against the GUIDE bar, and the review file hides the checker's output;
  scoring reports repeats; the declaration carries P4's "worse", the full decision rule, the temperature and a clock-drift
  check; `served_model` renamed `model_id`; the dashboard shows Rule 1 and no longer calls a code-default kind the model's;
  a record refusal names its diagnosis. 17 of 17 reverted fixes are caught by a test (`fixer/mutation-checks.log`).
  Deferred: showing the `diagnosis_requests` record in the dashboard.
* **Follow-up ($0, `followup/`):** the PM's F4 decision applied (guide block, plan validator, dashboard validator, T3/T9,
  probe test, doc; new probe plan `91ca47e4…`). The saved-store tests now read the native-v2b store at fixed, recorded
  snapshots, so later live runs cannot change their expected numbers: the three `test_history_fireability` tests at record
  cutoff 6748 (where live run v2g's own plan froze its history; the rebuilt plan equals v2g's frozen history, replay list
  and table, and the old numbers 30 / 3,7 / 8 / 8 hold), the diagnosis-rules T1 test at the store's reviewed end (row 8583,
  its six plans), and the v2d request rebuild (used by two tests) at 3022 (the store as v2d left it). Controls: on a copy
  grown by a synthetic later run the pinned tests pass and the unpinned versions fail; 11 of 11 product mutations are
  caught. The follow-up's one `scripts/test.sh` run **exited 0** (`followup/full-test-sh.log`): backend 3,135 passed,
  180 skipped; frontend 373 passed; build and browser (19 passed, 1 skipped) passed; no non-loopback connection. Runtime
  `1abba8a6…`; Rule 2 still not offered.
* **Next:** with owner/PM approval and a declaration, the probe (decide the temperature question first); Rule 1 ships
  unless P4 shows the new message is worse; Rule 2 only if P1 and P2 pass. Register every agent again before any live
  run.

**Build before this one (September 30, after live run v2f; builder, two $0 reviews and fixer, all offline): history
fireability for Explorer picks, and evidence retry v3. Committed locally as `661e2d0`; run live once (v2g).** Runtime
`49958e716f0b08aacb9db5d6ddf99620451f949a901aa35cca979918c1df6b6e` (algorithm `7a56afed…`), built on `95042e4d`
(= `backup/part2-2026-09-22` at `432e54b`); the builder's unreviewed `07b8ccc4…` is superseded. Design, measurements,
limits, the review findings and the fixer's table: [history fireability note](docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md)
(sections 5 and 8). Evidence: `artifacts/product-fireability-2026-09-30/` (`builder/`, `review-integrity/`,
`review-product/`, `fixer/`).
* **Why:** in v2d and v2f every candidate that passed source validation ran a challenge with 0 failed checks and still
  ended INCONCLUSIVE, because the challenge Explorer picked a lone F4 fault on the orders status read, which seldom
  fires with a healthy upgrade. Discovery picks in v2c, v2e and v2f spent slots on it too. v2f also used up the 6
  automatic evidence retries per campaign in 10 waits.
* **Rule 1, `faultlab-explorer-selection/v3-history-fireability`** (plan field `explorer_selection`), frozen into **new
  Learn plans with discovery v3-history or v4-history-replay only**:
  * **The table.** When the plan is saved, FaultLab counts, per fault kind, service and tool, how many verified episodes
    scheduled a fault there and in how many every such fault fired. It reads exactly the plan's frozen same-agent
    history episodes: one shared eligibility generator, and the ids must hash to the history's `episode_ids_hash`. It is
    frozen with its hash and recomputed before Start and before the first Explorer request. A target with at least 3
    verified episodes and a fired share below 1/2 is REFUSED.
  * **The rule (changed by the fixer).** A discovery or challenge pick is refused before any episode only when **every
    one** of its faults is on a REFUSED target. A pick with a fault on any other target runs, even beside a REFUSED
    target. The refusal is recorded with its table rows, and the Explorer gets one re-plan inside the existing Explorer
    requests: the challenge's 8, or discovery's declared 8. Under v3-history a re-plan can leave the last discovery slot
    without a request, and that is recorded. **The builder's version refused a pick if any fault was on a REFUSED
    target; both reviews showed that this also refused a status-read failure during a pending upgrade, which fires, and
    that in native-v2b the refused status read is the very step every generated guardrail adds (integrity MEDIUM-1,
    product F1). The fixer's form departs from the task's wording ("any of its primitives"), so the owner should confirm
    it before commit.**
  * **What the Explorer sees.** Each request states the rule, carries the table and says that the rule takes precedence
    over "every valid pick runs" in its instructions (system prompts unchanged).
  * **What it never reads.** Candidate, challenge, reproduction or other later-stage episodes, other agents or protected
    data. The table is the same for every candidate, unlike the withdrawn candidate-reach rule.
* **Rule 2, `faultlab-evidence-retry/v3`**, in every new Learn plan: the same per-wait rule (3 retries at 30, 120 and
  300 s) and a cap of 24 per campaign. v2 plans keep 6; Start accepts exactly v2 and v3. The saved plan now names the rule
  id beside its cap.
* **On a scratch copy of the saved native-v2b store:**
  * **The table.** A new v4 plan's table marks F4 on `get_operation_status` (orders) **0 of 4** verified history
    episodes: REFUSED. The episodes are 2 discovery picks each from v2c and v2e, all `target_not_reached`. Every other
    target fired in all its verified episodes; F4 on `get_order` has 1 episode and is allowed. A new v3-history plan has
    the same rows (its cutoff and hash differ).
  * **The task's numbers.** Over every stored episode, the target fired in 2 of 14 policy-v0 episodes and 1 of 9
    candidate episodes. The rule reads none of these except the 4 history episodes.
  * **Saved picks.** 3 of 11 challenge picks and 7 of 15 discovery picks are refused, all of them lone status-read
    picks; the rest are allowed. The fixer's rule gives the same counts, because no saved pick mixes the status read
    with another target.
* **Limits (stated plainly after review):**
  * the rule is the same for every candidate but **not neutral**: repairs add calls where the starting policy seldom
    reached, which is where rows are REFUSED; a lone pick on a REFUSED target never runs, so a mistake only that pick
    could show is tested only if the Explorer pairs the target with another fault;
  * a PASSED_OBSERVED challenge has tested the guardrail's status step failing only if one of its picks faulted the
    orders status read; the challenge panel lists the refused targets and every checked pick;
  * a REFUSED row changes only through mixed discovery picks that run and enter a later history, or through a plan
    without the rule;
  * v3's cap of 24 re-admits the "flaky six-episode batch" scenario that v2's cap of 6 was added for (18 retries before
    it settles).
* **Other review fixes:** the saved plan and setup preview no longer say "no re-plans" under the rule (F2); the dashboard's
  experiments poll reads only the campaign's own selection, challenge and slot records, and validates a plan only when it
  names the rule (F3; Phase 18/19 showed heavy polling can freeze the lab loop); no "Refused: Refused", the REFUSED row
  is highlighted (F4); doc wording corrected (F5); four new tests close the reviewers' test gaps (LOW-2).
* **Unchanged:**
  * gates, the referee, the simulator, C1-C8, `challenge.py`, `evaluation.py`, `promotion.py`, `diagnosis.py`,
    `explorer.py` (since the builder) and the reference Actor prompt;
  * service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…` and scorer `19de811c…`;
  * both native adapters and prompt v2.1 `fff397c9…`;
  * discovery v1, v2 and v3-history-reachability plans (pinned v1/v2 Explorer message digests still match), and every
    saved plan (native-v2b's five plans still read byte for byte).
  `gate_freeze.py` shows 20/20 files and 30/30 functions identical. The reference Actor **source** hash changed with the
  builder (`fb5e1894…` → `7f78de28…`, a tree hash over `backend/app/agents`, which holds `explorer.py`) and is unchanged
  by the fixer, so **register every agent again before a live run**.
* **Checks ($0):**
  * builder: 22 fireability tests (3 on the saved-store copy), 5 evidence-retry v3 tests, 6 frontend tests;
  * fixer: 11 new backend tests and 6 new frontend tests; before the fix, 7 of the first 10 backend tests and all 6
    frontend tests failed on the builder's code; 18 of 18 negative-control mutations caught in a scratch tree;
  * the integrity review's own counterexample demo, rerun on the fixed code: COUNTEREXAMPLE_FOUND with the rule, as
    without it;
  * the one final `scripts/test.sh` is `fixer/full-test-sh.log`, and its counts are in the fixer report.
* **Next:** (rule change signed off by the PM, delegated; committed locally) register every agent again, then a declared
  live Learn run (native adapter v2, v4 history replay, `native-v2b` store) with a descriptive read-out: did the
  challenge Explorer re-plan away from the status read, did a challenge reach 4 complete schedules, how many automatic
  evidence retries were used, the refused targets and every refused pick with its recipe, and whether any challenge
  schedule faulted the orders status read (if none did, a pass must not be described as testing the guardrail's status
  step).

**Build before this one (September 30, after live run v2e; builder, two $0 reviews and fixer, all offline): native
citation status in Mechanic requests. Committed locally as `47b8f69`; run live once (v2f).** Runtime
`95042e4d9a67c739387a3841152bd7c23448f89cd5271ca32806552d6f3fc36c` (algorithm `4e5a8f90…`), built on `f058c03c`
(= `backup/part2-2026-09-22` at `d38c0b8`); the builder's unreviewed `c4195af1…` is superseded. Design, measurements,
the review findings and the fixer's table: [citation-status note](docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md)
(sections 8 and 9). Evidence: `artifacts/product-mechanic-citations-2026-09-30/` (`builder/`, `review-integrity/`,
`review-product/`, `fixer/`).
* **Why:** in v2d and v2e the diagnosis Mechanic twice claimed the agent cited labels it was never shown. It was false
  both times: all 8 diagnosed episodes had every cited label shown and decoded. The Mechanic could not see the
  adapter's per-report citation record.
* **What:** `faultlab-mechanic-evidence/v2-native-citation-status` (plan field `mechanic_evidence`) is frozen into
  **every new Learn plan of native adapter v2 only**. Each Mechanic diagnosis or candidate request, and each challenge
  Explorer request, that carries episode evidence gets a separate `native_citation_status` block:
  * one plain sentence saying what the block means;
  * one row per episode: tokens cited, how many decoded to delivered evidence, and any undecoded tokens.

  The rows are read only from the `report_submitted` event, never from scoring. The v2 memory text in Mechanic requests
  gets one sentence pointing to the block. The block is added before the request-size rule counts the request, and it
  is never compacted.
* **Unchanged:** discovery Explorer requests. Every other plan (older v2 plans, the reference Actor, native v1, baseline
  and compare) is byte for byte the same (differential check against the backup `learning.py`). So are the gates,
  `diagnosis.py`, `mechanic.py`, `explorer.py` and `challenge.py`, both native adapters and their prompts (v2.1
  `fff397c9…`), simulator `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…` and scorer `19de811c…`.
  `gate_freeze.py` (builder and fixer): 30/30 functions and 20/20 files are identical; only the runtime, algorithm and
  lab-tree fingerprints changed. The reference Actor source hash (`fb5e1894…`) is unchanged, but the runtime changed,
  so **register every agent again before a live run**.
* **Measured on scratch copies of the saved v2b store** (fixer's wording):
  * v2e's diagnosis request is 9,088 → 9,434 tokens, and its block shows 4 episodes with 0 undecoded;
  * v2d's refused candidate request is 33,223 → 34,806 tokens and still fits at compaction stage 3 (22,684 ≤ 28,000),
    with all 34 rows kept. The block counts toward that target and is never omitted from it.
* **Misreading checker v2** (`scripts/experiments/check_evidence_gap_misreading_v2.py`, sha256 `11920882…` after the
  fixer; v1 untouched). It scores v2d and v2e **MISREADING, POST-HOC**; the pre-registered read-out stays NOT_CHECKED.
  The fixer made it safe to use after this build: bare "undecoded" and "not decoded" (the block's own words) no longer
  count, a denied claim ("no label was never shown") does not count, every match is listed with its sentence for a
  **required human check**, and every output states `read_out_status` (POST_HOC or PRE_REGISTERED) and the script's
  sha256.
* **Reviews and fixer:** both reviews reproduced the builder's claims and found no product defect. 7 findings (1 MEDIUM,
  on checker v2, found by both; 6 LOW, one found by both). Fixed: the checker (MEDIUM-1), its output labels (LOW-1),
  the block's null clause, which was narrower than the code (LOW-4, declaration `163c1a4c…` → `b84f55db…`), and three
  doc findings. Deferred: a product record that a Mechanic request carried the block, the size rule's recorded wording
  (frozen), and a paid paired probe. Table: note section 9.
* **Checks ($0):**
  * builder: 17 backend tests, 4 checker tests, 3 frontend tests, 17/17 mutations caught, real API responses pass the
    dashboard validators; its final `scripts/test.sh` (`builder/full-test-sh.log`): backend **2,970 passed, 180
    skipped, 0 failed** (2 known warnings), frontend **356**, build passed, browser **19 passed, 1 opt-in skip**;
  * fixer: 1 new backend test and 29 new checker test cases, each written first and failing on the builder's code
    (`fixer/tests-before-fix.log`: 27 failed); 11/11 new mutations caught (`fixer/mutation-checks.log`); a targeted
    backend run after the fixes, 185 passed; the reviewers' probe wordings re-run, 0 of 20 counted.

  The one final `scripts/test.sh`, after the fixer's last edit, is `fixer/full-test-sh.log`; its counts are that log's
  last lines and are in the fixer's report.
* **Next:** commit (owner's OK), register every agent again, then a declared live Learn run (v2 agent, v4 history
  replay, `native-v2b` store). Its read-out must be **descriptive only** (did the diagnosis claim unshown citations; did
  it request the declared intervention), because there is no concurrent control without the block. Declared steps
  (note section 8): rebuild each diagnosis and candidate request offline to confirm the block and its rows (provider
  tokens = rebuilt local count − 136); run the frozen checker v2 with `--read-out pre-registered` and confirm each
  counted sentence by hand. For a causal answer, first a small paid paired probe with and without the block (owner's
  decision).

**Build before this one (September 30, after live run v2d; builder, two $0 reviews and fixer, all offline): the
Learn-loop limits. Committed locally as `884de24`; run live once (v2e).** Runtime `f058c03c53b6442cd1c3d308d46007af8b755af0478595d57b964261aa17677a` (algorithm `a08a8d61…`), built on
`ee2d1df9` (= `backup/part2-2026-09-22` at `3b31b58`); the builder's unreviewed `4d0d7914…` is superseded. Design,
measurements and the PM decision: [loop-limits note](docs/PRODUCT_LOOP_LIMITS_2026-09-30.md). Evidence:
`artifacts/product-loop-limits-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`, `fixer/`).
* **`faultlab-mechanic-context/v2-bounded`** (the v2d ERROR) is frozen into **every new Learn plan**. The refused
  33,223-token request was rebuilt exactly from a read-only store copy (three times, independently). Its size came from
  per-episode evidence rows: 12,047 tokens for the 18 clean challenge episodes, 11,030 for the development evidence.
  A Mechanic candidate or diagnosis request over 32,000 tokens is now compacted in 3 fixed stages to at most 28,000
  tokens (4,000 are kept for its one format-repair turn):
  - only clean episodes' rows are omitted (no failed check, no VIOLATION outcome, not the source or a reproduction),
    and each is still named with its own outcome;
  - a kept example stands only for episodes of the same recipe, arm, policy, purpose and outcome, and the request says
    their own rows can differ from it;
  - the request states what was omitted.
  If it still does not fit, nothing is sent and that source's search ends with a recorded reason; the campaign
  continues or ends NO_CHANGE (its reason then names the search that ended early), never ERROR on this path.
  v2d's request would now go out at **21,101 tokens (stage 3**, 24 clean episodes named, not repeated; every failing
  episode kept). The builder's wording fitted at stage 2 by 10 tokens; the clearer wording the reviews asked for adds 66.
* **`faultlab-challenge-selection/v2-candidate-reach`** (for the v2d INCONCLUSIVE) is **withdrawn before any live run**.
  Both reviews found it can hide a counterexample: it refused picks by what the candidate's own agent did in source
  validation, so for v2d's candidate it refused 3 of 5 tool/service pairs that the agent did call in the same
  challenge. An offline replay with the unchanged `challenge.py` turned COUNTEREXAMPLE_FOUND into PASSED_OBSERVED. No
  new plan declares it, run options do not offer it, and a plan that does cannot be created or started. The code is
  kept, unused, for the PM. **Corrected cause of v2d's INCONCLUSIVE:** pick 3 was one failed orders-status read with a
  healthy upgrade, so neither arm needed that read (it fired in 1 of 3 incumbent episodes, 0 of 3 candidate episodes);
  it was not "made unnecessary by the candidate". The existing reachability labeller cannot give a candidate-independent
  check for it either (its IMPOSSIBLE rules pass pick 3; its FORCED model covers only the reference Actor under
  policy-v0). **PM decision:** keep rule 2 dropped (fixer's recommendation), or ask for a new candidate-independent design.
* Unchanged: gates, referee, simulator `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…`,
  `challenge.py`, `mechanic.py`, `diagnosis.py`, `promotion.py`, `evaluation.py`, the reference Actor prompt, native
  adapters v1 (`6f303264…`, `external_agent.py` byte-identical) and v2.1 (`dfd41b33…`), and the discovery protocols.
  The reference Actor source hash changes (a tree hash over `backend/app/agents`, which holds `explorer.py`).
  **Register every agent again before a live run.**
* Checks ($0): builder (21/21 mutations; `scripts/test.sh` all passed), two reviews (10 findings: 2 HIGH, both on rule 2;
  2 MEDIUM, docs; 6 LOW), fixer: every finding verified; each fix has a test that failed before it and passes after,
  and 17/17 new negative-control mutations are caught (`fixer/mutation-checks.log`); the dashboard's validators accept
  the real API responses (`fixer/api-contract-check.log`); `gate_freeze.py` 30/30 functions and 20/20 files identical.
  `scripts/test.sh` before the last doc edit (`fixer/pass1-full-test-sh.log`): backend **2,949 passed, 180 skipped,
  0 failed** (2 known warnings; 9 more than the builder's 2,940), frontend **353**, build passed, browser **19 passed,
  1 opt-in skip**. The final run after the last edit is `fixer/full-test-sh.log`; its result is in the fixer report.
* Next: the PM's decision on rule 2 (recommended: keep it dropped), commit (owner's OK), register every agent again,
  then a declared live Learn run.

**Runtime before this build: `ee2d1df914bd54c766eaec200715ad976f7d905964e1077adbb14ce46cc928e9`** (algorithm `ab296a32…`):
**discovery protocol v4 (history replay, regression-first discovery): builder, two $0 reviews (integrity, product) and
fixer, all $0 and offline; since committed locally as `814a6e3` and run live once (v2d).** Chain: `4553ebe7` (= `backup/part2-2026-09-22` at
`4d1c21b`) → `2a181539` (builder, algorithm `f66ae8bb…`) → **`ee2d1df9`** (fixer: the reviews' findings). Design,
rules, caveats, checks and the findings table: [discovery v4 note](docs/DISCOVERY_V4_HISTORY_REPLAY_2026-09-30.md)
(section 14). Evidence: `artifacts/product-discovery-v4-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`,
`fixer/`).
* **Why:** the one reliable, repairable native failure (dev-5 rejected upgrade → confirmation anyway, C3; 6/6 on v2,
  9/9 on v1) was never picked by the Explorer in three v3 Learn campaigns; the binding limit is which recipe discovery
  picks.
* **What:** opt-in `faultlab-discovery/v4-history-replay` = v3-history (same frozen history, checks and budget,
  8/8/8/8) plus a replay list frozen into the plan: history rows with ≥2 verified episodes, every fault fired in every
  one, violation share ≥ 2/3, ordered by share, then verified count, then row order, at most 3, never a no-fault row.
  Replays run first (one slot and one Actor episode each, no Explorer request) and become sources by the unchanged rule;
  the Explorer then takes the remaining slots as under v3, with the replays in its search ledger (duplicate rule
  applies) and one appended prompt section. An empty list says so; the run is then v3-history except the protocol id.
  Every replay is labelled "history replay" with its row (selection record, fault-search and source panels, recording,
  exports); the saved plan shows the frozen list; the chooser explains it in one sentence. v1 stays the default; v1,
  v2, v3 and v3-with-pre-check are unchanged.
* **What v4 would replay (read-only, saved stores):** in the v2.1 store `2026-09-30/native-v2b`, dev-5 first (3/3, C3),
  then dev-6 (2/3, C4, the flaky failure).
* **Review fixes (fixer, $0):** replay episodes **never enter a later agent history** (they were counted as a learn
  campaign's Explorer picks and fed the replay rule; now skipped and not counted, like single-case baseline runs; every
  saved store's history is byte-identical before and after, 14 histories in 11 stores opened read-only); the chooser
  sentence and the saved plan now say that **a replay source can use up the campaign's 4 candidate requests and end
  discovery before any Explorer slot** (unchanged loop rule; the product review's offline run did exactly that); the
  fault-search panel no longer claims Explorer slots that did not run; a v4 recording's history claim rule names v4
  (v3 recordings keep their exact text); a no-case replay row no longer reads "(Explorer pick)"; the Run summary shows
  "Found by …" for a v4 incident. **Deferred:** W&B regression dataset rows and Weave traces still do not say "history
  replay"; cite the recording's `discovery_history_replays` block or the source panel's **Found by** line for any v4
  result. Fixer checks: 5 new backend tests, 3 new frontend tests, 14/14 negative-control mutations caught
  (`fixer/mutation-checks.log`); `gate_freeze.py`: 30/30 gate functions and 20/20 gate files identical, only the
  runtime, algorithm and lab-tree fingerprints changed; one `scripts/test.sh` after the fixer's last edit, result in
  `fixer/full-test-sh.log` and the fixer report.
* **Checks (builder):** 23 new backend tests, 6 frontend unit tests, 1 browser test; 21/21 negative-control mutations
  caught; a manual offline run through the product API (replays first with 0 model calls, then 6 Explorer requests; a
  changed history refused with 409; the real Reproducer code reproduced the replay source 3/3 **on scripted native
  replies: fixture behaviour, not model evidence**); real API responses pass the dashboard validators (this caught and
  fixed one validator bug). Repo `gate_freeze.py`: only the runtime, algorithm,
  source and lab-tree fingerprints changed. One `scripts/test.sh` after the last code edit (`builder/full-test-sh.log`):
  backend **2,905 passed, 180 skipped, 0 failed** (2 known warnings; 23 more than `4553ebe7`'s 2,882), frontend **345** unit
  tests (6 new), build passed (size advisory only), browser **18 passed, 1 opt-in skip** (1 new); no code or test file
  changed during the run (sha256 compared).
* Unchanged: simulator `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…`, capability
  `8e8e04af…`, reference Actor prompt `12eabe7f…`, native v1 adapter `6f303264…` and prompt `22515428…` (`external_agent.py`
  byte-identical), native v2.1 adapter `dfd41b33…` and prompt `fff397c9…`. **Register every agent again before a live run**
  (the runtime changed); agent histories are unaffected (the fixer's history change touches only replay episodes, which
  no saved store holds).
* Next: commit (owner's OK), register again under `ee2d1df9…`, then a declared live v4 Learn run in the `native-v2b`
  store (frozen list: dev-5 3/3, then dev-6 2/3; summary `d45adfdeef3c…` today). Name the store, the history's
  composition and the frozen summary hash with any result.

**Runtime before this build: `4553ebe7db2f9e3efda6f8761e987c6f1ea58dce12d3fde2dfbc8812ebb7c057`** (algorithm
`b2575eb2…`): the September 30 round (builder, two $0 reviews, fixer; next paragraph), committed locally as `78878bb`
on `backup/part2-2026-09-22`; built on `ac7a12d2`. Chain: `ac7a12d2` → `18292424` (September 30 builder, never committed) → **`4553ebe7`**
(September 30 fixer: the reviews' findings). Simulator service `3ce5bcd2…`, contract `6f9d7783…`, interpreter
`6da0714a…`, scorer `19de811c…` and capability `8e8e04af…` are unchanged; `external_agent.py` (native v1) is
byte-identical and v1's prompt hash (`22515428…`) is unchanged. **v1's adapter hash changed** `fa7a58db…` → `6f303264…`:
`registry.py`, part of it, now records v2.1's label rule in a v2 registration (review finding P-2); v1's history identity
does not use the adapter hash, so v1's history is unaffected. **Register every agent again before a live run** (the
runtime changed, as after every build). **Native adapter v2 must be registered again and is a new identity:** its adapter
protocol (part of its prompt hash) changed, prompt hash `cee3aeda…` → `fff397c9…`, adapter hash `d27c374f…` →
`dfd41b33…`; a v3 agent history for v2 does not include the first v2 build's episodes, and the two builds' results must
not be pooled. The reference Actor's source hash (a tree hash of `backend/app/agents`, which now holds the retry code)
changed `99a9034f…` → `142a9ebc…`; its prompt, context and response protocols, and so its history identity and
model-visible behaviour, are unchanged.

**September 30 (builder, two reviewers, fixer; $0, offline; not run live, not committed): two fixes from the first live
v2 run.** Evidence: `artifacts/product-native-v2b-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`,
`fixer/`).
* **Lab-role transport retry with backoff** (rule `faultlab-transport-retry/v2-lab-backoff`, frozen into every new
  Learn plan). Campaign `b05ac280` ended ERROR because rule v1's single retry of a lost Explorer request went out
  ~130 ms later, into the same outage. Now the Explorer (discovery and challenge selections) and the Mechanic
  (diagnosis and candidate requests) of a Learn campaign re-send a request that got no answer (connection error,
  timeout, HTTP 503) up to **3 times after waits of 5 s, 20 s and 60 s**, at most **12 times per campaign** (during
  discovery also within the plan's declared Explorer retry bound). Each retry is charged on the ledger before it is
  sent and recorded (`transport_retries`: attempt, wait, campaign retry number); a returned answer is never re-rolled.
  **Stop during a wait** ends the campaign STOPPED with a plain reason within about half a second. If every retry
  fails, the campaign ends ERROR as before and the message says how many retries were tried. The agent roles
  (reference Actor, native v1 and v2) keep rule v1 (one retry). Plans saved before, baseline/compare plans, and
  separate studies (selection comparison, completion study) keep rule v1; Start accepts a saved plan only with
  exactly rule v1 or (Learn) exactly rule v2. Shown in the saved plan, the discovery budget and the Learn setup form;
  a **discovery** selection's retries are shown on it in the fault-search panel, while challenge-selection and
  Mechanic retries appear only in the campaign recording and the budget counts, and nothing shows a wait while it
  happens (the campaign stays SELECTING or DIAGNOSING). Review fixes: a retry the unreserved budget cannot cover is
  refused **before** its wait (a read-only budget check; the charge after the wait stays the only admission); a
  request that got no retry says "no transport retry was sent: <reason>" instead of "after 0 transport retries"; under
  discovery v2 the dashboard states the real discovery bound (12, the campaign cap, not the declared 16). A store with a
  new Learn plan needs this runtime or a later one: an older checkout (`ac7a12d2` or earlier) reports such a plan as
  "missing, corrupt or inconsistent" (read from that code, not run). Details: [transport retry note, section 12](docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md#12-rule-v2-faultlabs-own-lab-roles-back-off-september-30-0-not-yet-run-live).
* **Native adapter v2.1: contiguous labels over what the agent is shown** (adapter protocol
  `faultlab-native-adapter/v2.1-shown-order-labels`). Labels now count observations in the order v2 first shows them
  (`obs-1..obs-n`, no gaps); an observation the agent never sees (a broker-retried first write attempt, a
  non-blocking policy read) gets no label; decoding maps only labels already shown. `report_submitted` now lists
  `cited_tokens_not_decoded` instead of `cited_unshown_labels`. A new v2 registration records this rule in its
  limitations (review fix; the builder's text still said "journal label"). The Mechanic and Explorer never see a
  label the adapter decoded; they see each report's decoded IDs as the episode's `oN` row aliases. A token the adapter
  did **not** decode (a guess such as `obs-4`) reaches them as written. That view is unchanged for the same citations
  (the hidden first attempt is still a recorded row, so a report citing only what the agent saw still skips it, e.g.
  o1, o2, o4). What changed for them is only the v2 contract text: it now says unseen observations exist and get no
  label, and that `oN` counts every recorded observation, so it can differ from the agent's `obs-N` (v1 and reference
  views unchanged). Details: [external agent setup](docs/external-agent-setup.md#native-adapter-v2-first-build-run-live-september-29-2026-v21-labels-not-yet-run-live).
* **Not fixed: the September 29 misdiagnosis (review findings P-1, LOW-1; deferred to the PM).** The live
  INCONCLUSIVE came from the diagnosis **Mechanic** misreading reports (all 53 v2 reports cited only labels the agent
  had been shown; the Mechanic claimed "o6" was undelivered, which was false on the rows it was given). v2.1 changes
  what the agent sees, **not** what the Mechanic reads: its evidence view is byte-for-byte the same (only the
  `V2_MEMORY` contract text is new), so this round does not address that failure, and whether a Mechanic now reads
  such reports correctly is unmeasured. Options for the PM: (a) measure it in the next declared live run with the
  pre-registrable check `artifacts/product-native-v2b-2026-09-30/fixer/check_evidence_gap_misreading.py` (reads a
  campaign export only; on the September 29 export it returns MISREADING for the one diagnosis, and its negative
  controls pass: `fixer/misreading-check-selftest.log`); or (b) for smolagents-v2 plans only, add a per-episode list
  of rows the agent was not shown under a new, declared compact-evidence format ID (needs a gate-freeze exception,
  because `summarize_evidence` is frozen).
* **Checks run by the builder (one `scripts/test.sh` after its last code edit, `builder/full-test-sh.log`):** backend
  **2,867 passed, 180 skipped, 0 failed** (43 more than `ac7a12d2`'s 2,824); frontend **338** unit tests (4 new);
  build passed; browser **17 passed, 1 opt-in skip**. Negative controls (`builder/mutation-checks.log`): all 10
  mutations caught. Repo `gate_freeze.py`: referee, promotion, evaluation, actor, actor prompt and progress files and
  `assess_pairs` unchanged.
* **Reviews ($0):** integrity PASS WITH NOTES (5 LOW findings; `review-integrity/`), product review (2 MEDIUM, 4 LOW;
  `review-product/`). **Fixer:** the findings' fixes each have a check that fails on the unfixed code and passes after
  (`fixer/mutation-checks.log`); P-1/LOW-1 deferred as above; P-3's optional live "waiting to re-send" note not built
  (the docs now say what is and is not shown). Suites after the fixer's last edit: one `scripts/test.sh` run,
  `fixer/full-test-sh.log` (the counts are in the fixer's report).
  Next: commit (owner's OK), register every agent again, then a declared live run that exercises rule v2 and the v2.1
  labels, with the misreading check pre-registered.

**Previous runtime: `ac7a12d2c1fc3baf4c680719afaa9b6287971e5a9211064c80f27c06a3382090`** (algorithm
`7afabd51…`): native adapter v2 and its review fixes, committed locally as `c9db705` on `backup/part2-2026-09-22` (next paragraph); independent verification READY_WITH_NOTES (`artifacts/product-native-v2-2026-09-29/verify/REPORT.md`): backend 2,824 passed / 180 skipped / 0 failed, frontend 334, build passed, browser 17 + 1 opt-in skip. The runtime before it,
`5583dcad…` (algorithm `5c95f2a9…`), is committed locally as `94b130e` on backup branch `backup/part2-2026-09-22` (previous checkpoint
`af5a3fb`, runtime `08e4c20d…`); simulator service **`3ce5bcd2…`**, contract **`6f9d7783…`** and interpreter hash `6da0714a…`
unchanged, so checkpoint bundles stay rerunnable. **Every agent must be registered again under `ac7a12d2`
before a live run, native v1 included:** adding v2 changed `registry.py`, which is part of v1's adapter hash
(`61497db3…` → `fa7a58db…`), so a v1 registration made before v2 is refused. v1's prompt hash and request bytes are
unchanged. An idle campaign saved under an older runtime cannot be started (create a new one); it stays readable. Chain: `cfe5ac07` → `bb87c764` → `9f53eb8c` (discovery v2) → `c9b1b7e6` → `c0a8aad7`
(simulator revert, committed as `e7340c9`) → `debc86f3` (transport retry, below) → `c9af0a47` (its review
fixes, below) → `a8a32234` (discovery v3, below) → `08e4c20d` (discovery v3 review fixes; the checkpoint) →
`c4157e33` (builder A: automatic evidence retry, truthful stop during a wait) → `4016cff9` (builder B: ports,
launcher, CLI, test runner, CI, docs) → `5583dcad` (fixer: both reviews' findings) → `7968b622` (native
adapter v2, builder) → **`ac7a12d2`** (native adapter v2 review fixes; committed) → `18292424` (September 30
builder) → `4553ebe7` (September 30 fixer; current, not committed).

**September 29 (builder, two reviewers, fixer; $0, not run live): native adapter v2 for smolagents.** A second
declared adapter, `smolagents-toolcalling-v2` (agent kind `smolagents-v2`), for the same unmodified smolagents
1.26.0 agent. It adds only the reference Actor's two report fixes: short evidence labels (`obs-1`, `obs-2`, ...,
decoded back to the real IDs before the report is checked) and a strict final-report turn (only `final_answer`,
structured output). v1 is unchanged and stays the default; v1 and v2 are separate agents whose results are never
pooled. Review fixes: a label is decoded only if the agent had been shown it (the journal can hold a policy step's
read or a broker-retried attempt the agent never sees; a guessed label for one now fails C6, as it would under v1);
the final turn's size check counts its schema before the turn is charged; the docs and the Start refusal now say
to register again. How to use it: [external agent setup](docs/external-agent-setup.md#native-adapter-v2-first-build-run-live-september-29-2026-v21-labels-not-yet-run-live).
Evidence: `artifacts/product-native-v2-2026-09-29/` (`builder/`, `review-integrity/`, `review-product/`, `fixer/`).

**September 29 (builders A and B, two reviewers, fixer; $0, not run live): a more dependable product.**
Evidence: `artifacts/product-dependability-2026-09-29/` (`builder-a/`, `builder-b/`, `review-builder-a/`,
`reviewer-b/`, `fixer/`).
* **Automatic evidence retry** (rule `faultlab-evidence-retry/v2`, frozen into every new Learn plan). While a
  Learn campaign waits for verified Weave evidence, FaultLab retries it by itself: at most **3 times per wait**
  (30 s, 120 s, 300 s) and at most **6 times per campaign**. Each retry only re-sends saved trace records and
  reads them back: no episode, business call or model request is repeated, and nothing is charged. When a
  limit is reached the Run desk shows **Needs operator**; its button retries only that wait's episodes,
  blocked episode first, and a retry job skips episodes already verified. Plans saved before the rule keep
  manual retry only. A v1-rule plan (per-wait limit only, never run live) still reads, and Start refuses it.
* **Stops and limits are recorded truthfully.** A stop during a wait ends STOPPED with a plain reason; the
  qualification is INCOMPLETE with an interruption record, not an error. A stop during episodes keeps the
  Stop's own reason. A budget limit inside a qualification is recorded as `BUDGET_EXHAUSTED`, not an error.
  After a Stop no automatic retry starts, and one already running ends at its next step.
* **Clean install and local use:** the 33 tests that need two git-ignored files skip in a clone, naming the
  file. `test.sh` runs every stage, prints PASSED/FAILED per stage, and Ctrl+C stops it at once (exit 130).
  `FAULTLAB_SIMULATOR_PORT`, `FAULTLAB_BACKEND_PORT` and `FAULTLAB_DASHBOARD_PORT` choose the ports; unset
  means 8001/8000/5173 as before. The command-line tools print which backend they use and name the address
  if none answers. CI is split into two jobs; it has not run on GitHub (no push without the owner's OK).
  README and setup docs no longer contain owner paths, the W&B entity or local-only IDs.
* **Reviews:** 9 evidence findings and 7 install findings, all applied. Two parts were not done: blanking
  the team's project name in `.env.example` (the reviewer asked for a separate, reviewed change) and running
  CI (needs a push). Each fix has a test that fails on the old code (`fixer/mutation-checks.log`).
* **Suites under `5583dcad`, after the last edit:** backend **2,756 passed, 180 skipped, 0 failed**; frontend **329** unit
  tests; build passed; browser **17 passed, 1 opt-in skip** (17 new backend tests and 1 new frontend test;
  `fixer/full-test-sh-run*.log`).

**September 29 (builder, then fixer, $0): discovery protocol v3 (history-informed), opt-in; v1 stays the default.**
Design and results: [discovery v3 note](docs/DISCOVERY_V3_HISTORY_2026-09-29.md); section 12 covers the review fixes.
Evidence: `artifacts/product-discovery-v3-2026-09-29/builder/`, `…/review-integrity/`, `…/reviewer-product/` and
`…/fixer/`.
* **Why:** in 7ee35abe the Explorer never picked a rejected upgrade, although the same native agent failed C3 on
  `dev-5` in 6 of 6 saved baseline episodes.
* **What v3 adds:** one read-only Explorer input, `agent_history`. It summarises the same agent's earlier verified
  development outcomes in the same store, per recipe: verified episodes, outcomes and failed checks.
* **Frozen at plan time.** The plan stores the summary, its hash, the store's record cutoff and the agent identity.
  At creation, at first Start and before the first Explorer request, FaultLab recomputes the history at that
  cutoff; any difference refuses the run. Later records, the campaign's own included, never enter it.
* **Same agent** = adapter entry point + model + scorer + prompt, plus (since the review) the simulator contract
  and service, the capability set, the model request settings and the per-episode limits:
  * native agent: native prompt and source hashes;
  * reference Actor: prompt, context protocol and response protocol.

  Not the configuration hash, the FaultLab runtime or the adapter code, so re-registering keeps the history. Each
  history row lists the runtime and adapter builds its episodes ran under. Only the plan's starting policy counts.
* **What is used:**
  * development-split, discovery-purpose, non-B1 episodes from exactly two product paths:
    * `baseline_study`: B0 slots of a baseline study (fixed six cases × 3 trials);
    * `learn_discovery`: a learn campaign's own discovery picks;
  * **never** a baseline campaign's own single-case run, because its case is the operator's choice. A review
    showed three dev-5-only runs could otherwise curate the history;
  * only COMPLETED, non-lab-error, Weave-verified episodes. Lab errors, interrupted, unfinished and unverified
    episodes are excluded and counted.
  
  Promotion, held-out and final-audit records are never read into it. A seeded test proves this, and a mutant
  without the filters fails that test.
* **Two protocol ids:**
  * `faultlab-discovery/v3-history`: exactly v1 plus the history, for the reference and native agents;
  * `…/v3-history-reachability`: exactly v2 plus the history, reference only.

  Budgets and the transport-retry rule are those of the base protocol. With no prior history the plan says so
  plainly. Slot dispatch, budget and schedule identity are then exactly the base protocol's. But the Explorer is
  still sent the v3 prompt section and an empty history, so such a run is **not** a v1/v2 run and must not be
  pooled with one.

  The dashboard shows the history, its hash, the cutoff, its composition and each row's builds in the saved plan.
  Failed checks are shown with their names, and a **Check against the store now** button asks on demand whether
  Start would accept the plan. The recording carries all of it.
* **History-informed results are marked:** every v3 selection record has `matches_history_row` (the history row
  the pick re-tries, or null). The search-attempts panel, the source panel and the recording
  (`discovery_history_matches`) show it. Any v3 result must say "history-informed" and name the store, the
  composition and the summary hash. A matching source is never "independent discovery".
* **A changed history** is refused at Start (409, plain message). Caught before the first Explorer request, it
  ends the campaign as `AGENT_HISTORY_CHANGED` with that message, no longer a generic `EXECUTION_ERROR`.
* **v1/v2 unchanged:** Explorer messages in 4 scripted scenarios are byte-identical to before the change (pinned).
* **Suites under `08e4c20d`, after the last code edit:**
  * backend **2,683 passed, 180 skips, 0 failed** (10 new tests);
  * frontend **320** unit tests passed (3 new);
  * build passed;
  * browser **16 passed, 1 opt-in skip**.

  The builder's run under `a8a32234` had 2,673 / 317 / 16. The reviewers' two finding probes now fail, as
  intended; their three safety probes and the protected-data mutation check still behave as before.
* **Manual checks ($0, final code):**
  * scratch store, real product API, scripted native transport:
    * three single-case dev-5 baseline runs, started through Start, gave a v3 plan with **NO_PRIOR_HISTORY**;
    * after the product's baseline study, a v3 plan froze **18** B0 episodes over 6 cases (dev-5 3, not 6), from
      1 study and 1 build;
    * a changed record made the on-demand check say CHANGED, and Start was refused with 409; 0 selections;
  * read only, on the saved stores (all 8 unchanged, 0 saved v3 plans):
    * v3 would show `dev-5` C3 3/3 from `native-probe`;
    * it would show **no** rejected-upgrade row from `native-learn`, because that store had no study;
    * both registrations are still the same agent under the stricter rule.
* **Format:** the frozen history is now `faultlab-agent-history/v2`. Only scratch evidence stores held v1 plans.
* **Next for a live try:**
  1. Register again under the current runtime (`ac7a12d2` at the time of writing).
  2. Run the baseline study in the **new store** first, then create the v3 learn plan there.
  3. Review the frozen history (composition, builds) and press *Check against the store now*.
  4. Declare the run, and report its result as history-informed.

**September 29 (builder, $0): one bounded transport retry for every model role, and fixes.** Details:
[transport retry note](docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md); evidence `artifacts/product-retry-2026-09-29/builder/`.
Two independent $0 reviews (accounting READY, correctness READY_WITH_CHANGES) found no accounting bug and six small
items; **all six are handled** (runtime `debc86f3` → `c9af0a47`; evidence `…/fixer/`, note section 11):
- **Cost and token figures after a retry (documented; one convention now in code):** per record, tokens are the
  answered request's only and the cost is unknown (`cost_dollars: null`) for a retried selection or Mechanic output
  and for an Actor or native episode after any lost request (the Actor now matches the native bridge). For the
  campaign, every attempt is charged its full call, token and dollar bound, but after the first retry the budget
  shows usage as not fully known (`usage_metadata_known: false`, `actual_cost_dollars: null`) for the rest of that
  campaign. Conservative and honest; not an accounting error. Live runs already had null costs (the provider reports none).
- **Mechanic retry labels:** `mechanic_diagnosis` / `mechanic_proposal` / `mechanic_completion` (was `mechanic_mechanic`).
- **Retry bounds are discovery-only:** the 8/16 Explorer retry bound and the 160-request / $4.27 worst case cover
  **discovery**; later Explorer (challenge, selection comparison) and all Mechanic retries have no separate count and
  are bounded by one retry per request and the campaign caps. The dashboard now says "during discovery" plus one line.
- **Task display, digits:** a U+FE0E/U+FE0F after a digit, `#` or `*` is now marked unless it is inside a keycap
  (1️⃣); plain only after a pictograph (❤️). The builder's rule had left one hidden bit per digit.
- **Native drift companion** lists why each native tick-0 row stays drift. **Imports list re-check:** no change
  (measured 0.32 s for 100 items; not polled), as the reviewer advised.
- **FaultLab bug fixed:** campaign `a301846e` ended ERROR after one Explorer `APIConnectionError`. The Explorer,
  the Mechanic and the native smolagents transport now follow the Actor's exact rule (one shared module): one
  blind retry of the identical request, only when no answer arrived (connection error, timeout, HTTP 503 after
  1 s; never after any answer, never other statuses/auth/config/model mismatch), charged on the ledger before it is
  sent from unreserved capacity (refused → the original failure stands), recorded, and a second failure ends the
  campaign as before. Native: the retry sits inside `_Bridge.generate`, so smolagents sees one step and the same
  messages; it is charged as a model call, never an actor turn (≤ 8 generations + ≤ 8 retries per episode).
- **Discovery budget decision:** a retry is **not** one of v2's 16 Explorer requests; it is declared separately as
  `explorer_transport_retries_max` (8 v1 / 16 v2, **discovery requests only**) and every new plan freezes the rule as
  `transport_retry` (dashboard plan text shows both). v2 **discovery-phase** worst case is now 160 requests / about
  $4.27 (was 144 / $3.47); later-phase retries are bounded per request and by the campaign caps.
- **Native report tick fixed** (real tick), so new native stores pass `check_clock_drift.py` as is. For old native
  stores use `scripts/experiments/check_clock_drift_native.py` (same scan, plus the declared rule: tick 0 + equal
  attempt counts + integrity VALID). `check_clock_drift.py` stays byte-identical because closed runners pin its
  sha256 (editing it failed 78 pin tests). On a read-only copy of the native-probe store: drifted 0, 13 cleared.
- **Verification LOW issues 2–5 fixed:** presentation selector unmarked only after a pictograph or inside a keycap
  (review fix; the builder's "emoji base" rule still let digits through); Run desk
  "Recorded task" and history "Saved task" use `TaskText`; the imports list agrees with the detail view on
  `runnable`; a capability directory raises `ConfigurationError` and closes its descriptor. Issue 1 (caller gate
  counts B1 controls) is still open.
- **Manual $0 check:** the full offline original loop under a v2 plan, with lost Explorer, Mechanic (connection and
  503) and Actor requests, reached the same COMPLETED result and accepted-policy content as a clean run, with exactly
  4 retries recorded and 4 extra requests charged.
- **Found, not fixed (LOW, pre-existing):** selection records keep `input_tokens: null` when a provider returns no
  usage; the dashboard's Usage contract rejects null and the fault-search panel then refuses the whole list.
- **Next:** register the agents again under `c9af0a47`, then a new, separately declared 8-slot v2 campaign
  (never merged with `a301846e`'s partial 5 of 8).

**PM decision (September 28): the simulator identity change is reverted.** Compatibility of previously
exported bundles and existing registrations matters more than a control-capability file created at import
time, so `backend/app/simulator/main.py` is back to its `8e497da` bytes (it builds the server app when
imported, as before). Nothing else changed in that step. Consequences:
1. Bundles exported under the checkpoint simulator (contract `6f9d7783…`) can be **rerun again** (checked in
   the real dashboard at $0: reviewed as eligible, target compatible, confirmed fresh rerun COMPLETED,
   3 of 3 valid trials). A bundle made by the reverted build (contract `1099eda7…`; the only known one is
   the test fixture `exported-regression-other-simulator.zip`, sha256 `f2ac6a60…`) stays reviewable and is
   refused for rerun, naming both identities and "an earlier or different simulator build".
2. Every agent must still be **registered again** before any live run: a registration records the
   whole-backend `runtime_hash`, which differs from every earlier registration's (discovery v2 and the
   review fixes changed `backend/app`), even though its simulator and contract part matches again.
3. The planned paid import validation uses the **restored** fixture `frontend/tests/fixtures/exported-regression.zip`,
   sha256 `14e53310cde9a3f6f985eb6bc4ac9fa0393a2155effd518953f39699a4ecb6df` (its `8e497da` bytes, contract
   `6f9d7783…`). The old `exported-regression-earlier-simulator.zip` was byte-identical to it and was moved
   to `artifacts/product-discovery-2026-09-28/fixer3-0928/moved/`, with the lazy `main.py` and its test.
4. Accepted trade-off: outside tests, importing `app.simulator.main` reads settings (from `.env`) and
   creates or reuses `artifacts/control-capability` (0600), exactly as at the checkpoint. The test suite
   imports it once with an empty scratch settings file and a scratch artifact directory (root
   `backend/tests/conftest.py`), so tests still never read `.env`; `tests/simulator/test_entry_point.py` pins
   the simulator identity to the checkpoint values and checks the entry point's capability and authorization.

Verification of `c0a8aad7` is recorded under *Verification and known issues*.

**Independent verification of `c0a8aad7` (September 28, verifier4; $0, no provider/model/W&B call; evidence
`artifacts/product-discovery-2026-09-28/verifier4-0928/`, git-ignored).** Nothing was taken from earlier reports.
- **Identities** (the app's own functions): runtime `c0a8aad7…`, algorithm `e5dce72c…`; simulator service
  `3ce5bcd2…` and contract `6f9d7783…` equal `8e497da` (`simulator/` and `contracts/` byte-identical; the
  checkpoint tree recomputes to `cfe5ac07…`). `gate_freeze.py`: `checks.py` hash and `assess_pairs` text/AST
  unchanged against `8e497da` and the Phase 28 record (`783e8e58…`).
- **Suites, one clean run each:** backend **2,562 passed, 180 skipped, 0 failed**, 2 known warnings, 929.09 s;
  frontend **303 unit tests** (17 files), build (size advisory), **15 browser tests passed, 1 opt-in skipped**.
  **0 outside connections or lookups**: audit hooks in every Python and Node process refused and logged none, and
  a process-tree socket sampler saw none. The only real-`.env` events were the 3 synthetic ones in `test_env_guard.py`.
- **A bundle exported before today reruns:** `native-offline-incident-bundle-96f072.zip` (exported September 27,
  contract `6f9d7783…`, the same bytes as the restored fixture), through the real backend API and a real simulator
  on 127.0.0.1, a scratch data folder and the tests' scripted provider-free agent: reviewed as runnable, fresh rerun
  **COMPLETED, 3 of 3 valid trials**, incident reproduced (C3), not provider-backed, $0. The other-simulator bundle is
  refused (409, both identities named). A September 20 bundle (contract `6265eadc…`) is refused at upload.
- **Every review finding re-tried and holds.** The six re-send picks the review named are now NOT_FORCED (N3). Caller
  gate PASS (3,337 episodes, 124 points, lowest 83.3%); it fails both controls (caller v1: 20 of 134; no 3-check cap: 3).
  Back-test re-derived: IMPOSSIBLE fired **0 of 6**; the 58 FORCED misses are 47 skipped calls + 11 early ends, 0
  reached-but-not-fired (3,402 episodes; the lost script's 3,447 / FORCED-fired 3,370 differ only in that cell).
  New adversarial sweep: **1,540 rule-IMPOSSIBLE faults, 1,500 recipes, 29,620 runs, 0 fired** (raw attempts, adapter
  calls, control-plane waits; other faults fired in 19,913 of 27,680 runs). Task display: all 4,174 default-ignorable
  and 58,390 other non-visible code points are marked; 2,000 random mixes hide nothing. The dotenv guard makes 0 `.env`
  opens (also with `PYTHON_DOTENV_DISABLED=0`). Capability files with mode 0644/0640/0604, symlinks or FIFOs are refused.
- **v1 unchanged by default:** checkpoint and current code, fed the 8 saved c701e850 Explorer outputs through the real
  loop, send byte-identical Explorer messages (8 of 8) and store identical selection records. 115 real plans saved on
  September 27, before the `discovery` field existed, still verify and read as v1.
- **Historical data unchanged:** the 31 result documents and all other tracked files not in the commit list match
  `8e497da`. All 8,863 `.sqlite3` and `-wal` files keep their hashes, sizes and mtimes. Only the 3 known `-shm` timestamps
  moved, because older tests open those stores `mode=ro`. HEAD and index are unchanged.
- **New LOW FaultLab issues, not fixed:**
  1. The caller gate also counts 30 handwritten B1 control episodes (`source_mode` offline_fixture) as the real Actor.
     Without them it still passes. Fix: filter `source_mode == 'live'` in `load_rows`, before Run A.
  2. One U+FE0E/U+FE0F after every visible character stays unmarked, following the review's rule. That leaves a
     1-bit-per-letter hidden channel that raises no warning; only the character count shows it.
  3. `RunControls` "Recorded task" and `CampaignHistory` "Saved task" show a task raw. For an import, that is the
     bundle's task.
  4. The imports list still says `runnable: true` for an other-simulator bundle. Its detail view and execution refuse it.
  5. A capability path that is a directory fails with a raw `IsADirectoryError`.
- **For the PM commit:** 43 changed and 27 new files versus `8e497da`, none removed. The exact list with sha256 is in
  `verifier4-0928/COMMIT_LIST_vs_8e497da.txt`.

**Implemented offline, not yet committed or run live: discovery protocol v2 (reachability pre-check).**
A Learn plan can now explicitly declare `faultlab-discovery/v2-reachability` (default stays v1, today's
exact behaviour). Before a paid Actor episode, a free in-process replay labels each fault FORCED /
NOT_FORCED / IMPOSSIBLE for the reference Actor's real action space; only all-FORCED picks run, a refused
pick gets one re-plan, and the declared budget is 8 slots / 16 Explorer requests / 8 episodes. Native
agents cannot declare v2. The order-sensitive schedule-identity bug is fixed for new campaigns only.
Read-only back-test on 3,447 stored episodes: 0 of 6 stored IMPOSSIBLE faults fired (the wider evidence
is a 35,976-run adversarial sweep with 0 fired); all 58 unfired FORCED faults were the Actor skipping a
call or an episode ending early; that FORCED-miss rate (1.5% for V3.1) covers attempt-1 faults only.
**Review fix (FaultLab modelling bug):** the first caller model assumed the Actor re-sends a write after
UNKNOWN; stored DeepSeek-V3.1 almost never does, so re-send-dependent faults were wrongly FORCED. Caller v2
never re-sends and makes at most 3 status checks after a write failed on both attempts; a new $0 gate
(`scripts/experiments/check_reachability_caller.py`) checks every modelled attempt against 3,337 stored
episodes and passes (124 points, lowest 83%); the old model fails it. **Corrected Run A bound:** discovery
at most **144 requests / about $3.47** (the earlier 80 / $2.14 left out the charged Actor transport retry);
campaign worst case about $56 by the plan's phase table, $200 cap. Runtimes `9f53eb8c…`, `c9b1b7e6…`, now
`c0a8aad7…` (the simulator revert; no discovery code changed); $0. The gate was re-run under `c0a8aad7`: PASS.
See [the discovery v2 note](docs/DISCOVERY_V2_2026-09-28.md), which also lists the completion-gap families
a wait/retry policy could recover but policy-v0 cannot.

**Implemented and reviewed, not yet committed: dashboard bundle import, review and a separate fresh
rerun.** The whole feature is now in this main folder (the product worktree copies are stale). A saved
regression ZIP is checked and stored as data with no provider calls; the review shows the source trials,
how they were produced, and the exact task and order the rerun will send; a fresh rerun is a separate,
confirmed, bounded action whose accounting campaign refuses all other work. Three independent $0 reviews
(September 28) found real gaps — the task sent to the agent was not shown, the accounting campaign admitted
paid studies, malformed bundle fields could break the imports list, and the backend accepted any Host
header — and every finding was fixed with tests; see *Review fixes* in the
[import review](docs/PRODUCT_IMPORT_REVIEW_2026-09-27.md).
*Historical:* the import increment was verified under runtime `cfe5ac07c6ef571f7be5f57cc8f56cbce4084496c3d157d3b222c0e9bb0f6738` (full backend 2,363 passed, 180 skips; frontend 254 unit tests, build and 13 browser fixtures). Those counts and that runtime are **not current**; see *Current runtime* above. Provider calls 0, cost $0; main HEAD/index unchanged; no push.
A second $0 review (September 28) found that the task display let variation selectors, U+034F and other
invisible combining characters through unmarked, and that hidden characters on collapsed blank lines
vanished; fixed in the dashboard (every default-ignorable character is marked except one emoji
presentation selector after a visible character; collapsed lines count every hidden character; the warning
and escaped copy appear whenever any are present). It also found tests that read the real `.env` through
the simulator's `create_app`; they now pass explicit settings and the test process refuses any open of it.
Smaller hardening from the same review: an existing control-capability file readable by group/others, owned
by another user, or not a regular file is now refused; importing the backend sets `PYTHON_DOTENV_DISABLED=1`
by default (an explicit operator value is kept); a static test fails if any module imports smolagents outside
the adapter's dotenv guard; a bundle from an earlier or different simulator build is marked not runnable at bundle level.
**Next:** the PM commits, then the owner declares the bounded real-model validation (worst case 72
requests across the two targets, or cap each execution at 24; see the review doc) **under the current
runtime, after registering the targets again and using the restored fixture above**. Original historical
stores remain untouched. See [current increment memory](memory/context/product-import-2026-09-27.md).
Of the five LOW issues from the independent verification (above), issues 2–5 were fixed on September 29 (runtime
`debc86f3`; the task-display rule was tightened for digits in `c9af0a47`); issue 1 (caller-gate scope) is still open.

**Reviewed campaign setup and native-agent execution are implemented, verified and saved locally.**
The dashboard now offers reference/native selection, explicit registration, six public cases, an immutable
saved plan and a separate Start action. Every original learning phase uses the selected agent. Native
provider-identity/accounting failures are classified as lab errors; native audit freezing and a guard
against calling same-implementation reruns independent portability are implemented. Public recordings
include unsuccessful runs and the plan. Current campaign state also keeps history labels up to date.

Onboarding runtime: `d1845765fa1c120ad4afd936461ddb4e4d909972209b160d6eebd63d6b3c64fb`.
**Full backend: 2,224 passed, 180 existing skips, zero failures**, two warnings, 791.81 seconds.
**Frontend: 219 tests, production build and ten browser fixtures passed**; one opt-in actual-backend check
was skipped. Actual UI checks ran all six public cases, verified a real recording download, and preserved
138 records / 64 events / six policy pointers across restart. Independent manual audit passed 160 checks;
153 scripted-native worlds passed 2,324 independent comparisons. A further final-source dashboard run,
CLI audit freeze and archive check passed; all old database hashes/mtimes stayed unchanged. These
checks establish execution and evidence integrity, not new live learning or generated-policy acceptance.
[Onboarding review](docs/PRODUCT_ONBOARDING_REVIEW_2026-09-27.md) and
[implementation memory](memory/context/product-onboarding-2026-09-27.md) contain the details.
The exact source checkpoint and verified recovery manifest are recorded in
`artifacts/product-onboarding-2026-09-27/final-checkpoint.json`; external backup:
`/Users/shree/FaultLab_Backups/2026-09-27/product-onboarding/`. Main/index/history/secrets are preserved.
All temporary services and browser tabs are closed. No GitHub push.

**Durability increment completed and verified.** The original learning workflow was
exercised end to end, then the app's ownership, recovery and local operation were hardened. One writable
coordinator now owns each store before recovery; archive mode never initializes or recovers records;
dashboard queries use independent read-only snapshots; job finalization and reservation release are atomic.
CLI registration, import/execution and portability preparation now use the owning backend. A paired local
launcher makes the data directory explicit. The dashboard handles missing saved IDs without repeated
requests and distinguishes full, partial and absent fault exposure.

Durability runtime: `7dfdfe29fd210c70b5b83915f0cd47b144e03d49ffe172a9dfa722c50bd523f0`.
The complete backend suite passed on this frozen source: **2,123 passed, 180 existing skips, zero failures**,
two warnings (Starlette deprecation and the explicit fork ownership test), 727.37 seconds. Three old restart
fixtures were corrected to close the first store; all recovery assertions stayed intact. Frontend:
**206 tests, production build and eight browser fixtures passed** (one opt-in actual-backend test skipped).
Actual manual checks used both the archive and a fresh offline store: one upgrade, one confirmation,
all eight fixed checks, zero model calls. A real process restart preserved all 23 records, eight events
and the policy pointer exactly. A second coordinator was refused before recovery. All eight closed live
SQLite files retained their hashes and modification times after archive browsing.
[Durability review](docs/PRODUCT_DURABILITY_REVIEW_2026-09-27.md) and
[current implementation memory](memory/context/product-durability-2026-09-27.md) record the evidence.

**The latest live original campaign is closed NO_CHANGE.**
[Declared run](docs/PRODUCT_LOOP_RUN_2026-09-27.md) `c701e850…`, frozen runtime `60f27623…`,
completed seven tasks with zero violations and seven verified traces. Eight Explorer requests included
one correctly declined duplicate. Exposure was four full recipes, one partial and two absent; the
status-read faults were not reached because the Actor already had terminal receipts. This is an Explorer
planning limitation, not an Actor mistake or FaultLab dispatch failure. No source candidate qualified;
baseline remains active. Independent audit passed 188 checks, including 34 read-only Weave readbacks.
[Closed result](docs/PRODUCT_LOOP_RESULTS_2026-09-27.md). No repeat campaign is planned merely to seek success.

**Spending:** $1.04662 conservative bound for those 39 live requests ($1.05 carried); measured token-priced
estimate $0.15324862, provider-billed cost unavailable. **Carried total $856.96. Durability and onboarding work: $0 in
provider calls.** All historical evidence is preserved. No GitHub push.

Continue to use the milestones below as hypotheses, not a fixed script. Exercise independent
architectural judgment and verify manually as well as with tests. Time and budget are generous;
the old allowance is historical accounting, not a renewed limit.

**Core reliability fixes are implemented.** The complete original workflow was traced in source.
Candidate violations now survive opposite-arm infrastructure retries; invalid simulator clocks are
classified as lab errors; new heldout plans apply the same boundary without rewriting old protocols.
Stop affects only owned active work, partial evaluations survive interruption, restart preserves
charges and releases abandoned reservations, and cleanup cannot strand the scheduler. Saved reads
run outside its event loop. Campaign and saved regression execution history now have bounded selectors;
provider-free readiness explains which local settings/services are missing.

Final verification passed against runtime
`58cd13b6f966d5b1c789fde7de9ca4bbdf744b2335bca25d9f3930e57e14f357`.
Frontend: **192 tests, production build and six browser checks passed** (one opt-in server test skipped).
Heldout/world integration: **104 passed**. A fresh dashboard reference run completed with one actual
upgrade, one confirmation, all eight checks and zero model calls; direct world reconstruction agrees.
The dashboard reopened five saved executions and an original trial from a read-only historical copy,
without executing anything. Full backend: **2,010 passed, 180 existing skips, zero failures**, one
dependency warning, in 714.97 seconds. The verified local source/evidence checkpoint is recorded in
`artifacts/product-core-2026-09-27/final-checkpoint.json`; its external recovery copy is
`/Users/shree/FaultLab_Backups/2026-09-27/product-core/`.

**That completed core increment spent $0; prior historical accounting was $855.91.** No GitHub push. No historical verdict,
active pointer or result report was changed. This work establishes specific product correctness and
usability improvements, not a generated accepted policy, successful unseen validation, repaired-policy
transfer or a second task. Those product milestones remain open.

The [product workflow audit](docs/PRODUCT_CORE_REVIEW_2026-09-27.md) records the trace, decisions and
verification. [Current implementation memory](memory/context/product-core-2026-09-27.md) supersedes
the earlier [continuation notes](memory/context/product-continuation-2026-09-27.md) for this work.

### Phase 31 and report-finalization follow-up

The owner authorized the recommended write-up/demo and focused offline follow-up. No new paid
experiment is planned in this round; the latest reserved result remains INCOMPLETE.

- [x] Prepare the [Phase 31 write-up](docs/part2/PHASE31_WRITEUP.md) and
  [four-minute demo guide](docs/part2/PHASE31_DEMO_GUIDE.md), with separate development,
  reserved-evaluation and active-policy claims.
- [x] Investigate repeated notification polling. [Review](docs/part2/NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md)
  confirms the older v2/v3 progress summaries already regressed. Keep v4; do not add a duplicate v5.
- [x] Implement a narrow final-report hook fix and precise diagnostics; independently review guard,
  citation, stop and budget behavior. Preserve the captured original development failure as a fixture.
- [x] Verify the fix with 45 focused checks and a fresh offline world reconstruction, comparing the
  original and corrected modules with the same captured answers. The correct result is SAFE_UNRESOLVED,
  with no extra business effects. [Fix and evidence](docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
- [x] Rehearse the saved-evidence dashboard using an isolated copy; provider calls disabled and writes
  rejected. Verify the original trial pair, all eight checks and retained baseline. Clarify one misleading
  main-loop sentence; 166 frontend checks and the production build pass after that text change.
- [x] Record the new runtime and complete one clean backend invocation: **1,952 passed, 180 existing
  skips, zero failures**, one dependency warning, in 697.17 seconds. Preserve the earlier cloud-read
  failures separately. Save code, documents and diagnostic evidence on the local backup branch and
  in `/Users/shree/FaultLab_Backups/2026-09-27/phase31-followup/`; no push.

Runtime of that completed follow-up: `b9410f5e77f2b98e6a621ee5adabc20c7ac65ea042f8a9d7049dedadaec7d719`.
The quoted live results still use `3da193e3…`; this offline correction is not a new live result.
Some Desktop source/dependency files became iCloud placeholders. The runtime and main database
are now readable; all 241,000 main-store records and 142,417 events match the preserved backup.
Unavailable originals have not been replaced. The source/evidence backups outside Desktop remain
the recovery copies. Keep the project downloaded before using it; do not treat file existence alone
as evidence that a cloud-backed database or dependency can be read.

- [x] Establish this status page and replace conflicting continuation pointers; preserve old notes.
- [x] Fix successful replay parsing and verify a real saved replay in the dashboard.
- [x] Decode Actor citations using the evidence available when the model was called, before report hooks.
- [x] Repair or correctly scope the two failing historical research tests.
- [x] Make normal app defaults use the tested model/context settings, preserving explicit historical versions.
- [x] Show development qualification, unseen-case results and the active policy separately.
- [x] Complete offline checks, manual saved-evidence verification and documentation of the new runtime.

### September 27 follow-up

- [x] Save the consolidation and Claude's existing report correction on the local backup branch
  (`52ee801`); preserve `main`, the real index, historical evidence and `.env`.
- [x] Obtain one clean, complete backend-suite result after the test corrections:
  **1,891 passed, 180 skipped, zero failures** in 712.56 seconds.
- [x] Verify exact model availability and published prices; prepare non-secret process settings.
- [x] Close the dashboard and stop its server and the idle backend before paid execution.
- [x] Freeze and execute the first separate public compatibility check. It stopped on HTTP 503
  after 16 attempted episodes: 15 completed with verified traces, 26 never attempted. Its status
  remains **INCOMPLETE**; original protocol, sealed plan, results and costs remain preserved.
- [x] Independently reconstruct those 16 worlds, actual effects, original answers, request identities
  and the 15 saved Weave readbacks; no mismatches found. The baseline remains active.
- [x] Add one bounded, charged retry for HTTP 503 with no returned generation; 66 focused checks
  passed and independent code review cleared the change. Returned answers are never re-rolled.
- [x] Complete the full backend suite again: **1,920 passed, 180 skipped, zero failures**.
- [x] Execute the sealed [service-reliability check](docs/part2/SERVICE_RELIABILITY_CHECK_2026-09-27.md)
  once: **42/42 episodes**, **36/36 faults triggered**, **42 verified Weave readbacks**;
  the saved repair completed **15/21 tasks**, versus **9/21** for the baseline, with zero violations.
  New runtime `3da193e3…`; separate store, same fixed policy and known public cases.
- [x] Finish the independent post-run reconstruction: all 42 worlds/reports/readbacks, 262 HTTP
  attempt identities, 66 operation journals and 336 rule checks agree. Save the final local checkpoint.
  [Full current review and results](docs/part2/CURRENT_REVIEW_2026-09-27.md) records both executions
  separately, manual findings, pricing, current spending and the recommended next experiment.

### Fresh repair experiment — execution and verification finished

The owner authorized a fresh repair-generation experiment followed by one reserved-case
evaluation on September 27. [Prospective declaration](docs/part2/PROSPECTIVE_REPAIR_2026-09-27.md).
This extends the evidence beyond Claude's original Phase 31 write-up/demo; it does not
reopen Phase 28 or activate a policy. The sealed run finished and must not be resumed or
rerun. [Full result and manual findings](docs/part2/PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md).

- [x] Declare up to ten development attempts; select the first strongly qualified new saved-policy hash.
- [x] Separate $100 generation and $60 evaluation pools, within the remaining $181.77.
- [x] Finish independent review and 102 offline checks; reserve three unexposed combinations and seal
  all inputs before generation. Frozen configuration `88e97d68…`; same tested application runtime.
- [x] Execute ten development studies / 162 episodes; the tenth produced the first new strongly
  qualified policy. Its development validation completed **15/21 versus 9/21**, with zero violations.
- [x] Execute all **156 reserved evaluation episodes** once. Formal result **INCOMPLETE**: one baseline
  episode never attempted its notification, so one scheduled fault could not fire. Candidate had
  **zero violations**, baseline one C5 report-label violation. No policy was activated.
- [x] Independently reconstruct all **318 worlds**, 2,544 checks, 1,996 HTTP attempts, 452 journals,
  315 filed reports and 318 saved readbacks; verify three episodes again directly in Weave.
- [x] Reconcile **1,783 requests / $37.68 carried cost**; preserve source, historical results,
  active baseline pointers and the main evidence store. Stop the simulator and other local servers.
- [x] Save all 318 worlds, all 11 stores, preparation/audit evidence and source locally; verify the backup manifest.

**Decision:** do not perform the suggested immediate “Phase 28 unseen-case check.” The frozen Phase 28
protocol explicitly disallows that routing. The old unseen-case generator also excludes notification
development cases but not `upgrade-v1`, so a different seed could repeat known upgrade faults. Instead,
the completed measurement compared the first strongly qualified Phase 28 policy and the empty baseline on
the seven already-public upgrade cases: 21 pairs / 42 episodes, under the corrected runtime, with a
$20 cap. It cannot establish new learning, unseen generalization, certification or policy acceptance.
The subsequent prospective experiment reserved new combinations before generating candidates,
then qualified and evaluated under one frozen runtime. Its coverage gate returned INCOMPLETE;
it does not establish an unseen-case pass. That partition is now spent.

Changes to runtime code produce a **new runtime identity**. They do not rewrite, resume or repin
closed Phase 17–30 experiments. The Phase 30 report-status hint remains experimental and is not adopted.

## What is established

FaultLab tests one task: upgrade an order in a synthetic shop and send one truthful confirmation.
The Actor performs the task; a Mechanic proposes bounded recovery rules; a fixed Referee checks
the outcome. The original discovery workflow also has an Explorer, reproduction, diagnosis,
challenge and promotion. A separate completion study uses a chosen failure case and never promotes.

| Evidence | Established result | Limit |
|---|---|---|
| Phase 17 | 1 development-certified repair attempt out of 9 | Separate completion experiment, not original promotion |
| Phase 23 | 3 out of 30, three notification-side policies | One routed policy subsequently failed its unseen-case check |
| Phase 28 | **9 out of 49; eight distinct upgrade-side policies** | Development cases only; no unseen-case evaluation of these policies |
| September 27 compatibility check | Saved repair **15/21 completed**, baseline **9/21**, zero violations across 42 episodes | One existing policy on known public cases; no new qualification or acceptance |
| September 27 fresh repair experiment | **1 of 10 studies qualified**; 15/21 versus 9/21 on development validation | Bounded first-success search; not an unbiased repair-rate estimate |
| September 27 reserved evaluation | All **156 episodes** ran; candidate zero violations, baseline one | **INCOMPLETE** because one baseline fault did not trigger; no NO_HARM claim |
| Original policy acceptance | **Zero generated ACCEPTED policies** | All recorded active pointers remain `policy-v0` |
| Native smolagents | Live independent-agent baseline already completed in Phase 1 | Same shop; accepted-repair transfer remains unproven |

Phase 28 retained **1,104 scored trials**, all 885 scheduled faults triggered, all 1,104 saved
Weave readbacks verified, and no detected clock drift or missing worlds. Its selected certified
policies had no failed checks in 216 trials. The whole experiment retained 22 violating trials
across baseline and unsuccessful candidates. It stopped normally at its spending guard after
49 of 50 planned attempts. Its success rate is a repair-attempt yield, not general agent accuracy.

The executed Phase 28 path was **chosen source → baseline controls → Mechanic proposal → source
tests → development validation**. It did not invoke the Explorer, generated challenges or original
promotion. The primary report's earlier Explorer wording was corrected by Claude before this work.
See the new [clarification note](docs/part2/STATUS_NOTES_2026-09-27.md); no historical results are
edited by this consolidation.

“Development qualified” means the stated development requirement passed. “Unseen-case result”
is a separate frozen-policy evaluation. “Active policy” is what the campaign actually uses.
None implies either of the others. Completion studies cannot activate a policy. Earlier unseen-case
checks returned HARM; the Phase 24 failure was an unsupported PENDING report after UNKNOWN
observations. That verdict stands; it does not by itself prove causal harm. Tested partitions are spent.

The shop, fixed checks, repeated trials, incident export, fresh regression execution and evidence
storage work. A second task environment, general agent onboarding, successful repair validation on reserved unseen cases and a shared hosted product are not established.

## Evidence and reading order

1. [Product workflow review](docs/PRODUCT_CORE_REVIEW_2026-09-27.md) and
   [current implementation memory](memory/context/product-core-2026-09-27.md): implemented core fixes,
   final verification and open product milestones. The original continuation notes remain historical context.
2. [Offline report-finalization correction](docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
3. [Latest fresh repair and reserved-case results](docs/part2/PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md).
4. [September 27 earlier review and compatibility results](docs/part2/CURRENT_REVIEW_2026-09-27.md).
5. [Historical repair-generation result: Phase 28](docs/part2/PHASE28_RESULTS.md) and its
   [declared protocol](docs/part2/PHASE28_EXPERIMENT.md).
6. [Phase 24 unseen-case result](docs/part2/PHASE24_RESULTS.md).
7. [Phase 30 narrow reporting probe](docs/part2/PHASE30_RESULTS.md): recommended for a later experiment,
   not adopted and not an end-to-end result.
8. [Phase 1 results](docs/part2/PHASE1_RESULTS.md): native agent, incident export and regression evidence.
9. [Original month plan](docs/part2/PLAN.md): a historical roadmap, not a completed-feature list.
10. [Phase 31 write-up](docs/part2/PHASE31_WRITEUP.md) and [demo guide](docs/part2/PHASE31_DEMO_GUIDE.md):
    completed communication assets, not a declaration that the product is finished.
11. [Preserved handoff notes](memory/history/2026-09-27-before-consolidation/README.md) for detailed history.

The original [specification checklist](../FaultLab_Specs/specs/001-faultlab-loop/tasks.md)
ends at Phase 15: 234/239 checked. This is not a product completion percentage. T065, T088,
T097, T100 and T102 remain open: original learning/promotion evidence, complete sponsor/Aria
walkthrough, final freeze, independent transfer/selector acceptance, and the complete final audit.
Do not check those off because completion studies or software tests pass.

## Configuration and execution

- App root: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.
- Specs root: sibling `FaultLab_Specs/` (outside the application Git repository).
- Latest tested Actor: `deepseek-ai/DeepSeek-V3.1`.
- Latest tested Mechanic and configured Explorer: `deepseek-ai/DeepSeek-V4-Pro-0813`.
- Latest tested Actor context: `faultlab-actor-context/v4-indexed-evidence`.
- Confirmed W&B destination: `shreetbohara-quinstreet/Faultlab` (capital F).
- Credentials remain in the existing `.env`; do not print, copy into docs, overwrite or commit it.
- Aria remains deferred. Starting servers, viewing evidence and offline tests must not make provider calls.
- Both launchers use the same application model/context defaults. Nonempty `.env` values and explicit
  process overrides win; empty model placeholders in old `.env` templates adopt the defaults without
  editing the file. An explicitly blank process model override is still respected.
- New campaign configuration freezes the selected Actor context. Explicit study overrides remain valid;
  historical snapshots without that field retain v1. This does not bypass runtime compatibility checks.
- Startup remains offline by default and Aria is off. The live launcher does not supply historical prices
  or mark them verified; exact-model pricing must be configured before a paid campaign can be admitted.
- Completion studies already default to the tested v2 task-outcome evidence summary. Their ordinary
  case manifest remains `notification-v1`; Phase 28 explicitly chose `upgrade-v1`. Selecting the same
  models is not a replay of Phase 28 or evidence of a new successful experiment.
- Backend `http://127.0.0.1:8000`; simulator `http://127.0.0.1:8001`; dashboard
  `http://127.0.0.1:5173`. Open the dashboard URL, not `frontend/index.html` as a file.
- Start commands and offline verification: [setup](docs/setup.md) and [user guide](docs/user-guide.md).

The idle backend and dashboard were used for the saved-evidence verification, then stopped during
this follow-up. The owned simulator is also stopped after verification. A live model-catalog check verified both selected IDs
without generation. Both compatibility checks used their own stores and explicitly declared their
new runtimes; historical campaigns are read-only. Recheck processes before starting or stopping services.

## Ledger entry 2026-10-11: Claude Actor screen (v2 reset, first paid runs)

Four declared baseline studies (DeepSeek V3.1 control, Claude Haiku 5.5, Sonnet 5.5, Opus 5.5; 18 live
episodes each): reserved bounds $3.01 + $0.61 + $12.10 + $24.19 = $39.91, measured $2.70; two smoke
requests $0.08 reserved. Project ledger carried forward: $937.99 + $39.99 = **$977.98** (bounds, as always).
Write-up: `docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`; evidence `~/FaultLab_Runs/2026-10-11/claude-actor-screen/`.

## Ledger entry 2026-10-11: Claude Actor screen phase B

Thirty of the declared 36 baseline studies started (the loop stopped at 18:56 UTC after the owner's
console spend limit refused Claude calls from 18:49): DeepSeek control 8, Haiku 8, Sonnet 7, Opus 7.
Reserved bounds from the declaration, per started study: 8 x $3.01 + 8 x $0.61 + 7 x $12.10 + 7 x $24.19
= **$282.99**; measured $18.27 (`artifacts/claude-actor-screen-2026-10-11/phase-b/LEDGER.phase-b.auto.json`;
two studies inside the block carry no measured cost). Project ledger carried forward: $977.98 + $282.99
= **$1,260.97** (bounds, as always). Read-outs: the Phase B section of `docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`.

## Ledger entry 2026-10-12: Claude Actor screen phase C (refused at admission)

One of the declared 18 studies ran: the round-1 DeepSeek control (`c1-deepseek-v3.1-control`, COMPLETED).
The first Fable study was refused when queued (hold $507.36 at Fable's $0.42 per-call bound against the
lab's $500 campaign-cap ceiling) and the loop stopped. Reserved bound for the started study: 1 x $3.01 =
**$3.01** (the Fable study was never admitted, so nothing was reserved for it); measured $0.16
(`artifacts/claude-actor-screen-2026-10-11/phase-c/LEDGER.phase-c.auto.json`). Project ledger carried
forward: $1,260.97 + $3.01 = **$1,263.98** (bounds, as always). Read-outs: the Phase C section of
`docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`.

## Ledger entry 2026-10-12: Claude lab-loop probe piece D

Seven completion studies started under `DECLARATION.piece-d.json`: two attempts ended INCOMPLETE after
one control trial each on the Weave project-name mismatch and are excluded; the declared five then ran
to completion, all NO_CHANGE at the controls stage. Reserved bounds from the declaration, per started
study: 7 x $40.99 = **$286.93** (480 Actor calls at Sonnet's $0.084 plus 4 Mechanic calls at Opus's
$0.168; the campaign hold per study was $260.06); measured $1.48 for the five plus $0.11 for the two
attempts = $1.59 (`artifacts/claude-lab-loop-probe-2026-10/piece-d/LEDGER.piece-d.auto.json` carries the
five). Project ledger carried forward: $1,263.98 + $286.93 = **$1,550.91** (bounds, as always).
Read-outs: `docs/CLAUDE_LAB_LOOP_PROBE_2026-10.md`.

## Ledger entry 2026-10-25: first run on the subscription channel (claude-code provider)

One declared baseline study, `claude-code:claude-haiku-5-5`, through the Claude Code CLI on the owner's
subscription (`~/FaultLab_Runs/2026-10-25/claude-code-channel-smoke/`, declaration sha256 `0f464e28…4573`,
commit `fc9dc45`): COMPLETED, 18 live episodes, 15 completed and 3 violations (all dev-5 through C5, the
pattern phase B saw for Haiku on the API), all 18 episodes `weave_verified`, 90 calls, 236 seconds.
Money: **$0** (91 ledger rows at zero); API-equivalent cost $0.056, the shadow price the campaign ledger
charged. Project ledger carried forward unchanged at **$1,550.91** (bounds); the channel's equivalent
figures are reported, never added. A smoke of the channel, not a screen result.

## Ledger entry 2026-10-25: first run of the Claude Agent adapter (Claude Code as the agent under test)

One declared batch, `faultlab run --adapter claude-agent --model claude-haiku-5-5 --execute-live --dollars 1`,
every scenario of the orders pack once, on the owner's subscription (`~/FaultLab_Runs/2026-10-25/claude-agent-adapter-smoke/`,
declaration sha256 `c8b85812…640e`, commits `94c129f` and `17edfdf`, bundle in
`artifacts/claude-agent-adapter-smoke-2026-10-25/`): dev-1, dev-2, dev-3, dev-4 and dev-6 COMPLETED with no
violation; dev-5 VIOLATION through C5 (the notification label after a rejection, as Haiku shows on the API);
the stale-read fault of dev-4 did not fire. 29 model calls, 125,079 input and 225 output tokens, 55 seconds.
Money: **$0**; API-equivalent $0.013 (the adapter's shadow price). Project ledger carried forward unchanged at
**$1,550.91** (bounds). A smoke of an adapter, not a bench result. Two earlier attempts the same hour ended
on defects the run exposed (the batch cap admitting one trial; each content block charged as a turn), fixed
in `17edfdf`; their files are kept beside the run as `attempt1` and `attempt2`.

### Repair study smoke (2026-10-26, subscription)

One declared run of `faultlab study repair` (commit `9580bc0`, `~/FaultLab_Runs/2026-10-26/repair-study-smoke/`,
declaration sha256 `e8517621…a1db`, record and bundles in `artifacts/repair-study-smoke-2026-10-26/`): Haiku 5.5
as Actor through the Claude Agent adapter, Sonnet 5.5 as Mechanic through the Claude Agent SDK, both on the
owner's subscription. Controls: 4 of 6 dev-5 trials carried the target finding (C5,
`notification_label_after_rejection`), 3 of 3 dev-1 clean; the gate opened. The Mechanic proposed a valid policy
at its first attempt in both slots (two turns, 6,497 input tokens each): slot 1 `report_terminal_failure` alone,
which cannot touch a label (L 2 of 3 target, as B0); slot 2 added `require_label notification_outcome
NOT_STARTED`, the slip's own label, so nothing was blocked (L 2 of 3 target). Decision NO_CHANGE at the
candidate stage; validation never ran. 21 trials, 100 Actor model calls, 405,954 input and 1,174 output tokens,
181 seconds. Money: **$0**; API-equivalent $0.041 Actor + $0.027 Mechanic = $0.068 (shadow price). Project
ledger carried forward unchanged at **$1,550.91** (bounds). A smoke of the study with a real Actor and a real
Mechanic, not a pilot result. Two design findings, recorded in
[VIOLATION_GAP_DESIGN_2026-10-25.md](docs/VIOLATION_GAP_DESIGN_2026-10-25.md): the Mechanic's view carried no
label vocabulary (the public report schema), and the candidate gate's "expected outcome 3 of 3" cannot be met
by an Actor that truthfully reports SAFE_UNRESOLVED on dev-5 five times in twelve; both amended for a second smoke.

### Repair study smoke 2 (2026-10-26, subscription)

Same Actor, Mechanic, channel and parameters as smoke 1 with its two amendments (commit `370a1e2`,
`~/FaultLab_Runs/2026-10-26/repair-study-smoke-2/`, declaration sha256 `0e18e595…968f`, record and bundles in
`artifacts/repair-study-smoke-2-2026-10-26/`). Gate opened again (4 of 6 dev-5 controls with the C5 label slip,
dev-1 3 of 3 clean). With the report contract in view, both Mechanic slots proposed the repair the design note
expected, `require_label notification_outcome NOT_REQUIRED` when the upgrade's `terminal_failure` holds, at the
first attempt (two turns, 7,208 input tokens each). Slot 1 (condition `always` on the step) blocked six
NOT_STARTED or UNKNOWN proposals across three trials; Haiku relabelled to NOT_REQUIRED in one trial and ran out
of turns in two, which the adapter filed as `ADAPTER_ERROR:RuntimeError` (the CLI's `error_max_turns`): not
qualified. Slot 2 put the step's condition on the notification operation, which never fails, so the rule never
acted; its L arm showed 0 of 3 target by chance (three truthful SAFE_UNRESOLVED reports against 3 of 3 slips
under B0) and "qualified", then failed validation on dev-4 (the stale-read fault unfired in 3 of 3 L trials
against 1 of 3 under B0, the Actor's path, not the rule) and dev-6 (2 completed and 1 SAFE_UNRESOLVED against
the 3 of 3 `must_complete` rule). Decision NO_CHANGE. 51 trials, 248 Actor model calls, 1,062,408 input and
2,244 output tokens, 466 seconds. Money: **$0**; API-equivalent $0.107 Actor + $0.030 Mechanic = $0.137. Project
ledger carried forward unchanged at **$1,550.91** (bounds). Five amendments follow, in the design note.

## Budget

**Current carried accounting: $898.58 conservatively charged** (ledger
`artifacts/product-live-2026-09-28/ledger.json`, as committed in `4d1c21b`; the earlier $893.86 is superseded) = $856.96 below
+ $2.14 native baseline probe `e5b01658` ([result](docs/PRODUCT_NATIVE_PROBE_2026-09-28.md))
+ $1.04 INCOMPLETE discovery-v2 run `a301846e` ([result](docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-28.md))
+ $1.46 complete discovery-v2 run `17d60a9e` ([result](docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-29.md))
+ $7.53 native original-loop learn `7ee35abe` ([result](docs/PRODUCT_NATIVE_LEARN_RUN_2026-09-29.md))
+ $2.35 v3 baseline study `aaceaf2f` + $15.91 v3 learn campaign `a2fbffe3` ([result](docs/PRODUCT_NATIVE_LEARN_V3_RUN_2026-09-29.md))
+ $6.47 native adapter v2 first live run ($2.07 baseline probe + $4.40 learn `b05ac280`; [result](docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md))
+ $4.72 native adapter v2.1 live runs ($2.12 baseline study `c8063a11`, declared NO_GO; $2.60 separately declared v3-history
Learn campaign `077b8434`, NO_CHANGE; evidence `artifacts/product-live-2026-09-30/native-v2b-run/` and `native-v2c-run/`;
no write-up on this page yet).
The transport-retry, discovery-v3, dependability, native-v2, September 30 and discovery-v4 builds, reviews and fixes made
no provider call ($0).

The previous carried accounting was **$856.96 conservatively charged**: the previous $855.91 plus
$1.05 for the completed original-workflow campaign (39 requests, exact bound $1.04662).
Its token-priced estimate is $0.15324862; provider billing is unknown. The independent audit and
current durability implementation made zero new inference calls. The owner has repeatedly authorized
further work with generous resources; the old $1,000 allowance is historical. The actual provider balance and billed cost are unavailable;
do not invent either, reset prior charges or interpret generous resources as permission for unbounded
unattended spending. Declare and monitor the next experiment's allocation and verify its exact prices.

The ledger begins with Phase 2; changing accounts, agents or machines does not reset it.
Before this follow-up, the non-overlapping historical ledger summed to $811.39726
and its carried figure was $811.70, conservatively higher due to an old probe double-count and rounding.
That difference was not reclaimed. See the
[preserved ledger](memory/history/2026-09-27-before-consolidation/memory/context/runtime-and-evidence.md).

The original consolidation made no paid calls. The first separate compatibility check charged
81 model requests / $1.6929 upper bound, carried as $1.70. The complete follow-up charged
231 requests / $4.8279 upper bound, carried as $4.83. Together: **312 requests / $6.5208**, carried as
**$6.53**. Both costs remain recorded separately; incomplete runs are not erased or refunded in this ledger.
That earlier machine-readable accounting remains at
`artifacts/verification-2026-09-27/followup-budget-ledger.json`.

The fresh repair experiment added **978 development requests / $20.84536** and **805 evaluation
requests / $16.82450**, conservatively carried as $20.85 + $16.83 = **$37.68**. Total new requests:
1,783. The current ledger is `artifacts/prospective-repair-prep-2026-09-27/final-budget-ledger.json`;
the independent accounting audit records all 11 stores. The INCOMPLETE evaluation is fully charged.

The owner reported adding more than $1,000 and authorized further work. This is not a verified provider
balance and does not erase prior charges. All three bounded experiments fit the existing allowance. Exact model
prices and the required non-secret process settings are documented in the
[current review](docs/part2/CURRENT_REVIEW_2026-09-27.md#exact-model-pricing-and-admission).

## Source and backups

Latest verified source is saved on local `backup/part2-2026-09-22`; exact commit and unchanged main/index
are in `artifacts/product-onboarding-2026-09-27/final-checkpoint.json`. Its external `product-onboarding/`
copy includes source, test/native-fixture evidence and both actual manual workspaces. The earlier `product-core/` recovery copy
contains a self-contained source bundle, new diagnostic stores/worlds, manual screenshots, full check
logs, current notes and a verified hash manifest. Historical evidence backups below remain intact.
No GitHub push was made. Do not reset or stage everything relative to the intentionally old main.

At the September 27 audit, local `main` and GitHub `main` were at `cbbf957` (September 14).
Local `backup/part2-2026-09-22` was at `7c36110` (September 26), 22 commits ahead. All 585
files in that backup matched the working folder before Claude's later wording correction and this
implementation. Current edits are therefore additional local work; do not reset the working tree.
Recheck Git state before publishing. This work does not push or merge branches.
The September 27 consolidation is saved on that local backup branch at `52ee801`; the reviewed
replication runner and declaration are saved at `deff0b1`; the bounded 503 fix and follow-up declaration
are saved at `e38f7db`. The final results are saved on the same local backup branch. `main` and GitHub
were not moved.
The fresh experiment's sealed source and offline tests are saved at `7000ced`; its results and current
status are saved in the subsequent local checkpoint. No GitHub push was made.
The Phase 31 report-finalization code/tests and dashboard wording are saved locally at `0eb7da7`;
the completed write-up, demo and validation record are saved in the following checkpoint on the
same backup branch. `artifacts/phase31-followup-2026-09-27/final-checkpoint.json` records the exact
final commit and verifies every saved source file against the working folder. Main and its index
remain unchanged. The separate `phase31-followup/` backup contains a complete source bundle,
both diagnostic worlds, review records, logs, a demo screenshot and a verified file manifest.

Ignored `artifacts/` contains roughly 4.5 GB of databases, worlds and evidence. A source clone does
not carry it. `/Users/shree/FaultLab_Backups/2026-09-26/lab-after-phase28.sqlite3` matches the
campaign, episode, policy, verdict and evidence records checked in the main store at audit time.
Keep local world files and frozen configurations with the database. The temporary Phase 28 worktree
is an older preparation copy; do not use it as the latest implementation.
Both September 27 experiment stores, all 58 new world databases and their verification files have
byte-verified copies at `/Users/shree/FaultLab_Backups/2026-09-27/followup-verification/`.
Its `MANIFEST.json` records every copied file hash; it contains no credentials.
The fresh repair experiment has a separate verified backup at
`/Users/shree/FaultLab_Backups/2026-09-27/prospective-repair/`, including all 318 worlds, 11 stores,
commitments, independent audits, current reports and a self-contained source bundle.
Its manifests record copied file hashes; credentials and SQLite transient sidecars are excluded.

## Verification and known issues

**Runtime `ac7a12d2…` (September 29, native adapter v2 and its review fixes; evidence `artifacts/product-native-v2-2026-09-29/fixer/`):**
the fixer ran `scripts/test.sh` once after its last edit (`fixer/full-test-sh.log`). Not yet independently verified or committed.

**Previous runtime `5583dcad…` (September 29, dependability round; evidence `artifacts/product-dependability-2026-09-29/verify/`):**
an independent verifier ran each suite once after the last edit, in the workspace and in a fresh clone on non-default ports:
* workspace backend **2,756 passed, 180 skipped, 0 failed** (1,080 s); fresh clone **2,704 passed, 232 skipped, 0 failed** (1,118 s; the extra skips are the tests that need two git-ignored files);
* frontend **329 unit tests**; production build passed; **17 browser tests passed, 1 opt-in skipped**;
* gates and scorer unchanged (`checks.py` hash, `assess_pairs` text and AST, 30 of 30 functions); simulator service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…` unchanged;
* 48 files (36 changed, 12 new) committed as `94b130e`; main `cbbf957` untouched; nothing pushed; $0, no provider calls.

**Previous runtime `08e4c20d…` (September 29, discovery v3 review fixes; evidence `artifacts/product-discovery-v3-2026-09-29/fixer/`):**
one run of each suite after the last code edit:
* full backend **2,683 passed, 180 existing skips, 0 failed**, with the 2 known warnings, in 928.06 s;
* frontend **320 unit tests** (19 files);
* production build (size advisory only);
* **16 browser tests passed, 1 opt-in skipped**.

Identities: runtime `08e4c20d…`, algorithm `8fb8ab2a…`. These are unchanged: service `3ce5bcd2…`, contract
`6f9d7783…`, interpreter `6da0714a…`, reference Actor prompt `12eabe7f…`, native prompt `2251542869cf…` and
native adapter `61497db3…`. `referee/`, `simulator/` and `contracts/` are identical to `backup/part2-2026-09-22`.
All 8 saved run stores were read only with `mode=ro&immutable=1` and kept their sizes and modification times.
HEAD `cbbf957` and the empty index are unchanged; nothing was committed. After the suites, only this file and the
discovery v3 note were edited, and no test reads either.

**Previous runtime `a8a32234…` (September 29, discovery v3 builder; evidence `artifacts/product-discovery-v3-2026-09-29/builder/`):**
one run of each suite after the last code edit:
* full backend **2,673 passed, 180 existing skips, 0 failed**, with the 2 known warnings, in 927.49 s;
* frontend **317 unit tests** (19 files);
* production build (size advisory only);
* **16 browser tests passed, 1 opt-in skipped**.

Identities: runtime `a8a32234…`, algorithm `eea45d1d…`; service `3ce5bcd2…`, contract `6f9d7783…`, interpreter,
reference Actor prompt `12eabe7f…` and native prompt `2251542869cf…` unchanged. The two native stores read (only
with `mode=ro&immutable=1`) kept their sizes and modification times. HEAD and index are unchanged; nothing was
committed.

**Previous runtime `c9af0a47…` (September 29, review fixes; evidence `artifacts/product-retry-2026-09-29/fixer/`):**
one clean run of each suite after the last code edit. Full backend **2,651 passed, 180 existing skips, 0 failed**, the
2 known warnings, 932.61 s; audit hook: **0 outside connections or lookups**, `.env` touched only by the 3 synthetic
events in `test_env_guard.py`. Frontend **312 unit tests** (18 files), production build (size advisory only), **15
browser tests passed, 1 opt-in skipped**; Node guard logged nothing. New or changed tests cover the Mechanic request
kinds, unknown cost after a retry (Explorer, Mechanic, Actor; loss-free controls keep the known cost), the checker's
reasons, digit/keycap/pictograph task display (unit, component and random-mix oracle), and the "during discovery"
text. Negative control on a scratch copy whose reverted files equal the builder's: backend 12 and frontend 7 of the
new or changed tests fail; the rest check unchanged behaviour. Manual $0: the real dashboard marks a selector after
each digit in the Run desk, saved plan and history, and keeps keycaps and pictographs plain; the companion checker
reads the native-probe store as before (0 drifted, 13 cleared) and gives the Phase 1 store's reason per row. The
console 404 on first load is Chrome's `/favicon.ico` request (no icon shipped), not an API call. Historical stores:
9,409 files, no content or size change, only the 3 known `-shm` timestamps moved. HEAD `cbbf957`, backup branch and
index unchanged; nothing committed. Identities: runtime `c9af0a47…`, algorithm `6d6433df…`, service `3ce5bcd2…`,
contract `6f9d7783…`, interpreter `6da0714a…`, `check_clock_drift.py` `fa25ab9d…`.

**Previous runtime `debc86f3…` (September 29, builder; since reviewed twice, see *Current work*):** one clean run of each
suite after the last code edit. Full backend **2,642 passed, 180 existing skips, 0 failed**, the 2 known warnings,
950.60 s; audit hook: **0 outside connections or lookups**, `.env` touched only by the 3 synthetic events in
`test_env_guard.py`. Frontend **310 unit tests** (18 files), production build (size advisory only), **15 browser
tests passed, 1 opt-in skipped**; Node guard logged nothing. New tests: `tests/agents/test_role_transport_retry.py`,
`tests/lab/test_campaign_transport_retry.py`, `tests/lab/test_native_transport_retry.py`,
`tests/lab/test_transport_retry_plans.py`, additions to `test_bundle_import_boundaries.py` and `test_config.py`;
frontend `transport-retry.test.tsx` plus task-text and discovery additions. Negative control: run on the checkpoint `e7340c9`
code, the new tests fail (backend 14 of 17, frontend all 8 new or changed; the 3 backend passes assert behaviour
that did not change, e.g. a retry the budget refuses). That control predates the checker companion.
A first full run failed 78 closed-runner pin tests because `check_clock_drift.py` had been edited; it was restored to
its pinned bytes (see above). Historical `.sqlite3`/`-wal` files: 9,176 checked, hashes unchanged; only the 3 known
`-shm` timestamps moved. HEAD `cbbf957` and the real index unchanged; nothing committed. Evidence:
`artifacts/product-retry-2026-09-29/builder/` (`suites/`, `negative-controls/`, `checker-native-probe/`, `manual/`).

*Independently re-verified by verifier4 (September 28): every count below was reproduced exactly (backend 2,562 /
180 skipped / 0 failed; frontend 303, build, 15 + 1 opt-in skip); see* Independent verification *under* Current work.

**Current runtime `c0a8aad7…` (September 28, after the PM's simulator revert):** one clean invocation of
each suite after the last source/test edit. Full backend **2,562 passed, 180 existing skips, zero failures**,
two known warnings (Starlette alias, explicit fork test), 928.94 s; a log-only audit plugin recorded **0
non-loopback connects or name lookups** and no `.env` open attempt other than the three intentional
synthetic audit events in `tests/test_env_guard.py`. Frontend **303 unit tests** (17 files), production
build (bundle-size advisory only) and **15 browser fixtures passed**; one opt-in actual-backend check
skipped. New tests: `tests/simulator/test_entry_point.py` (simulator identity pinned to the checkpoint and
matching the restored download; import builds the entry point with a 0600 capability, 403 without or with a
wrong token, 200 with it; a restart reuses the capability; the test process's import-time app lives in
scratch, not `artifacts/`) and a plan-record test in `tests/lab/test_discovery_v2_flow.py` (new records carry
`discovery`, `null` for baseline; a record saved before the field still verifies and reads as v1).
Caller gate re-run: **PASS** (3,337 stored V3.1 episodes, 124 checked points, lowest 83.3%); its control with
caller v1's re-send patched in a scratch process **FAILS** on 20 of 134 points, the review's figure.
**Manual real-dashboard check** ($0; real backend API and simulator on 127.0.0.1 over a scratch store; the
tests' scripted, provider-free native agent; `.env` and outside network refused by an audit hook, neither
attempted): the restored checkpoint download was reviewed as eligible and its target compatible, and a
confirmed fresh rerun COMPLETED (3 of 3 valid trials, incident reproduced, not provider-backed, $0); the
other-simulator download was refused, naming `bundle 1099eda7…, installed 6f9d7783…`, with Run disabled; a
correctly hashed bundle whose task hides a sentence in 38 variation selectors plus 4 on a blank line showed
"42 invisible characters", 38 markers and `⟨5 blank lines, 4 invisible characters⟩` in the review and 38
markers in the confirmation box, and its escaped copy decodes to the exact task. Historical `.sqlite3` and
`-wal` files unchanged (only the three known `-shm` timestamps moved); the real control-capability file is
unchanged (0600, September 12); provider calls 0, cost $0; HEAD and index unchanged. Evidence (durable,
git-ignored): `artifacts/product-discovery-2026-09-28/fixer3-0928/` (`suites/`, `gate/`, `manual/`, `moved/`).
*Scratch evidence lost:* a macOS update restart wiped `/private/tmp`; the scratchpad folders cited for
earlier runtimes (`fixer-0928/`, `fixer2-0928/`, `discovery-v2/`, `review-disc-v2/`, `secops-review-0928/`) no
longer exist. Their figures remain as recorded.

*Superseded:* **runtime `c9b1b7e6…` (September 28, after the discovery-v2 and security/import reviews):**
Full backend **2,558 passed, 180 existing skips, zero failures**, two known warnings (Starlette alias,
explicit fork test), 864.82 s, in one clean invocation after the last source/test edit. A log-only audit
plugin recorded **0 non-loopback connects or name lookups** and no attempt to open the real `.env` other than
the three intentional synthetic audit events in `tests/test_env_guard.py`, which the conftest guard refused.
Frontend **303 unit tests** (17 files), production build (bundle-size advisory only) and **15 browser
fixtures passed**; one opt-in actual-backend check skipped. Caller gate
`scripts/experiments/check_reachability_caller.py`: **PASS** on 3,337 stored DeepSeek-V3.1 episodes, 124
checked points, none below 80% (lowest 83.3%). A new invariant test runs every shared task-text case and 400
seeded random mixes: no hidden character appears as plain text, the count covers every default-ignorable
character, the warning and escaped copy appear, and the escaped copy decodes back to the exact text. The
pre-fix display fails it on 364 of 428 texts. Historical `.sqlite3` and `-wal` files kept their sizes and
modification times; provider calls 0, cost $0; HEAD and index unchanged. Evidence: scratchpad `fixer-0928/`
(the fixes) and `fixer2-0928/` (that verification), both lost.
Intermediate runtimes, superseded: `bb87c764…` (hardening; backend 2,402 passed / 180 skips, frontend 286,
build, 15 browser + 1 opt-in skip) and `9f53eb8c…` (discovery v2; backend 2,490 passed / 180 skips, frontend
295, build, 15 browser + 1 opt-in skip, as re-run by the reviewer).

*Historical —* **Import increment runtime `cfe5ac07…` (September 28, after review fixes):** Full backend **2,363 passed, 180 existing skips, zero failures** (two known warnings); frontend **254 unit tests, production build and 13 browser fixtures passed** (one opt-in actual-backend check skipped).
Manual $0 check: import → review → confirmed fresh rerun with the scripted native target, archive reopen,
refusals and the local-host guard, on a scratch store and non-default ports.

**Onboarding runtime `d1845765…`:** full backend 2,224 passed / 180 existing skips / zero failures, 791.81 seconds;
219 frontend tests / build / ten browser fixtures pass. Two backend warnings: upstream Starlette alias and
the explicit POSIX fork ownership test. Vite bundle 502.10 kB minified / 118.64 kB gzip produces a size advisory.
Actual setup/six cases/download/restart/final-source freeze/archive and independent raw audits passed.
[Full log](artifacts/product-onboarding-2026-09-27/full-backend-final.log),
[review](docs/PRODUCT_ONBOARDING_REVIEW_2026-09-27.md). The incomplete isolated suite is preserved;
missing historical fixtures and invalid old test doubles were diagnosed, not silently skipped.

**Previous core runtime `58cd13b6…`:** one complete backend invocation passed **2,010 tests**, with
**180 existing skips**, zero failures and one dependency deprecation warning, in 714.97 seconds.
[Full log](artifacts/product-core-2026-09-27/full-backend.log) and
[result](artifacts/product-core-2026-09-27/full-backend-result.json). Frontend **192 tests and build
passed**; **six browser checks passed**, one opt-in server check skipped. Manual real-server work ran
separately: fresh reference smoke, direct world reconstruction, bounded campaign navigation, readiness
and saved regression/trial reopening. All used isolated stores and zero provider calls.
[Product review](docs/PRODUCT_CORE_REVIEW_2026-09-27.md) distinguishes fixture gates, actual local worlds,
copied historical evidence and unproven live repair claims. All 31 historical result documents and
the main database's complete hash are unchanged. Temporary services are stopped.

**Previous offline runtime `b9410f5e…`:** one complete backend run passed **1,952 tests**, with **180 existing
skips**, zero failures and one dependency deprecation warning, in 697.17 seconds.
[Full log](artifacts/phase31-followup-2026-09-27/full-backend-hydrated.log).
Frontend **166 tests and production build passed** after the main-loop wording change. Manual
verification covered the original/corrected report-hook reconstruction, direct world-state inspection,
and the real saved dashboard trial pair. [Verification note](docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
The earlier invocation hit three failures and six setup errors reading the unhydrated main database;
its full log remains preserved. No test was changed or newly skipped to obtain the clean result.

Audit baseline on September 27: **1,805 backend tests passed, 180 skipped, two failed**;
**124 frontend tests**, production build and **three browser fixture checks passed**.
The optional actual-server smoke was skipped.

**Previous live runtime verification:** after the 503 fix, one complete backend invocation finished with
**1,920 passed, 180 existing skips, zero failures**, one dependency warning, in 702.49 seconds.
[Full log](artifacts/verification-2026-09-27/backend-full-after-service-retry.log) and
[result](artifacts/verification-2026-09-27/backend-full-after-service-retry.json).
The earlier clean 1,891-pass run and combined-run record remain preserved; the latest full run
supersedes them for runtime `3da193e3…`. Separate focused Actor/provider checks: 66 passed;
shared checks of both experiment entry points: 74 passed. Offline checks made no provider calls.

**Previous frontend verification:** 166 tests, production build and three browser fixture checks passed. The optional automated
actual-server mutation test remains skipped; manual real-server checks covered the successful saved
replay, Phase 28 qualification, Phase 24 HARM, retained baseline policy, and displayed model/context defaults.
Read the [new verification note](docs/part2/STATUS_NOTES_2026-09-27.md).
Local proof: [dashboard screenshot](artifacts/verification-2026-09-27/unseen-result-and-active-policy.png) and
[verification summary](artifacts/verification-2026-09-27/verification-summary.json). These ignored local artifacts
are not included in a source clone. Those original implementation checks used saved data only;
the separately declared live compatibility follow-up is tracked above.

- **Fixed:** one bounded, charged retry handles a model HTTP 503 with no returned generation.
  Controlled failure tests and code review verify the branch. No real 503 occurred in the complete
  live follow-up; that run verifies integration, not another provider-error recovery.
- **Fixed:** successful replays validate against their saved replay-policy hash. Ordinary generated-candidate
  validation remains strict. A real 42-trial successful replay now opens in the dashboard.
- **Fixed:** indexed citation decoding uses the observations sent to that model request, before report
  hooks can append new evidence. Hook-generated labels cannot validate a guessed citation. The audit
  found no affected citations in 4,615 inspected stored reports; no saved reports were rewritten.
- **Fixed tests:** historical policy records are checked by their original identities, and the cancelled
  protocol's approval rehearsal is isolated from its later cancellation. The original runtime rejection
  checks remain covered; the cancelled experiment remains cancelled.
- The new status display independently reads development evidence, matching unseen checks and the actual
  campaign active-policy pointer. Saved qualifications match Phase 17 **1/9**, Phase 23 **3/30** and Phase 28
  **9/49**, with zero mismatches across 88 attempts. It never promotes or activates a policy.
- All **37 historical result files** matched the consolidation's pre-change hashes, including Claude's
  already-corrected Phase 28 report. The scorer and Actor system prompt remain unchanged. The later
  report-finalization fix intentionally changes the interpreter under a new runtime identity.
- The prospective runner/partition passed **102 offline checks**. At completion of that live experiment,
  all 98 application files matched the pre-run source checkpoint; it did not change the runtime. All 318 worlds and
  saved readbacks were reconstructed; fresh exact-ID Weave reads verified three selected episodes.
- **Fixed offline under a new runtime:** a rejected generated policy used `defer_unresolved` then
  tried a business read in its report hook, preventing submission of a real answer. Finalization now
  skips closed business I/O while preserving applicable receipt guards and charged policy steps;
  other hook-budget failures get precise diagnostics. The three historical failures remain unchanged.
  The selected live repair does not use this sequence. This fix does not prove live completion gain.

Preserve original reports, failed trials and evaluation partitions. Do not weaken C1–C8, qualifying
thresholds or gates, substitute a corrected model answer, or present a replay as fresh execution.

## Next recommended work

Claude's original program ends at **Phase 31: the write-up and event demo**. That research-program
milestone is complete; the broader product goal is not. No paid run is active.

The core path, local durability and reviewed two-agent setup have now been implemented and checked.
Dashboard bundle import with a review before a separate, confirmed fresh execution is now implemented
and reviewed (September 28); it awaits the PM commit and the owner's bounded real-model validation, which
must use the current runtime, fresh registrations and the restored fixture (see *Current runtime*). Repair effectiveness, a separately versioned second
task and clean-machine/hosted deployment acceptance remain separate open milestones. A new live native
check should be prospectively declared, bounded and interpreted honestly; do not reuse a closed partition.

The owner accepted the following broader direction; revise it using actual evidence:

1. **Complete the core workflow.** Trace connecting an agent/task, fault discovery, reproduction,
   diagnosis, repair, challenge, acceptance/rejection and saved regression as one usable flow.
   Locate missing links and distinguish working modules from verified end-to-end behavior.
2. **Improve repair quality.** Investigate what information and actions the Mechanic needs, then
   compare repairs on fresh cases with honest completion, violation and fault-exposure accounting.
3. **Make it usable by another developer.** Improve agent setup, campaign history/progress,
   before/after evidence, export and rerun. Verify whether routine use still requires research scripts
   or manually pasted identifiers before deciding what to build.
4. **Prove reuse beyond the shop.** Complete independent-agent integration and choose a second
   meaningful workflow with its own environment and rules, reusing the same testing engine.
5. **Make operation dependable.** Verify persistence, restart, cancellation, isolation/concurrency,
   clean setup on another machine and security appropriate to the intended deployment.

Start by auditing and completing the core workflow, not by automatically starting another narrow
notification experiment. A write-attempt record remains one possible intervention; the
[notification review](docs/part2/NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md) explains why simply
reintroducing the old v2/v3 summaries is not justified. Change the sequence when a concrete dependency
or new evidence warrants it, and explain why.

FaultLab can work correctly while rejecting an ineffective repair. Product reliability, the tested
agent's mistakes and learned-repair effectiveness are separate outcomes. Do not force the agent to
call a tool just to expose a scheduled fault, weaken the referee to create acceptance, or count an
untriggered fault as a passing fault test. Handwritten reference policies can check plumbing when
clearly labeled; they are not learned-repair evidence. Keep closed evaluations and their verdicts intact.

The next chat should take ownership of implementation and verification after a concise evidence-based
plan. Keep this page current; use the [saved starting prompt](NEW_CHAT_PROMPT.md) to continue.
