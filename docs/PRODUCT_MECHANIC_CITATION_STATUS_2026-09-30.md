# Native citation status in Mechanic requests (September 30, 2026)

**Status: built offline at $0 (builder), reviewed at $0 by two reviewers (integrity, product), and fixed at $0
(fixer, section 8). Not yet committed. Not run live.** Runtime after the fixer: `95042e4d9a67c739387a3841152bd7c23448f89cd5271ca32806552d6f3fc36c`
(algorithm `4e5a8f90…`); the builder's `c4195af1…` is superseded.

Protocol id: `faultlab-mechanic-evidence/v2-native-citation-status` (plan field `mechanic_evidence`).
Code: `backend/app/lab/citation_status.py` (new), the learning loop (`learning.py`, three short additions), plan
freezing and the Start check (`run_plans.py`), and the dashboard's saved plan and Learn setup form
(`frontend/src/loopLimits.ts`, `runPlans.ts`, `components/LoopLimits.tsx`, `CampaignPlan.tsx`, `RunSetup.tsx`).
Evidence: `artifacts/product-mechanic-citations-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`,
`fixer/`).

## 1. Why

In live runs v2d and v2e ([write-up](PRODUCT_NATIVE_V2_RUN_2026-09-29.md), last two sections) the diagnosis Mechanic read
a native adapter v2.1 source (dev-5: the agent confirms after a rejected upgrade, C3 and C5). Both times it proposed
CONTRACT_EVIDENCE_GAP: "the actor's report cites evidence labels that were never shown to it".

That was false both times. In all 8 diagnosed episodes (4 per run):

- every cited label was one the agent had been shown;
- every cited label was decoded;
- every decoded ID was a delivered observation.

The adapter records exactly this for every report (the `report_submitted` event's `cited_evidence_tokens`,
`labels_shown_to_agent`, `cited_tokens_not_decoded` and decoded IDs). The Mechanic never saw that record. It saw
only a memory text describing how labels work. In v2e it wrote that "the supplied observations do not establish whether
the report's evidence citations were valid under the shown-order label contract", and it requested no intervention
(INCONCLUSIVE, NO_CHANGE).

## 2. What the rule does

For a **new Learn plan whose agent is native adapter v2** (`smolagents-v2`), these requests get one separate block,
`native_citation_status`, when they carry evidence of at least one episode:

- every Mechanic diagnosis request;
- every Mechanic candidate request;
- every challenge Explorer request.

The block has **one plain sentence** saying what it means:

> Each row is what the native adapter recorded when that episode's agent submitted its report: cited is how many
> evidence tokens the report cited, decoded is how many of them were obs-N labels the agent had been shown and so were
> decoded to the evidence ID of an observation delivered to it, and undecoded lists every cited token that was not
> decoded and was kept exactly as written (all three are null when no complete native adapter v2.1 citation record was
> recorded for that episode).

Then one row per episode, in the order the request's evidence first lists it.

- **Source.** Each row is read only from that episode's last public `report_submitted` event (native adapter v2.1
  record). `decoded` counts a cited token only if it is a label the agent had been shown and the event's own label map
  gives the decoded ID recorded at that position.
- **Nothing from scoring.** No check, verdict, trial outcome or finding is read. The block says nothing about why any
  check failed, and a test checks that the sentence has no such words.
- **No guessing.** An episode without a complete v2.1 record (no report, a report without the v2.1 citation record, or
  an incomplete one) gets `null` in all three fields. The fixer reworded the sentence's last clause to say exactly this
  (review finding LOW-4); the builder's wording, "when no submitted report was recorded", was too narrow.

In a Mechanic request, the runtime contract's v2 memory text gets one added sentence:

> This request's native_citation_status block lists, for each episode in its evidence, the adapter's recorded outcome
> of that decoding: how many tokens the report cited, how many decoded to delivered evidence, and any token kept as
> written.

