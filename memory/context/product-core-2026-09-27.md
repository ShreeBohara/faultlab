# Product core implementation — September 27, 2026

Current status lives in [CURRENT_STATUS.md](../../CURRENT_STATUS.md). This new note follows
the earlier product-continuation handoff. The owner authorized taking ownership of architecture,
implementation and manual/test verification, with generous time/resources and no GitHub push.

## Findings and implemented direction

The core source trace is in [the product review](../../docs/PRODUCT_CORE_REVIEW_2026-09-27.md).
The original learning workflow is connected in code; completion studies are a separate path.
Do not call a successful reference fixture a generated accepted policy. Zero generated policies
have been accepted through original promotion, and all historical active pointers remain baseline.

New fixes target evidence integrity and normal operation before buying more model experiments:

- A candidate violation in the opposite arm of an infrastructure-failed pair could disappear
  from source/challenge/promotion gating after a clean retry. Gates now inspect retained scored
  candidate attempts. Incomplete/lab-error observations do not become scored agent failures.
- A transport attempt charged before reaching the simulator could desynchronize ticks and
  falsely score a truthful completed report as C5/C6/C8. The runner freezes world admission first,
  checks actual ticks/attempt counts/identities, and preserves the report/effects/charges while
  classifying inconsistent execution LAB_ERROR. The original checks are unchanged.
- New heldout plans need an explicit integrity boundary so legacy research scoring does not
  interpret invalid-world checks as harm. Historical plans/predicates/results retain their meaning.
- Passive API reads and JSON encoding move to worker threads. This avoids blocking the execution
  event loop, but SQLite's shared lock and multiple backend writers remain limits.
- Campaign history and saved regression execution history use bounded cursors, explicit refresh
  and normal selectors. Reading history never starts work. Pasted IDs remain a fallback.
- Stop applies only to the campaign owning active work, including auxiliary work on terminal
  campaigns. Inactive saved runs are unchanged. Readiness separates simulator/live configuration
  from provider account access, and makes zero provider calls.
- Evaluation progress, queued request state and regression interruption survive exceptions or
  cancellation. Owned-resource cleanup releases admission even if close fails. Restart preserves
  attempted effects and charged calls; unfinished work is never automatically replayed.

## Evidence and safeguards

Work/evidence directory: `artifacts/product-core-2026-09-27/`. Original snapshot `before.json`:
runtime `b9410f5e77f2b98e6a621ee5adabc20c7ac65ea042f8a9d7049dedadaec7d719`, backup branch
`9ef1d987ada80b5830a570e18e5c1a1dad512047`, main `cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe`,
logical index SHA-256 `34a77879bf2b787ace8cfc9cccf85972552028f4c617db4ad216072b16e9062f`.

Historical read-only audit: 241,000 records, 142,417 events; original-loop evaluation batches
contained 21 scored candidate violations, none outside trial pairs. The retry defect is latent
in this store, not evidence of an invalid historical acceptance. No generated ACCEPTED policy
exists and all 294 active pointers are baseline. Closed results were not rewritten.

Manual clock audit uses a handwritten reference and real localhost TCP: healthy; one refused
connection; and genuine F1 response loss after commit. The latter remains valid. The refused
connection changed from false VIOLATION to LAB_ERROR, retaining one actual upgrade and one actual
notification. This is lab correctness evidence, not task completion gain.

Manual dashboard uses credential-free isolated services and worlds. A selected historical
regression was copied read-only into that isolated store solely for navigation checks; that copy
is not new execution evidence. The normal historical database was never served by these processes.

No provider calls or new charges. Carried historical accounting remains **$855.91**; actual balance
unknown. No push, secret edit, reset, clean or checkout. Final source checkpoint/runtime/full-suite
results are recorded in CURRENT_STATUS.md and the product review. The frozen full backend suite passed: 2,010 tests, 180 existing skips, zero failures, one existing dependency warning in 714.97 seconds.

## Current frozen implementation and manual evidence

New runtime: `58cd13b6f966d5b1c789fde7de9ca4bbdf744b2335bca25d9f3930e57e14f357`.
Algorithm: `0833915fb8daba5ec4713a79583049afbdf80fcaa9ee3d46f0a8156bb95bfe1b`.
Contract remains `faultlab/v1`, trace contract 2. New-plan integrity marker is
`faultlab-world-integrity/v1`. Legacy `harmful`, `assess_heldout` and `assess_heldout_v2`
function bodies remain byte-identical. New guarded scans fail closed to INCOMPLETE if unreadable,
keeping the legacy assessment diagnostically. No historical assessment is reinterpreted.

Final frontend: 192 tests, build and six browser checks passed, one opt-in server skip. Focused
heldout/world: 104 passed; lifecycle/gates: 69 passed. These overlap the full backend suite.
The two intermediate heldout invocations overlapped source edits and stopped on source fingerprint
invalidation; they are not agent failures or final validation. The clean focused run passed after freeze.

The real localhost dashboard at its narrow native viewport created/started
`campaign-f06692f76bb64ba9b0f49fdef2929849` under the exact final runtime. Episode
`episode-d7e38b38813844cfba44cc9fb2159132`, world
`world-8b12df68660e4af58d66f427364127e6`: one upgrade, one notification, three admitted HTTP attempts,
decision tick 3/horizon 8, all eight checks, unchanged baseline, zero model calls. Direct SQLite world
reconstruction matches the original report. This is handwritten reference smoke, not learned repair.

Saved regression navigation reopened the copied historical execution
`execution-dcf7936ab295477fb7588f38584f8bbe` via a five-row selector and opened its original trial.
Three trials/24 calls displayed are historical. Browsing made no calls, new worlds or executions.
All 25 copied payload entries remained byte-identical. Evidence: `manual-final-verification.json`
and `manual-final-run.png`; the original main store was never served. Both isolated services and
Vite are stopped; the temporary tab is closed. Ports 8000/8001/5173 are free.

## Next architectural decisions

Complete a declared original-loop acceptance exercise with fresh evidence; investigate why existing
source qualifications reject candidates before allocating a paid run. Useful repair acceptance,
reserved-case validation, and accepted-repair transfer remain unestablished. Keep evidence partitions
and runtime claims separate. A reference/scripted positive gate test proves plumbing only.

The current local product still assumes a single backend writer. Moving readers to a threadpool does
not isolate SQLite locks or CPU contention. Startup scans still scale with history. A durable job/admission
record across processes, dedicated evidence-read boundary and verified non-cloud data migration deserve
review before shared hosting. Selector-search requests still need durable initial QUEUED status.
Second-task onboarding needs explicit tool and referee contracts; changing task text does not provide it.

Final checkpoint is recorded in `artifacts/product-core-2026-09-27/final-checkpoint.json` and
a verified external copy at `/Users/shree/FaultLab_Backups/2026-09-27/product-core/`. Preserve the
real main/index; use the existing temporary-index helper and explicit changed-file list only.

The complete backend invocation exited 0; result/log are `full-backend-result.json` and
`full-backend.log` in the evidence directory. The final runtime fingerprint matches the fresh UI
campaign's frozen configuration. All 31 historical result documents, the 901,308,416-byte main store
hash, main commit and logical index remain unchanged. `spending.json` records the $0 increment;
no extra skip or historical-result change was used to pass verification. The task completed a core
reliability increment, not the broader product milestones listed above.
