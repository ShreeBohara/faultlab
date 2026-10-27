# Plan revision (2026-10-24): running FaultLab on Claude Code and $200 a month

Written for the owner after the October 11 to 12 runs (phases A to C of the Claude Actor screen, piece D
of the credit plan) and a full re-read of the October 10 plan (`FaultLab_Plan_2026-10-10/`, seven stages,
62 phases, six gates). The question asked: we cannot spend $500 of API credit, we have Claude Code and at
most $200 of API credit a month, and we cannot rely on outside sources; how should the plan change, and how
does it become more robust and more scalable? Every number below comes from the lab's own ledgers and the
published read-outs; estimates are marked as such.

## 1. First, the correction: nothing in the plan costs $500

The $507 that stopped the Fable study on October 12 was a **hold**, not a bill. Before a campaign starts,
the legacy lab sets aside the worst case it could ever spend: 1,064 protected calls (for audit batches a
screen never runs) plus the study's 144 calls, each priced at the maximum prompt (32,000 tokens in, 2,000
out). At Fable's prices that is $0.42 a call and $507 in total. Measured spend is a different number, and it
is small.

| What | Measured | Source |
|---|---|---|
| One live episode, DeepSeek V3.1 | $0.009 | phases A+B, 162 episodes |
| One live episode, Claude Haiku 5.5 | $0.003 | phases A+B |
| One live episode, Claude Sonnet 5.5 | $0.053 | phases A+B |
| One live episode, Claude Opus 5.5 | $0.090 | phases A+B |
| One live episode, Claude Fable 5.1 | about $0.22 | estimate: 2.5 x Opus by price, never measured |
| One baseline study (18 live episodes) | $0.05 Haiku, $0.95 Sonnet, $1.65 Opus, about $4 Fable | phase B per-study costs |
| One completion study that ends at its controls (6 Sonnet trials) | $0.27 to $0.31 | piece D, five studies |
| Everything paid on October 11 and 12 (72 + 540 + 18 + 30 episodes) | $23.41 | spend ledger, October |
| The whole credit plan as declared (C, D, E) | about $45 at measured rates | this page |

The lab's holds run about eight times its measured spend (Opus: $13.30 held, $1.61 measured per study),
and the legacy campaign adds the 1,064 protected calls on top. So two different things were wrong in
October, and neither was money: a hold ceiling of $500 in the lab's settings that Fable alone exceeds, and
a monthly cap that counts holds, not dollars ($400 of holds is roughly $50 of spend). Both are fixed by
design changes below, not by a bigger budget.

The honest budget statement: **$200 a month of API credit covers every paid phase of this plan at its
measured rates**, including Bench v1, as long as the expensive models (Opus, Fable) are reserved for the
declared public numbers and everything else runs cheaper. The plan's spend caps ($5,000 for Bench v1,
$7,400 for the research track) were envelopes, not estimates; at measured rates Bench v1 is about $470.

## 2. The three channels we actually have

