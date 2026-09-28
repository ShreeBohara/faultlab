# Original learning workflow: verified result

The actual application workflow now has an offline reference exercise of acceptance,
rejection, interruption, restart and fresh exported-bundle execution. The subsequent
single declared live campaign ended normally **NO_CHANGE**. It completed seven tasks
without a qualifying violation, so it correctly produced no repair or promotion.
These results establish specific workflow behavior; they do not establish a generated
accepted policy or unseen-case reliability.

The [prospective declaration](PRODUCT_LOOP_RUN_2026-09-27.md) selected the original
`mode=learn` API path, not the separate completion-study scripts. Runtime was frozen at
`60f27623bdc461e3542a0118d381725b74cf6343169d07337ec77fed12e23a7e`, configuration at
`18e5efb1d72ccef51aa564586815aa34fb09acd6806be35239934d2c3f92ac8a`.
Campaign: `campaign-c701e850410747d8a832f5f68258b245`.

## What the reference exercise establishes

Scripted model responses drove the real Actor parser, broker, simulator, Referee,
reproduction, reduction, diagnosis, Mechanic parser, challenge, promotion and export.
The accepted reference passed source checks, four challenge schedules with three pairs
each, and 36 promotion worlds. Its active pointer survived restart, and its exported
bundle executed in three fresh worlds. The rejected reference failed its source check;
the interrupted reference retained the pending upgrade's eventual effect and did not replay it.

There were 121 retained worlds across the final accepted/rejected/interrupted exercise.
An independent reconstruction compared 2,094 facts without mismatch, plus 27 provenance
checks on the three exported-bundle worlds. The policy is explicitly manual and the
episodes are `offline_fixture`/`local_only`; none is evidence of model learning.
Earlier fixture setup failures are preserved separately. No inference was used.

Preparation uncovered an actual FaultLab budget defect: an optional blind transport retry
could spend capacity reserved for a later mandatory comparison turn. Retries now use
unreserved campaign headroom. The fixed limits and later gate requirements did not change.
The pre-live full backend suite passed **2,019 tests**, with 180 existing skips and one
existing dependency warning. Three newly added workflow tests passed separately.

## What happened in the live campaign

| Measure | Observed result |
|---|---:|
| Explorer selections / Actor requests | 8 / 31 |
| Worlds / completed tasks | 7 / 7 |
| Fixed-check violations / lab errors | 0 / 0 |
| Fully / partly / never triggered recipes | 4 / 1 / 2 |
| Triggered fault primitives | 5 / 8 |
| Duplicate schedules declined without a world | 1 |
| Verified remote episode evidence | 7 / 7 |
| Candidate / promotion / active learned policy | None / none / none |

The untriggered status-read faults were an Explorer planning limitation. The Actor already
had a terminal success receipt and correctly avoided unnecessary polling. One composite
also included a notification fault, which did trigger. FaultLab preserved those distinctions
and declined an exact duplicate even though its seed differed. It did not force a tool call,
reroll an answer or count missing exposure as a passing fault test. `policy-v0` remains active.

Independent audit passed **188 comparisons**, including all seven raw worlds and original
reports, 56 C1–C8 checks and 31 exact Actor request/message hashes. Thirty-four fresh
read-only Weave readbacks matched seven roots and 27 children exactly. Manual dashboard
checks opened original reports, actual effects, all checks, the duplicate selection and
the saved baseline pointer; reloading left the same 39 requests.

## Accounting and preservation

The 39 requests used 162,287 input tokens and 2,388 output tokens. At the declared per-model
rates, token pricing is **$0.15324862**. The retained conservative charge is **$1.04662**, carried
as **$1.05** on top of $855.91, for **$856.96 total**. Actual billed cost was not supplied by
the provider. Telemetry reads and subsequent durability work added no inference requests.

All eight closed live databases and the historical main database retained their hashes and
modification times through independent audit. No historical verdict, closed report or active
pointer was changed. No GitHub push occurred. The live store is for saved inspection only;
new runtime work must use a separate store and cannot resume this closed campaign.

Evidence: `artifacts/product-loop-2026-09-27/`, including `live-export.json`, `live-budget.json`,
`manual-browser-verification.json`, `world-review/live-findings.md`,
`world-review/live-independent-audit.json`, and `world-review/live-remote-readback.json`.
The external evidence/source backup is recorded in `final-checkpoint.json` there.

The next product work addresses demonstrated ownership, restart and read-isolation defects.
The live run does not justify repeating discovery merely to obtain an accepted policy.