**The v2e diagnosis request, before and after** (rebuilt from a scratch copy of the saved store; IDs replaced by fake
ones; the full excerpt, with the fixer's wording, is `fixer/v2e-diagnosis-request-excerpt.json`):

```
before: (no native_citation_status key)
        runtime_contract.actor_contract.memory = "<the v2 memory text>"
after:  "native_citation_status": {
          "protocol": "faultlab-mechanic-evidence/v2-native-citation-status",
          "meaning": "Each row is what the native adapter recorded when ...",
          "episodes": [
            {"episode_id": "episode-FAKE01", "cited": 5, "decoded": 5, "undecoded": []},
            {"episode_id": "episode-FAKE02", "cited": 5, "decoded": 5, "undecoded": []},
            {"episode_id": "episode-FAKE03", "cited": 6, "decoded": 6, "undecoded": []},
            {"episode_id": "episode-FAKE04", "cited": 6, "decoded": 6, "undecoded": []}]}
        runtime_contract.actor_contract.memory = "<the v2 memory text> This request's native_citation_status block lists, ..."
```

Every other field of the request is byte-for-byte the same (checked).

## 3. Where it does not apply

- **Other plans are unchanged byte for byte:** a native adapter v2 plan saved before this rule, the reference Actor,
  native adapter v1, and every baseline or compare plan. Their plans have no `mechanic_evidence` key (no null key is
  added), and the learning loop never calls the citation code for them.
- **Discovery Explorer requests are unchanged**, and so are the discovery protocols.
- **Unchanged files:** gate code, `diagnosis.py` (including `summarize_evidence`, `trial_outcomes`, `runtime_contract`
  and the v2 memory text itself), `mechanic.py`, `explorer.py`, `challenge.py`, the referee, the simulator, the native
  adapters and their prompts. The block is added by two thin wrappers (`CitationStatusMechanic`,
  `CitationStatusExplorer`) and one call in the learning loop.
- **Start:** a plan that declares the rule must declare exactly the installed text; a plan for another agent or mode
  cannot declare it.

## 4. Size, and the bounded-context rule

The block is added **before** `faultlab-mechanic-context/v2-bounded` counts the request, so the request-size rule
always counts it. That rule compacts only the evidence tables, so the block is **never compacted**. Every episode keeps
its row, including episodes whose evidence rows the size rule omits.

**The block counts toward the 28,000-token target and is never omitted from it** (review finding LOW-2). So the block
can be the part that keeps a request from fitting: about 45 tokens per episode, with no stage that shortens it. The size
rule's own records do not say this. Its recorded reason when a request does not fit (`UNFIT_REASON`) and its
compaction statement list the parts it never omits without naming this block, because that wording belongs to the frozen
`faultlab-mechanic-context/v2-bounded` declaration (`11bf9e32…`), which this build does not change. For such a record,
read this section: a native v2 plan's `mechanic_evidence` declaration means the block was in the counted request. At
today's sizes this is far off: v2d's 34-episode request has 5,316 tokens of headroom at stage 3 (below). Nothing over
the limit is ever sent in any case (the Mechanic's own input check is unchanged).

Measured with the Mechanic's own admission count (frozen tokenizer), on scratch copies of the saved store. The fixer
re-measured with its reworded sentence (`fixer/rebuild-requests.json`; the builder's numbers, 10 tokens smaller per
request, are in `builder/rebuild-requests.json`):

| request | without the block | with the block | the block adds |
|---|---|---|---|
| v2e diagnosis (4 episodes) | 9,088 | 9,434 | 346 |
| v2d diagnosis (4 episodes) | 8,990 | 9,331 | 341 |
| v2d refused candidate request (34 episodes) | 33,223 | 34,806 | 1,583 |

- **The rebuilds are exact.** The local count adds 136 tokens of message framing to what the provider reported
  (8,952 and 8,854). That is the same difference as for v2d's first candidate request (14,304 against 14,168).
- **v2d's refused request still fits.** Stages 1–3 give 35,194 → 29,639 → **22,684**, which is within the 28,000-token
  target (5,316 tokens of headroom). Without the block they give 33,611 → 28,056 → 21,101. Both fit at stage 3.
- **The block survives compaction.** After compaction the block is identical, with 34 rows, 0 undecoded in each and
  every cited token decoded.
- **Challenge Explorer requests** (product review, builder's wording): v2d's three recorded challenge requests grow by
  368 tokens each, to at most 8,086, far under the Explorer's 32,000 limit; nothing compacts them. The fixer's wording
  adds about 10 tokens more per request.

## 5. Checks ($0, offline)

**Final `scripts/test.sh` results.**
- Builder (`builder/full-test-sh.log`, 10:52:37Z to 11:11:04Z): backend **2,970 passed, 180 skipped, 0 failed** (2 known
  warnings: starlette BlockingPortal, fork); frontend **356 passed**; build passed; browser **19 passed, 1 opt-in skip**.
- Fixer: one run after the fixer's last edit, `fixer/full-test-sh.log`. Its counts are that log's last lines (the
  pytest summary line, the vitest "Tests" line, and the Playwright "passed" and "skipped" lines); they are also in the
  fixer report. A document cannot quote a run that must come after its own last edit.

- `backend/tests/lab/test_citation_status.py` (17 tests from the builder, 1 from the fixer).
  - **Rows.** One row per episode, taken from the event only. An undecoded token is shown. No record gives nulls.
    Scoring records and private events change nothing. The last report is used, and events are read past one page.
  - **Placement.** Each request kind gets the block in evidence order. Only Mechanic requests get the pointer. A request
    without evidence is unchanged. Another memory text is refused.
  - **Wrappers.** A discovery request passes through as the same object.
  - **Plans.** Only a new native v2 Learn plan declares the rule. An older v2 plan keeps its bytes and starts. Another
    rule text is refused at Start. Other agents and modes cannot declare it.
  - **Learning loop.** Candidate and challenge requests carry the block and discovery requests do not. The diagnosis
    request carries it. The size rule counts it, for diagnosis and candidate requests alike. Without the rule, no
    citation code runs.
  - **Saved store** (skipped where it is absent):
    - a new native v2 plan made in a copy of the v2b store gets the block for v2e's diagnosis context, with 0 undecoded
      in every episode;
    - v2e's own older plan gets none;
    - the v2e and v2d diagnosis requests rebuild exactly, and all 8 diagnosed episodes decoded every citation;
    - v2d's refused candidate request with the block still fits after compaction and keeps every row.
- **Differential check** (`builder/differential_requests.py`). The backup tree's `learning.py` and this one ran
  the same scripted loops for plans without the rule: reference, native v1 and older native v2 contracts, for both
  candidate and challenge requests and for diagnosis requests. Every Mechanic request and Explorer context was byte
  for byte identical after ID normalisation. A positive control with the rule declared differs.
- **Dashboard.** The saved plan shows "Native citation status" for native v2 plans only. An older v2 plan reads "Not
  declared …". The Learn setup form shows it only when native adapter v2 is chosen. Real API responses pass the
  dashboard's validators (`builder/api-contract-check.log`).
- **Negative controls:** 17 mutations, each undoing one part (`builder/mutation-checks.log`); the fixer added 11 more,
  each undoing one fixer change (`fixer/mutation-checks.log`, all caught).

## 6. Misreading checker v2 (post-hoc)

`scripts/experiments/check_evidence_gap_misreading_v2.py` is a copy of the pre-registered checker. It has a broader
claim-phrase list and self-tests (`--self-test`, and `backend/tests/experiments/test_check_evidence_gap_misreading_v2.py`).

- **What changed (builder).** The v2 phrase list is a superset of v1's. It adds "never shown", "were not shown", "cannot
  be decoded", "not decodable", "undecoded" (not after "0", "no", "zero" or "without"), "not decoded" and "outside the
  shown labels". The rule and everything else are unchanged.
- **What the fixer changed (review finding MEDIUM-1; version string `faultlab-misreading-check/v2.1-claim-shapes-and-denials`,
  sha256 `11920882…`).** This block puts "undecoded" (a field name) and "not decoded" (its meaning sentence) into every
  native v2 Mechanic request. A Mechanic that reads the block correctly may echo those words or deny the claim. The
  builder's version read 17 of the reviews' 20 such wordings as claims (for example "undecoded: [] in all four episodes"
  and "no label was never shown"), and scored a contract-gap diagnosis that blamed something else MISREADING just for
  mentioning an empty undecoded list. Now:
  - bare "undecoded" and bare "not decoded" no longer count. Only claim shapes do: a nonzero amount or a verb of having
    or citing before "undecoded token(s), label(s) or citation(s)" ("1 undecoded token", "has undecoded tokens"), or a
    nonzero amount of tokens, labels or citations that "were not decoded";
  - a match does not count when its own clause, before the match, has a denial word (no, none, nothing, neither, nor,
    never, not, n't, zero, 0, without). A clause ends at . ; : ! ? , a dash, and the words and, but, yet, so, because,
    since, while, although, though, whereas and however;
  - each output lists every counted match with its sentence (`claim_matches`) and every match the denial rule set aside
    (`denied_matches`). **A CHECKED verdict counts only after a person confirms that each `claim_matches` sentence is a
    real claim**, because a phrase heuristic can still err both ways;
  - each output states `read_out_status` (`POST_HOC` or `PRE_REGISTERED`, required on the command line; the script
    refuses to run without it) and the script's own sha256 (review finding LOW-1: the builder's outputs carried the
    post-hoc label only in their file names).

  All 20 review wordings now score NOT_CHECKED, the block's own two sentences are not claims, and both live hypotheses
  still match exactly as before (`fixer/checker-v2/probe.json`, `product-echo-probe-rerun.json`, and 29 new pytest cases).
  **Known limit:** the unchanged v2 memory text itself says a token kept as written "is one the agent was never shown as
  a label". A Mechanic that repeats that rule matches "never shown" and counts; only the human check catches it.
- **v1 is untouched.** Its sha256 is `70c4eeda…`, both in `artifacts/product-native-v2b-2026-09-30/fixer/` and in the
  v2b, v2c, v2d and v2e run folders.

**Results. They are POST-HOC:** the phrase list was widened after reading these two hypotheses. They are not the
pre-registered read-out, which stays NOT_CHECKED for both runs. The fixer's version gives the same results, and the
fixer confirmed by reading them that each counted sentence is a real claim.

| run | v1 (pre-registered) | v2 (post-hoc; builder and fixer versions agree) | phrases matched | episodes read |
|---|---|---|---|---|
| v2d | NOT_CHECKED | **MISREADING** | "cannot be decoded", "never shown" | 4; 0 report IDs not recorded, 0 tokens not decoded |
| v2e | NOT_CHECKED | **MISREADING** | "never shown" | 4; 0 report IDs not recorded, 0 tokens not decoded |

Outputs: `fixer/checker-v2/v2d-misreading-check-v2.1-POSTHOC.json` and `v2e-…` (each says `"read_out_status":
"POST_HOC"` inside). The builder's `builder/checker-v2/` outputs came from its earlier version (sha256 `bd508a79…`) and
carry the label only in their names; they are kept unchanged as the builder's record.

## 7. What this does not show

- Nothing here ran live. Whether the Mechanic stops making this claim once it sees the block is unmeasured. It could
  still make the claim, or make a different mistake.
- The block removes the stated basis for one misreading. It does not tell the Mechanic what the real cause is. That
  cause is an untruthful report after a confirmation the agent should not have sent, and the block states no such
  thing, by design.
- The block costs about 45 tokens per episode. In a large candidate request that is about 5% of the request. For v2d it
  did not change the compaction stage (stage 3 both ways).
- Checker v2 is a phrase heuristic. A future hypothesis could word the same claim differently, and the denial rule can
  set aside a real claim that follows a denial word in the same clause. Hence the human check of every match.
- The undecoded-token case has been tested only with made-up data: all 99 native v2.1 reports in the `native-v2b` store
  have 0 undecoded tokens.
- No saved record shows that a given live Mechanic request carried the block. `mechanic.py` saves each Mechanic output
  and its token usage, not the request (this was so before this build); challenge selection records do save their
  context, block included. See the read-out steps below.

## 8. How the next live run should be read (fixer, from the reviews)

The rule is on for every new native v2 Learn plan, and older plans cannot start under the new runtime. So a live Learn
run has **no concurrent control** without the block, and comparing its diagnosis with v2d's and v2e's (two diagnoses, on
a different runtime) cannot show that the block caused any change. The project has been misled by such comparisons
before (Phase 8's claim, withdrawn under Phase 9's concurrent control). The declared read-out should therefore:

1. **Be descriptive only** (review finding LOW-3, product): did the diagnosis claim unshown or undecodable citations,
   and did it request the declared intervention? No causal claim about the block.
2. **First confirm the block was in the requests** (LOW-3 integrity, LOW-2 product). Rebuild each live diagnosis and
   candidate request offline from a read-only copy of the run's store, with the real wrapping order
   (`CitationStatusMechanic(BoundedMechanic(capture))`, as `fixer/rebuild_requests.py` and
   `backend/tests/lab/citation_status_saved.py` do), and report the block's rows. Then check that each request's
   provider-reported input tokens equal the rebuilt local count minus 136.
3. **Freeze the checker.** Name `scripts/experiments/check_evidence_gap_misreading_v2.py` and its sha256 in the run's
   declaration, run it with `--read-out pre-registered`, and count a CHECKED verdict only after a person has confirmed
   each `claim_matches` sentence (and read the `denied_matches`).
4. **Optionally, for a causal answer, first run a small paired probe** (owner's decision; it costs a few dollars): the
   v2e and v2d diagnosis requests are deterministic and rebuildable, so each can be sent k times with and without the
   block to the Mechanic model and scored by the frozen checker. That is a concurrent comparison.

A product record of the block beside `mechanic_outputs` (for example its hash and row count) would remove step 2's
rebuild. It is a product change that needs its own review, so it is **deferred**, not part of this build.

## 9. Reviews and fixer ($0, offline)

Two reviews ran after the builder: integrity (`review-integrity/`, verdict *pass with notes*) and product
(`review-product/`, verdict *READY_WITH_NOTES*). Both reproduced the builder's claims and found no defect in the product
code. Their findings, and what the fixer did (evidence `fixer/`):

| finding | verdict | change | test |
|---|---|---|---|
| MEDIUM-1 (both reviews): checker v2 reads denials and echoes of the block as claims | FIXED | claim shapes instead of bare "undecoded"/"not decoded"; clause denial rule; `claim_matches`/`denied_matches`; human check required (section 6) | 29 new pytest cases and 20 new self-test phrase cases; failed first (17 of 20 wordings), pass now; mutations F1–F8 caught |
| LOW-1 (integrity): post-hoc label only in file names | FIXED | required `--read-out`; `read_out_status`, note and the script's sha256 in every output; v2d/v2e outputs re-made in `fixer/checker-v2/` | output test failed first, passes now; mutations F9, F10 caught |
| LOW-4 (integrity): the null clause is narrower than the code | FIXED | meaning sentence now ends "(all three are null when no complete native adapter v2.1 citation record was recorded for that episode)"; declaration hash `163c1a4c…` → `b84f55db…` | `test_the_meaning_sentence_describes_every_null_row` failed first, passes now; mutation F11 caught |
| LOW-2 (integrity): size-rule records do not name the block | FIXED in docs; record wording DEFERRED | section 4 says the block counts toward and is never omitted from the target; `UNFIT_REASON` unchanged because it belongs to the frozen v2-bounded declaration | docs only |
| LOW-3 (integrity) = LOW-2 (product): no saved record that a Mechanic request carried the block | DEFERRED (product record); read-out step added | section 8, step 2 | docs only |
| LOW-1 (product): docs point to a builder report that is not a file | FIXED | the builder's final counts are stated in section 5 and in CURRENT_STATUS; the stale 2,965 line is removed | docs only |
| LOW-3 (product): no concurrent control for the next live read-out | FIXED in docs; paired probe DEFERRED (costs money, owner's decision) | section 8, steps 1 and 4 | docs only |

Fixer identities (`fixer/identity-compare.txt`): runtime `c4195af1…` → **`95042e4d…`**, algorithm `ea1ed613…` →
`4e5a8f90…`, declaration `163c1a4c…` → `b84f55db…` (the meaning sentence is part of it). Unchanged: the memory pointer
(`75241be8…`), V2_MEMORY (`6cbe23d4…`), v2-bounded (`11bf9e32…`), service `3ce5bcd2…`, contract `6f9d7783…`, interpreter
`6da0714a…`, scorer `19de811c…`, capability `8e8e04af…`, native adapters v1 (`6f303264…`, prompt `22515428…`) and v2
(`dfd41b33…`, prompt `fff397c9…`, protocol `0136604…`), reference Actor source `fb5e1894…` and prompt `12eabe7f…`.
`gate_freeze.py`: 30/30 functions and 20/20 files identical to the backup; only the runtime, algorithm and lab-tree
fingerprints changed. The example configuration hashes changed again: **register every agent again before a live run.**