| Channel | What it costs | What it is for | Limits and conditions |
|---|---|---|---|
| **Claude API** (`anthropic:*`), OpenAI-compatible layer | per token; $200 a month | the declared, published numbers: screens, bench cells, certification runs; anything whose identity must be API-exact | the owner's console spend limit must match the declared monthly budget (October 11 stopped on a $20 console limit); no prompt caching on the compatibility layer |
| **Claude Code subscription** (`claude -p`, the Claude Agent SDK) | no marginal cost | development and iteration of prompts, study types and adapters; the Claude Agent SDK adapter under test; the Mechanic as a repair assistant | first-party tools only (the CLI or the Agent SDK; third-party harnesses are not permitted; verify the current terms before relying on it); 5-hour and weekly rate windows; the standalone CLI on this Mac is not logged in yet (`claude auth`); outputs carry Claude Code's own framing unless `--system-prompt` and `--tools ""` are used, so the identity differs from an API run and must be recorded as its own provider |
| **Local models** (Ollama at `localhost:11434`, OpenAI-compatible; the lab's `custom` provider already allows http to this machine) | electricity | CI and nightly smoke, the control arm during development, fault-injection tests that need any live model; never public numbers | an 8B model on an 18 GB M3 Pro is slow and weak at tool use; price entry of 0 needs one offline test of `require_live` |
| W&B Inference (DeepSeek control) | sponsor credits, ended October 12 | the open-model control arm | outside dependence; replace by DeepSeek through OpenRouter (about the same $0.009 per episode, paid from the $200) or by a local model for development |

Probe on 2026-10-24: `claude -p ... --output-format json --tools "" --max-turns 1 --bare` runs from a
shell on this Mac and reports `usage` and `total_cost_usd` per call, which is what the lab's shadow
pricing needs; it answered "Not logged in", so the subscription channel needs one `claude auth login` (or
a long-lived token) by the owner before it can be used.

## 3. The budget model that replaces "$400 of holds"

1. **Dollars, not holds, in the monthly ledger.** `backend/app/providers/spend.py` gates admission on
   the month's sum of per-call bounds. Change it to gate on settled spend plus the bounds of calls still
   open (reserve at the bound, settle at the measured cost, count only unsettled rows at their bound).
   The cap then means money: `FAULTLAB_MONTHLY_DOLLAR_CAP=200` is the owner's $200. One small, tested
   change; both figures stay in the summary. (Today's ledger: $197 of holds, $23.41 settled.)
2. **Campaign holds sized to the run.** The 1,064 protected calls exist for the research loop's audit
   batches. Screens never run them. In the v2 lab (`faultlab run`) a plan carries its own bound and the
   scheduler admits on measured plus reserved plus the plan's bound; there is no protected hold and the
   Fable problem does not exist. Move the screens to v2 as soon as the model Actor adapter has had one
   live smoke; in the legacy lab, keep the raised ceiling (500 to 1,000) only as a bookkeeping bound, or
   discard it if the screens move first.
3. **Shadow pricing for subscription runs.** A run through Claude Code records the API-equivalent cost the
   CLI reports as its measured cost, flagged `channel: subscription`, so declarations, caps and ledgers
   keep working and no run is ever "free" in the books. Public numbers state the channel.
4. **A monthly plan, declared once.** One declaration per calendar month listing the planned paid runs,
   their channel, their measured estimate and their hold; the per-run declarations extend it. Example for
   a bench month: Haiku and Sonnet cells on the API ($40), the open-model arm through OpenRouter ($30),
   Opus cells ($90), reserve $40. Fable is a headline screen, once, at about $40, when a month allows it.
5. **Pre-flight before any declaration.** A `--dry-run` in the driver that creates no campaign and prints
   every hold against every cap, ceiling and the month's remaining room, plus the provider's spend limit
   if the console exposes it. It would have caught both October faults before launch.

## 4. Where the money goes, phase by phase

Legend for the channel column: **offline** (no model), **local** (Ollama), **sub** (Claude Code
subscription), **API** (the $200), **W&B/router** (open-model arm). Costs are at the measured rates
above; "est." where nothing was measured.

### Stage 0, Foundation. Done except 0.7.

| Phase | Status | Channel | Change |
|---|---|---|---|
| 0.1 to 0.4, 0.6, 0.8 | done | offline | none |
| 0.5 Provider independence | done, with two defects found in October | API | add the `claude-code` provider (request profile: CLI or Agent SDK, tools off, one turn, system prompt replaced), the ledger change of section 3.1, the dry-run of 3.5, and a verified 0-rate entry for local models |
| 0.7 Chapter-closing replay run | skipped | sub | if ever run, run it on the subscription: it is a replay, not a public number |

### Stage 1, Core v2. Six of twelve phases have first cuts.

| Phase | Status | Channel | Change |
|---|---|---|---|
| 1.1, 1.2 | done | offline | none |
| 1.3 Task-pack interface | first cut | offline | finish moving the orders checks out of the legacy referee |
| 1.4 effectsafe extraction | alpha | offline | none |
| 1.5 Worker, scheduler, store | first cut | offline | the HTTP transport; keep the plan-level dollar bound as the only hold |
| 1.6 Adapters | first cut (reference, model-actor) | sub for the first live smoke | add a `claude-code` provider to `model-actor`, then a **Claude Agent SDK adapter** (the pack's tools as an MCP server through the effectsafe proxy; Claude Code drives them). Both run on the subscription |
| 1.7 CLI, pytest plugin, CI action | first cut | offline, local for a nightly live smoke | the CI action stays credential-free; a nightly job on a local model proves the live path without spend |
| 1.8 Replay | part | offline | recorded-input replay is the zero-cost regression path for every incident; finish the fresh-replication recipe |
| 1.9 Oracle | part | API (Haiku) for the model-extraction set | the 200-report labelled set is a one-time $2 job on Haiku; calibration by fault phase offline |
| 1.10 Test triage | part | offline | the core suite under five minutes is what makes every other change safe |
| 1.11 Exporters, Weave optional | not started, **now urgent** | offline | every October run's evidence was rejected by a project-name mismatch and the completion study hard-requires remote verification; make local evidence the authority (it already is for the screens) and remote verification a flag, exactly as the plan says |
| 1.12 Docs v2 | not started | offline | include the channel model and the budget rules of this page |

### Stage 2, Packs, adapters, Bench v1. Not started.

| Phase | Channel | Cost at measured rates | Change |
|---|---|---|---|
| 2.1 to 2.5 packs and fault families | offline, local for live smoke | $0 | none; the mutants and planted scenarios are offline tests |
| 2.6 Framework adapters | sub for Claude Agent SDK; local or Haiku for the others' conformance | under $10 | the Claude Agent SDK adapter doubles as the subscription channel's proof; every other framework's conformance run uses a local model or Haiku |
| 2.7 Bench harness | offline (scripted model double) | $0 | add channel, shadow cost and rate-window bookkeeping to the cost accounting |
| 2.8 Bench v1 execution | API for Haiku, Sonnet, Opus; router for the open arm | about $470 for 12,000 bare-arm trials (Haiku $9, Sonnet $160, Opus $270, open $27; plan cap was $5,000) | run it over two or three months inside $200; or run the Claude cells on the subscription if the terms allow and label the channel; Fable as one extra headline column adds about $660 and is optional |
| 2.9, 2.10 Report #1, Paper 1 | offline (writing) | $0 (plan caps $500 were for reruns) | reruns are replays first |
| 2.11, 2.12 site, launch | offline | $0 | none |

### Stage 3, effectsafe 0.1. Not started.

| Phase | Channel | Cost | Change |
|---|---|---|---|
| 3.1, 3.2, 3.7, 3.8 | offline | $0 | none |
| 3.3 Integrations (payments pack under F1/F5, zero duplicates) | local or Haiku | under $10 (plan cap $100) | the Claude Agent SDK integration (`PreToolUse`/`PostToolUse` hooks) is also the subscription channel |
| 3.4 Twin fidelity against Stripe test mode | none (Stripe test mode is free) | $0 | this is the one outside dependence worth keeping: it is the product's proof |
| 3.5 Certification pipeline, eight profiles | API, Sonnet | about $5 to $10 per certificate, under $100 total (plan cap $500) | declare the eight as one monthly plan |
| 3.6 Public reproductions fixed | local or Haiku, Sonnet for the published runs | under $20 | none |

### Stage 4, Research track. Not started; this is where the October lessons matter most.

| Phase | Channel | Cost | Change |
|---|---|---|---|
| 4.1 Minimization under a stochastic oracle | local or Haiku for the 50 planted recipes; Sonnet for the 20 real failures | planted: under $20; real: about $100 to $300 depending on trials per failure | SPRT needs many cheap trials: develop on local models, confirm on Haiku, publish on Sonnet |
| 4.2 Service-boundary contract | offline (TLA+ or P) plus the twin and Stripe test mode | about $0 | none |
| 4.3 Certification engine | Sonnet, k from the power analysis | each certification about $5 to $15 at Sonnet rates | the power analysis sets k before any spend; one month's plan |
| 4.4 Failure-class entropy | from bench data | $0 | none |
| 4.5 Repair assistance, controlled | Actor Sonnet on the API; Mechanic as **Claude Code** (sub) or Opus (API) | about $5 to $10 per full study at measured rates; fifty studies about $400 over two or three months | redesign first (section 6): the completion study's manifests only express completion gaps, which Claude Actors never show |
| 4.6, 4.7 Papers | offline | $0 | none |

### Stages 5 to 7. Unchanged; they cost people, not tokens.

The Anthropic startup credits (5.2) are an outside source; the plan works without them.

## 5. Robustness: eleven changes, each from a failure we actually had

1. **Dry-run admission** before declaring (section 3.5). October 12: Fable's hold exceeded the ceiling;
   the monthly cap could not have held nine rounds. Both were arithmetic available in advance.
2. **Dollars, not holds, in the monthly cap** (section 3.1). The $400 cap meant about $50 of spend.
3. **Holds sized to the run** (section 3.2). Screens do not need audit reservations; v2 has none.
4. **Evidence verification must not depend on an outside service name.** `WANDB_PROJECT=faultlab`
   against a project called `Faultlab` rejected every October trace. Fix: verify the project name against
   the service at start-up, make remote verification optional (1.11), and never let a study hard-require
   it unless the declaration says so.
5. **Stop rules on the stop reason, not on the status word.** Phase B's loop ran two error studies
   because the driver labels a study stopped by the LAB_ERROR streak rule `INCOMPLETE`; piece D's first
   two studies would have become five. The loop must stop when `stopped_by_rule` is set or an error is
   recorded, whatever the status says.
6. **Publish only complete runs, and say so when they are not.** The wrap-up published a two-study
   phase C and would have published two failed piece D studies. Rule: the wrap-up publishes when the
   declared count is reached or a declared stop rule fired, labels anything else `partial`, and replaces a
   folder it republishes (`--delete`), keeping attempts aside under an `attempt-` prefix.
7. **Console limits are part of the declaration.** October 11 stopped on a $20 console spend limit nobody
   had looked at. The declaration records the console limit and the loop stops on the first 402 or
   insufficient-credit error (piece D's loop already greps for it; make it the driver's job).
8. **Declarations generated from the ledger, the driver digest and the commit**, not typed. The plan's
   own "$60 start" cap for piece D could never have been admitted ($260 hold). The generator pattern used
   for the amendments (`write_declaration_*.py`) becomes the standard.
9. **One tiny live smoke before any declared batch.** The completion path had only been offline-tested;
   $0.06 of live smoke would have found the evidence rejection a day earlier. Every new study type gets a
   one-trial live smoke on the cheapest channel before its declaration.
10. **The study must match the question.** Piece D asked about label-rule violations on the rejected
    upgrade (dev-5) and ran a study whose only manifests are completion gaps on transient failures. Rule:
    a declaration names the manifest and the gap it targets, and the dry-run checks that the control
    arm can fail that gap (phase B data per model and case is enough to know).
11. **Changes to safety bounds go through a reviewed commit by the owner, not an unattended session.**
    The Claude Code safety classifier blocked the ceiling change on October 12 even with approval in
    chat. That is the right default; plan such changes as pull requests the owner merges.

## 6. The research question that remains open, and how the channels answer it

Phases A and B established, with intervals, that Claude Actors complete the transient-failure case where
DeepSeek stops, and that their violations are label or citation slips on the rejected-upgrade case (Haiku
12 of 24 on dev-5 through C5; Sonnet 3 of 24; Opus 6 of 21 through C6). The lab loop cannot study a
Claude Mechanic repairing those slips because its completion study only triggers on a completion gap.

What the subscription channel makes cheap to build and test:

- **A violation-gap manifest** (dev-5 as the source case, the gap being "a C5 or C6 failure in at least
  two of three valid controls"), with the same frozen discipline as the completion study. Development
  iterations on the subscription; the declared run on the API at Sonnet rates (about $5 per study).
- **Claude Code as the Mechanic.** The Mechanic's job (read the minimized counterexample, propose an
  effectsafe rule) is agentic; the Claude Agent SDK, with the bundle as its working directory and no
  network, is a natural Mechanic and costs nothing marginal. Its proposals are certified by 4.3 against a
  concurrent no-rule control, exactly as the plan wants; the channel is recorded.
- **Claude Code as an Actor under test.** The Claude Agent SDK adapter of 2.6 puts the most widely used
  agent harness on the bench at zero marginal cost, with the pack's tools behind the effectsafe proxy.
  This is also the first real "framework" cell of Bench v1.

Piece E (Opus Actor on the completion study) is withdrawn: it would end at the controls stage five times
for $1.50 and answer nothing.

## 7. Scalability: what grows and what does not

- **Throughput is not the constraint; rate windows and review are.** A baseline study is about 80 calls
  and 5 to 12 minutes; the Mac ran 36 studies in a day. The API channel at $200 a month allows roughly
  2,000 Sonnet studies' worth of episodes or 200 Opus studies; the subscription channel is bounded by its
  5-hour and weekly windows, which suit development, not matrices.
- **Parallel runs.** Ports are configurable since September 29; several lab stacks can run on one Mac.
  The bench harness (2.7) should own the queue: one worker per channel, each channel's limits declared,
  cells pulled in a randomized block order so time-of-day effects spread across models (phase B's reason
  for round-robin).
- **Zero-cost regression.** Recorded-input replay (1.8) reruns every published incident without a model;
  the pytest plugin and the CI action stay credential-free; a nightly local-model smoke proves the live
  path. Paid calls are for new information only.
- **Repetition policy.** k = 5 fresh runs per cell with Wilson intervals, as the architecture says; the
  bench math above already assumes it. Fewer repetitions on expensive models are reported as such, never
  pooled silently.
- **Caching and batching.** Each episode's calls share a long prefix, so Anthropic's prompt caching would
  cut Claude input cost substantially, but it needs the native Anthropic SDK path (the OpenAI-compatible
  layer has none); worth doing when Opus or Fable spend becomes the constraint, not before. The batch API
  does not fit interactive turns.
- **Local models as a scaling valve.** Development, CI and the control arm during iteration run on
  Ollama; public numbers never do. The lab's `custom` provider already accepts a local http endpoint.

## 8. What this changes in the calendar, and the decisions needed

Stage 1 first (1.11 Weave optional, 1.10 test triage, 1.6 the `claude-code` provider and the Claude
Agent SDK adapter, 1.5 the HTTP transport), because every later paid phase gets cheaper and safer
through them. Then Stage 2 on the budget model above, then 4.5 redesigned. The gates stand; none of them
needs more money than $200 a month, and none should be weakened.

Decisions for the owner:

1. **Subscription channel:** log the standalone CLI in (`claude auth login`) and confirm Anthropic's
   current terms allow first-party programmatic use of the subscription for this work. Without that, the
   plan still holds on the API alone at about $200 a month.
2. **The uncommitted ceiling change** (500 to 1,000 in `backend/app/config.py` and the campaign model, with
   its test and docs line): commit it as a reviewed change if the Fable screen should run in the legacy
   lab in November (about $40 measured), or discard it and run Fable later on v2, where no such hold exists.
3. **The ledger change** (section 3.1) and the dry-run (3.5): approve as the next two small, tested
   commits; they make `FAULTLAB_MONTHLY_DOLLAR_CAP=200` mean exactly the owner's budget.
4. **`.env`:** set `WANDB_PROJECT=Faultlab` now; it is one line and every evidence row depends on it until
   1.11 lands.
5. **The open-model arm:** DeepSeek through OpenRouter for public numbers (about $0.009 an episode), local
   models for development. No sponsor credits are assumed anywhere in this plan.

## 9. What was completed, for the record

Stage 0: 0.1 to 0.8 done (0.7 skipped by choice). Stage 1: 1.1, 1.2 done; 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10
have first cuts; 1.4 is at alpha; 1.11 and 1.12 not started. Stages 2 to 7: not started. Credit plan:
C blocked at admission (one valid control study; the two-study publish `9af2ba1` stays as the record), D
complete (five studies, all NO_CHANGE at controls, $1.48; published `0de4133`, `b45ad73`), E withdrawn.
Write-ups and ledger lines are on `main` (`856ca5c`). The project ledger stands at $1,550.91 in holds; the
October bill was $23.41.

## Addendum (2026-10-25): the subscription channel exists and ran a study

Done after this page was written, with the owner's go-ahead: the monthly ledger gates on committed dollars
(`ba82842`), the driver has `--dry-run` (`82da7fd`), the `claude-code` provider is in (`fc9dc45`,
"Claude Code: the subscription channel" in `docs/providers.md`), `.env` names the real W&B project, and
the owner logged the standalone CLI in. The first declared study on the channel
(`~/FaultLab_Runs/2026-10-25/claude-code-channel-smoke/`, Haiku, the frozen baseline study): COMPLETED in
236 seconds, 15 completed and 3 violations out of 18 (all dev-5 through C5, as phase B found for Haiku on the
API), every episode's evidence `weave_verified`, 90 calls, $0 of money, $0.056 API-equivalent. The channel
is ready for development runs and the Claude Agent SDK adapter; public numbers stay on the API.

## Addendum (2026-10-25, later): Claude Code is on the bench

The Claude Agent SDK adapter (`claude-agent`, Stage 2.6's first harness cell, commits `94c129f` and `17edfdf`)
ran the orders pack's six scenarios with Haiku 5.5 as Claude Code on the subscription: five completed clean,
the rejected-upgrade case the familiar C5 slip, 55 seconds and $0.013 equivalent for the batch. The channel and
the adapter are what section 6 asked for; the Mechanic-as-Claude-Code and the violation-gap manifest remain.

## Addendum (2026-10-25, evening): the violation-gap manifest of section 6 is withdrawn

Reading the code behind section 6's proposal showed it cannot produce a repair. The completion study's
gates are completion counts, which dev-5 (expected `CORRECTLY_REJECTED`) can never satisfy, and, the
real blocker, neither the legacy policy DSL nor the effectsafe rule language has a step that can act on
a report label; the dev-5 violation is a label slip (`NOT_STARTED` where the convention is
`NOT_REQUIRED`, every belief true). A Mechanic shown that counterexample has no vocabulary that repairs
it, so the study would end `NO_CHANGE` by construction. The design that can answer the question, one
report-gate step (`require_label`) in effectsafe plus a v2 repair study with Claude Code as the
Mechanic, its pre-registered read-outs, cost and the decisions needed, is in
[VIOLATION_GAP_DESIGN_2026-10-25.md](VIOLATION_GAP_DESIGN_2026-10-25.md). Stage 4.5's "redesign first"
is that note.

## Addendum (2026-10-26, night): Stage 4.5 ran its first repair, for $0

Option B of [VIOLATION_GAP_DESIGN_2026-10-25.md](VIOLATION_GAP_DESIGN_2026-10-25.md) is built and on main
(9580bc0, 370a1e2, 6e179d0): `require_label` in effectsafe, the report gate in both v2 adapters, the repair
study and the Claude Code Mechanic. Three declared smokes on the subscription, all at $0 money and under
$0.14 API-equivalent each: the first showed the Mechanic needs the report's label vocabulary, the second
that with it Sonnet proposes the designed repair at the first attempt, the third ended **REPAIRED**, the
loop of 4.5 closed once with the Mechanic's rule certified against the five other public cases. Six
amendments to the study's own rules are recorded with their reasons in the design note's build record. The
design is frozen at 6e179d0; a confirmatory run with six pairs and the declared API pilot are the owner's
next decisions. Nothing in `backend/app`, no check, gate or threshold changed.
