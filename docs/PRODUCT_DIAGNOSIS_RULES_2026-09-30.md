# Diagnosis rules: repair-and-record, and a guide built but not offered (September 30, 2026)

**Status: built by the builder, reviewed twice ($0: integrity and product), review findings fixed by the fixer ($0),
verified; then a $0 follow-up applied the PM's decision on review finding F4 and pinned the saved-store tests (section
11). All offline. Not yet committed, not run live, and the probe has not been run.** Evidence:
`artifacts/product-diagnosis-rules-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`, `fixer/`, `verify/`,
`followup/`, `probe-inputs/`; the current probe plan and declaration template are in `followup/probe-plan/`; the
builder's `probe-plan/` and the fixer's `fixer/probe-plan/` are superseded, because the guide block changed). The design
and the PM decision are in
[`artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md`](../artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md)
(sections 2, 3, 5 and 7, and the PM decision at its end). The runtime and identity values are in section 8; what the
fixer changed, and why, is in section 10; the follow-up is section 11.

Two separately declared rules and one probe harness:

| what | plan field | where it applies | in one line |
|---|---|---|---|
| `faultlab-mechanic-diagnosis/v1-repair-and-record` (Rule 1) | `mechanic_diagnosis` | frozen into **every new Learn plan**, every agent | a too-long diagnosis answer is told the limit and its own length on its one repair turn; every diagnosis gets a record saying whether the Mechanic requested, declined or gave no valid answer |
| `faultlab-diagnosis-guide/v1-kinds-and-checks` (Rule 2) | `diagnosis_guide` | **built and tested, not offered**; no new plan freezes it | a fixed block in the diagnosis request: the task, the C1-C8 public meanings verbatim with a two-sentence note on reading them, what each kind means, how the answer is used, the length limit |
| `scripts/experiments/diagnosis_probe.py` | - | request-only, pre-registered | 140 Mechanic calls on the five saved requests (cap $8); dry run by default; **not run** |

Every plan saved before these rules keeps its bytes, its plan_hash and today's behaviour.

## 1. Why (short)

Across live runs v2d to v2g the dev-5 source reproduced and reduced 4 of 4 times, but the diagnosis gave POLICY_GAP only
2 of 4 times. The two losses had two different causes (RECOMMENDATION.md section 1.2):

* **v2e** declined: the Mechanic requested no intervention, on a citation theory the recorded data refute.
* **v2g** did not decline. Both of its answers requested the right intervention, but both had a 614-character
  hypothesis against the 600-character limit. The repair message only said `string_too_long`, the model resent the same
  text, no intervention ran, and fixed code stored `proposed_kind: INCONCLUSIVE` as a code default. Nothing in the saved
  records said so, and a run document then described it wrongly (corrected earlier, commit `b5d0008`).

Rule 1 fixes the second cause and makes the record honest. Rule 2 might help the first cause, but that is unmeasured, so
it waits for the probe.

## 2. Rule 1: the repair turn states the limit, and every diagnosis is recorded

### 2a. The repair turn (only for a diagnosis request of a plan that declares the rule)

* Each `string_too_long` error in the repair message also carries `max_characters` (pydantic's own limit for that field)
  and `your_characters` (the length of the answer's field). For v2g it now says
  `{"location":["hypothesis"],"max_characters":600,"type":"string_too_long","your_characters":614}` (canonical JSON, keys
  sorted).
* Today's instruction sentence is kept exactly, and one sentence is appended: *"A string_too_long error gives
  max_characters and your_characters: rewrite that same field in at most max_characters characters, keeping its meaning
  and adding no new claim."*
* Other errors keep today's form. The first turn is byte-identical with or without the rule. The model's text is never
  truncated or edited; the 600-character limit (`contracts/models.py`) is unchanged. Candidate and completion requests are
  never changed.
* Cost: +47 tokens on a repair turn only (10,153 → 10,200 for v2g; 10,030 → 10,077 for v2f).

### 2b. The record (`diagnosis_requests/<diagnostic_id>`, immutable)

Written right after the Diagnostician returns and **before** the learning loop's POLICY_GAP gate, so INCONCLUSIVE
diagnoses get one too. Fields:

* `proposal_status`: `VALID_REQUESTED`, `VALID_NO_REQUEST` or `INVALID_OUTPUT`;
* `recorded_proposed_kind` and `recorded_proposed_kind_source`: `model` or `code_default`;
* `attempts`: every Mechanic attempt in order, by its `mechanic_outputs` id, with its validation errors (as the repair turn
  stated them); `output_refs`, `request_id` and `first_turn_hash` (the sha256 of the first-turn messages, since the product
  does not store the sent request);
* `last_raw_unvalidated`: the last answer's `proposed_kind` and requested id as parsed, marked `validated: false`;
* `options`: every offered intervention with its **change string** and observed treatment trials (this also works around
  the `diagnostics.py:72` defect, which stores the prediction in `change`, without editing that file);
* `requested_intervention_id`, `requested_change`;
* `intervention_ran`: **at least one fresh intervention trial ran** (fixer, review finding MEDIUM-1 / F3; the builder's
  version said true whenever an experiment was recorded, even one that ran nothing); `intervention_experiment_recorded`:
  an experiment was saved at all; `fresh_intervention_trials`;
* `interventions`: each experiment's result, complete trial pairs, limitations and `early_end`, the reason code when it
  ended before its three pairs (`PREFLIGHT_REJECTED`, `STOPPED`, `CALLBACK_ERROR:<class>`, `INVALID_CALLBACK_RESULT`,
  `INVALID_OR_UNTRIGGERED_TRIAL`), or null;
* `verdict`;
* `statement`: one plain sentence, for example *"None of the Mechanic's 2 answer(s) passed validation (hypothesis
  string_too_long (614 of at most 600 characters); …), so no intervention ran. Fixed code recorded INCONCLUSIVE; the
  recorded proposed_kind INCONCLUSIVE is a code default, not the model's."* When the requested intervention ended early it
  says so, for example *"Intervention result: intervention-… INCONCLUSIVE after 0 of 3 trial pairs; it ended early:
  preflight rejected its recipes before any trial (PREFLIGHT_REJECTED); no fresh trial ran."*

The recording wrapper is outermost, so it keeps the Diagnostician's own options before the guide, citation-status or size
wrappers touch the request. If its state does not describe this diagnosis (no attempt, the last output id is not the
returned one, or fresh trials without any recorded experiment), the record is **not** written and the campaign fails
loudly (ERROR, after the interventions were paid for) rather than saving a false record; the error names the diagnosis
and its counterexample. In the product this cannot happen, because the Diagnostician always calls the Mechanic once; it
did happen in two existing test harnesses (used by three test files: `test_evidence_wait.py`, `test_evidence_retry_v3.py`,
`test_discovery_v4_review_fixes.py`) whose Diagnostician is a stage double that never calls the Mechanic, so those
harnesses switch the rule off (with a comment). A separate loop test (fixer, review finding LOW-4) runs Rule 1 with the
real Diagnostician and the real Mechanic through the same evidence-wait harness, with a wait before the diagnosis and a
wait after it: the campaign ends NO_CHANGE and every diagnostic has exactly one record. A source whose diagnosis request
the size rule refuses (`MechanicContextUnfit`) gets no diagnosis and so no record; its `mechanic_context_records` entry
already says why.

**Dashboard (fixer, review finding F2 / LOW-2).** The Learn setup form lists the rule among the rules every new Learn
plan freezes, and the saved plan shows it (or says plainly that an older Learn plan predates it), with its exact text;
the frontend checks the declaration's fixed fields and refuses it outside Learn. The diagnosis panel now labels the stored
kind "Recorded proposed kind" and says it is INCONCLUSIVE by default when the Mechanic gave no valid answer. **Not done
(follow-up):** the dashboard does not show the `diagnosis_requests` record itself; only the campaign recording (export)
carries it. The experiments and diagnostics APIs are unchanged.

**Export.** For a plan that declares the rule, the development recording gains a top-level `diagnosis_requests` list;
each row embeds every attempt's `mechanic_outputs` record by id (`attempt_outputs`), including a rejected first attempt
that shares its request id with the repair (v2f's attempt 0, which the existing `mechanic_outputs` list leaves out; that
list's rule is unchanged). Older recordings keep their exact keys.

**Replayed on the five saved diagnoses** (saved-store check, section 7) the record says: v2d `VALID_REQUESTED`; v2e
`VALID_NO_REQUEST`; v2f `VALID_REQUESTED` with attempt 0 rejected at 743 characters; v2g dev-5 `INVALID_OUTPUT`,
`code_default`; v2g dev-6 `VALID_REQUESTED`. The wrong run-doc line could not have been written from this record.

## 3. Rule 2: the diagnosis guide, built and NOT offered

`backend/app/lab/diagnosis_guide.py`. A `DiagnosisGuideMechanic` wrapper adds one key, `diagnosis_guide`, to a diagnosis
request: `protocol`, `meaning`, `task` (the campaign's own task text), `kinds` (POLICY_GAP, CONTRACT_EVIDENCE_GAP,
INCONCLUSIVE, as in the minimal design), `checks` (`PUBLIC_INVARIANTS` C1-C8 verbatim), `checks_note`, `contract_note`,
`use` and `hypothesis_length`. It reads nothing from any episode or from scoring and contains no worked example.

* **PM decisions:** the draft `checks_note`'s interpretive sentence (*"C6 is the check of the report's citations: where
  C6 passed, that report's citations met it."*) is **dropped**, because it cannot be verified without opening
  `checks.py`. Its other two sentences name no check and are **kept exactly as drafted** (PM decision on review finding
  F4, follow-up, section 11): *"Each episode's checks row gives the fixed checks by check_id and category; the checks
  field gives each check's public meaning. Explain each failed check from its own meaning."* No fixed sentence of the
  block names a check; the C1-C8 meanings appear verbatim only. The block is 23 tokens (the C6 sentence) shorter than the
  prototype: **+608 tokens** on every first turn (the prototype measured +631; the builder's block without any
  `checks_note` was +569).
* **Not offered:** `DIAGNOSIS_GUIDE_OFFERED = False` in `diagnosis_guide.py` is the one reviewed switch. While it is
  False, run options do not list the rule and new Learn plans do not freeze it. It should be flipped only after the probe's
  P1 and P2 pass and the PM approves.
* **A plan that declares it** (a synthetic plan in the tests, or one saved after the switch is flipped) is validated
  exactly: its fixed text must be v1's, its frozen `checks_hash` must be the hash of its frozen `checks`, and Start
  refuses it unless the whole declaration equals the installed one (so any later edit to `PUBLIC_INVARIANTS` blocks Start
  for such plans until a v2 of the rule is declared, as intended). The learning loop then applies it.
* **Placement:** guide outside citation status, which sits outside the size rule; the recorder outermost. The size rule
  counts the block and never compacts it.

## 4. Common to both rules

* Only Learn plans may declare either rule (`_bindings` refuses baseline and compare plans).
* The protocol id binds its text: `MechanicDiagnosisPlan` and `DiagnosisGuidePlan` reject any altered fixed sentence or
  list, and `semantics_hash` / `checks_hash` must match. Start also compares each declared rule with the installed one.
* Both keys are in the plan's omit-absent list, so older plans re-serialize without new keys.

**Explicitly unchanged:** `referee/` (diagnostics.py, reducer.py; checks.py was not opened), `lab/diagnosis.py` (options,
context, V2_MEMORY, the hard-coded prediction, the null path and the code default), `prompts/diagnosis.md`,
`contracts/models.py` (the 600-character Text), `lab/citation_status.py`, the `learning.py` POLICY_GAP gate line,
reproduction, reduction, assess_pairs, source validation, challenge, evaluation and promotion, the reference Actor and
`prompts/actor.md`. The verdict still comes only from `classify_policy_gap`, fed by fresh trials.

## 5. The probe harness (not run)

`scripts/experiments/diagnosis_probe.py` implements RECOMMENDATION.md section 7. Section 7 does not settle every counting
detail, so the harness makes its own choices; they are listed below under **Scoring** and written word for word into the
declaration's `pre_registered_outcomes` (a declaration must carry exactly that text, so the hashed declaration states
them):

* **Inputs:** the five rebuilt requests, copied byte for byte into
  `artifacts/product-diagnosis-rules-2026-09-30/probe-inputs/` (`SHA256SUMS`, identical to inv-a's), each run's saved
  export (task text), and run v2g's saved plan and configuration for the model, the request settings and the per-call
  bound. All are pinned by sha256; the harness refuses any other bytes, and refuses if the installed product's request
  settings for the Mechanic model differ from the saved plan's.
* **Arms:** CONTROL (the first turn as sent) and GUIDE (the same plus the Rule 2 block, built with the product's
  `diagnosis_guide.attach`), K=10 per request per arm = 100 first-turn calls; repair sub-probe: v2f's 743-character and
  v2g's 614-character answers replayed as the assistant turn, then today's saved repair message or the Rule 1 message
  (built with the product's `diagnosis_protocol`, byte-identical to what the real Mechanic sends; a test checks this),
  K=10 each = 40 calls. Order: in each of 10 rounds, the 10 first-turn calls then the 4 repair calls; each pair of arms
  alternates which goes first.
* **Charging:** every call goes through `RuntimeProvider.complete` (role mechanic, 2,000 output tokens, 20 s) and is
  admitted and charged **before** it is sent on a `CampaignLedger` saved in the output folder, at the saved per-call
  bound ($0.04984), with a hard cap of $8: the 140 calls are reserved first ($6.9776), and the product's one blind
  transport retry is charged only from the remaining $1.0224 (at most 20 retries).
* **Dry run (default):** builds and checks every request, counts tokens, prints the maximum charge; no network, no
  provider, no `.env`.
* **`--execute-live`** refuses unless `--declaration FILE --declaration-sha256 HEX` are given, the file's sha256 is HEX,
  and the declaration names this harness's sha256, the dry-run plan hash, the model, a cap of at most $8, the approver,
  exactly this harness's pre-registered outcomes (P1-P4, the repeats report and the full decision rule), the frozen
  temperature and a non-empty `sampling.repeats_reading` (how repeated answers will be read), the checked preconditions
  (ledger checked, dashboard closed, no other paid run, **clock drift checked**) and exactly the `--out` folder, which must
  be new or empty. `followup/probe-plan/DECLARATION.template.json` is the current template.
* **Outputs (only under `--out`):** `plan.json`, `requests.json` (the exact messages sent), `answers.jsonl` (every raw
  answer verbatim, with `model_id`: the id the product's provider path returns, which `RuntimeProvider` echoes from the
  request; it is not a served-model field read from the response), `probe-ledger.sqlite3`, `manifest.json`,
  `scoring.json`, `review-blinded.csv` (no arm column, no checker output and no hints, seeded shuffle) and
  `review-key.json`.
* **Ledger.** The probe charges only its own `CampaignLedger` in `--out`. That charge is in no product campaign ledger or
  dashboard total, so after a run the manifest's `ledger.charged_dollar_upper_bound` (and the estimate from reported
  tokens) must be added to the project's carried total by hand; the manifest and the printed summary say so.
* **Scoring (the harness's counting choices):**
  * **P1:** a person marks every delivered dev-5 first-turn row Y or N in the blinded review file, without seeing the
    checker's matches or the arm. *Confirmed* = checker v2 claim match **and** the person's Y. PASS needs CONTROL confirmed
    at least 20 of 40 **and** GUIDE confirmed **plus** GUIDE rows the person marked Y without a checker match at most 4 of
    40 (fixer, review finding MEDIUM-2: a GUIDE hypothesis that blames labels in words the checker's phrase list misses
    counts against the bar). CONTROL confirmed below 20 of 40 is UNINFORMATIVE. Both choices make a PASS harder, never
    easier.
  * **P2:** dev-5 validity and over-600 counts, GUIDE vs CONTROL (the memo's bar).
  * **P3:** counts and one-sided Fisher tests with person-scored rubric columns (the automatic hints are in `scoring.json`
    only).
  * **P4:** valid-within-600 repair answers; PASS needs at least 9 of 10 on each setup with the Rule 1 message. For the
    decision rule, *worse* means the Rule 1 message's total over both setups (of 20) is lower than today's total.
  * **Repeats:** for every request key, the delivered answers, the distinct raw answers and the distinct hypotheses
    (fixer, review finding MEDIUM-3 / F1), also printed after a run.
  * `--score DIR [--review CSV]` rescores.

**Dry-run output** (`followup/probe-dry-run.txt`, the one dry run after the PM's F4 decision): 100 first-turn + 40
repair = **140 calls**; input tokens per request: CONTROL 8,990 / 9,088 / 9,639 / 9,794 / 9,352, GUIDE +608 each (9,598
/ 9,696 / 10,247 / 10,402 / 9,960), repair today 10,030 / 10,153, Rule 1 repair 10,077 / 10,200; **maximum charge 140 ×
$0.04984 = $6.9776** (hard cap $8.00); a tighter bound with these inputs and 2,000 output tokens per call is $2.9065;
network calls 0. Plan hash `91ca47e4aad3529605a68017a42789f80d4701ed62c6170993d56ae7bc4e5e57`, harness sha256
`b1eb7cdaf1490a459c26d36d0b8c16a5a585c663fee671f6ba90bb05e56b86ff` (unchanged: the harness file did not change; both
change if the harness or any request byte changes; a declaration must name them). Superseded: the fixer's plan
`e66a67b3…` (block without `checks_note`) and the builder's `9d5d3bd6…` / `fb73a584…`. Against the fixer's plan only the
five GUIDE requests (their `checks_note`, tokens and sha256), the Rule 2 declaration hash, the tighter bound and the plan
hash differ (`followup/probe-plan-diff-vs-fixer.txt`). `followup/probe-plan/` holds `plan.json`, the exact
`requests.json` and `DECLARATION.template.json` (`SHA256SUMS.txt`).

**Read before declaring the probe (PM decisions, not decided here).**
* **Temperature.** The harness sends the saved plan's frozen **temperature 0** (the product's `MODEL_REQUEST_SETTINGS`;
  `RuntimeProvider` always sends it). The declaration **cannot** change it: it only confirms the value and must say, in
  `sampling.repeats_reading`, how repeated answers will be read. (The builder's note said a different temperature could be
  declared; that was wrong and is corrected here.) K=10 repeats of an identical request at temperature 0 measure only the
  provider's run-to-run variation; if the answers repeat, each request-and-arm cell is effectively one sample and the
  4-of-40 and 5-of-40 bars mean much less than they appear to. `scoring.json` now reports the distinct answers per request
  key so this is visible. The PM either accepts temperature 0 and reads the cell, not the call, as the unit when answers
  repeat, or orders a reviewed harness change that sends another temperature (new harness sha256 and plan hash, and no
  longer the product's exact request path).
* **The guide text (review finding F4): decided.** The builder had dropped the draft's whole `checks_note`, three
  sentences, not only its C6 sentence. The PM decided that only the interpretive C6 sentence goes; the two neutral
  sentences are restored exactly as drafted (section 11). The block, T3/T9, the Rule 2 declaration hash and the plan hash
  changed accordingly (+608 tokens, plan `91ca47e4…`).

## 6. Tests ($0; the memo's T1-T9)

New files: `backend/tests/lab/test_diagnosis_rules.py` (60 tests from the builder, 65 after the fixer),
`backend/tests/lab/test_diagnosis_rules_loop.py` (3, now 5), `backend/tests/experiments/test_diagnosis_probe.py` (20, now 27)
and `frontend/tests/diagnosis-rules.test.tsx` (5, fixer). All pass.

* **T1 plans:** new Learn plans for reference, smolagents and smolagents-v2 carry Rule 1 and not Rule 2; run options
  offer Rule 1 only; baseline plans carry neither; altered text fails the exact validators (13 changes for Rule 1; for
  Rule 2, 13 changes, among them the draft's full `checks_note` with the C6 sentence, and a declaration without
  `checks_note`); non-Learn plans are refused; Start refuses a different installed Rule 1 and a guide whose frozen C1-C8 text or
  hash differs (including an edit to `PUBLIC_INVARIANTS`); a plan saved before the rules keeps its bytes and starts; each
  of the six plans earlier runtimes saved in the native-v2b store re-reads with its plan_hash and no new key (read at the
  store's reviewed end, row 8583, so plans a later live run saves cannot change the test; section 11); flipping `DIAGNOSIS_GUIDE_OFFERED` is the only way the
  guide is offered.
* **T2 flag off, byte for byte:** the real Mechanic, fed each saved context and the saved answers, sends exactly inv-a's
  saved request bytes (8,990 / 9,088 / 9,639 / 9,794 / 9,352 tokens; repairs 10,030 / 10,153); with the rule on, the
  first turn is identical; `mechanic_outputs` records have the same fields and values either way.
* **T3 the guide is additive:** exactly one key added, every other key byte-identical, +608 tokens on every first turn,
  the citation block and the V2 memory pointer unchanged; wrapper order checked in the loop; a synthetic diagnosis request
  of just under 32,000 tokens is sent unchanged without the guide, but with the guide it is over the limit and the size
  rule compacts it to at most 28,000 tokens, keeping the guide byte for byte; the block names no check outside the verbatim
  meanings, and its `checks_note` is exactly the draft's two neutral sentences, without the C6 sentence.
* **T4 repair turn:** v2g's 614-character and v2f's 743-character answers get `max_characters` 600 and
  `your_characters` 614 / 743 and the appended sentence (+47 tokens); flag off gives today's bytes; a 601-character
  hypothesis fails in both modes and is stored verbatim; a 600-character one passes; other errors keep today's form;
  candidate requests are unchanged; the flag-off repair line in `mechanic.py` is textually the backup tip's line.
* **T5 record:** valid request → VALID_REQUESTED; null → VALID_NO_REQUEST and INCONCLUSIVE; invalid twice →
  INVALID_OUTPUT, code_default, both output ids in order; invalid then valid (v2f) → VALID_REQUESTED with both attempts;
  option change strings equal the request's; the DiagnosticResult equals the flag-off one; the record is immutable; an
  inconsistent state writes no record.
* **T6 gate invariance:** the 24-cell matrix {reproduction valid, invalid} × {null, valid request, invalid output} ×
  {SUPPORTED, INCONCLUSIVE, CONTRADICTED, PREFLIGHT_REJECTED}: identical kinds, intervention records, ledger reservation
  and charge sequences and trials, flag off and on; pinned sha256 of `referee/diagnostics.py`, `reducer.py`,
  `lab/diagnosis.py`, `prompts/diagnosis.md`, `contracts/models.py` and `citation_status.py`, and PROTOCOL_HASH
  `bfefe69b…`, unchanged; the gate line is present once and the record call comes before it.
* **T7 export:** with the rule, every attempt appears by id, including a v2f-style attempt 0; without it, the recording
  has exactly today's keys and the rule's export code never runs. On a copy of the saved store, all 6 saved campaigns'
  recordings are byte-identical under this build's `exports.py` and the backup tip's.
* **T8 end to end:** the offline_fixture scripted Learn campaign (real localhost simulator) run without and with Rule 1:
  the same state, episode counts, scripted calls, records and ledger calls, plus exactly one `diagnosis_requests` record
  (VALID_REQUESTED, model, intervention ran, POLICY_GAP).
* **T9 replay:** the minimal design's prototype still reproduces its saved block and declaration hashes and +631 tokens on
  all five requests, and the product's block equals it with only the C6 sentence taken out of `checks_note` (23 tokens); the integrity prototype's saved statuses,
  kind sources and repair messages equal what the product now records and sends.
* **Probe harness:** dry run (140 calls, $6.9776, nothing written); every request is the saved bytes or exactly one
  declared change; the Rule 1 repair request equals the real Mechanic's; refusal without a declaration or with any
  mismatching field, a wrong sha256 or a used output folder (no provider is ever built); a scripted live run charges 140
  calls through the ledger ($6.9776), writes only under `--out` and scores (P1 pending a person, then PASS with a filled
  review file); with every call failing, 20 retries fit and the charge stays at 160 × $0.04984 ≤ $8; caps above $8 or
  below the planned calls are refused; pinned inputs are refused when changed.

**Negative controls** (`builder/mutation_checks.py`, `builder/mutation-checks.log`, in a scratch copy outside the
Desktop, deleted afterwards): the unmutated copy passes 83 of 83; each of 14 mutations is caught (dropping part 1a,
limit errors leaking into flag-off requests, a decline recorded as a request, a code default labelled as the model's,
the record moved after the gate, the guide offered, the C6 note restored, the guide placed inside the size rule, older
plans gaining a null key, Start not comparing the guide, the export dropping a rejected attempt, the probe sending before
charging, running live without a declaration, and a $9 cap).

**`scripts/test.sh` results.** The builder's one run (`builder/full-test-sh.log`) **exited 1**: the backend stage had
**2 failed**, 3,119 passed and 180 skipped; frontend, build and browser passed. The two failures are
`test_history_fireability.py::test_a_new_v4_plan_on_the_saved_store_refuses_the_lone_status_read_target` (36 == 30) and
`::test_the_saved_stores_status_read_picks_are_refused_and_its_other_picks_are_allowed` (14 == 8). That file is unchanged
from `626bae4`; its assertions pin the saved native-v2b store's history as it was before live run v2g added episodes, so
they fail with or without this change. Neither reviewer could re-run them on `626bae4` code (they need
`audit/promotion.json`, which reviewers may not copy). The fixer's one run is `fixer/full-test-sh.log` (section 10).

## 7. Saved-store check

`builder/saved_store_check.py` on a scratch copy of the saved native-v2b store (original opened `mode=ro&immutable=1`,
sha256 unchanged, copy deleted): 6 of 6 saved plans read and re-serialize byte for byte with their plan_hash and declare
neither rule; 6 of 6 recordings are byte-identical under the old and new `exports.py`; the five diagnosis requests,
rebuilt from the store with investigation A's own code and sent through the real Mechanic with the rule off, equal inv-a's
saved requests turn for turn; with the rule on the first turns are equal and the records are exactly as the memo predicted.

## 8. Identity

`builder/identity-before.json`, `builder/identity-after.json`, `builder/identity-compare.txt` (the product's own
functions, under the network guard). **After the follow-up (section 11) the current values are runtime
`1abba8a6810b6bd6b47dd5887c6305052ca87d48660977fb6277a3ff81462b2f`, algorithm `0b34473c…` and Rule 2 declaration
`def60594…`**; the list below is the builder's and fixer's history:

* runtime `49958e716f0b08aacb9db5d6ddf99620451f949a901aa35cca979918c1df6b6e` →
  `e3551ead0715fbbb65e24d1756f181b93acf237c9bdbe7849d266a1dc023a5a9` (builder) →
  **`c80d86323bc82624ab22000edb37ce46d09f2e621d04ca8928903471749aa493`** (fixer; only `diagnosis_protocol.py` changed in
  `backend/app`); algorithm `7a56afed…` → `e4c47b4e…` → **`743a1520…`**;
* reference Actor source hash `7f78de28…` → `eaffac74…` (`backend/app/agents/mechanic.py` is in that tree), and so the
  example native configuration hashes change too: **register every agent again before a live run**;
* Rule 1 declaration `729441f0…`, semantics `577b0c80…` (builder; **superseded by the fixer**: `998744f8…` and `c4dd868c…`,
  because the rule text now defines `intervention_ran`); Rule 2 declaration `36ca790f…` (offered: False, unchanged by the
  fixer); C1-C8 content hash `e792e8f0…`;
* unchanged (30 of 41 values): service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…`,
  native v1 and v2 adapter and prompt hashes (v2.1 prompt `fff397c9…`), the response-format and transport/evidence-retry
  declaration hashes, `PROTOCOL_HASH` `bfefe69b…`.

`gate_freeze.py` (run with `audit/promotion.json` and `audit/final-audit.json` left out, so they are never read):
124 values compared, 8 changed, all of them `mechanic.py` (file and `Mechanic` class) or the source fingerprints.

## 9. Before any paid step, and what is still open

* The probe needs owner/PM approval and a declaration (template in `followup/probe-plan/`, plan `91ca47e4…`); decide
  the temperature question in section 5 first (the `checks_note` scope is decided, section 11). Check the ledger (last
  carried total $923.53), close the dashboard, run `check_clock_drift.py`, never run two agents at once, and quote
  heredocs when a declaration contains `$` figures. After a run, add its charged upper bound to the carried total by hand.
* Rule 1 ships after review unless the probe's P4 shows the new repair message is worse than today's. Rule 2 ships only
  if P1 and P2 pass; then flip `DIAGNOSIS_GUIDE_OFFERED` in a reviewed change.
* Follow-ups not in this change: the dashboard should read and show the `diagnosis_requests` record (the diagnosis panel
  now calls the stored kind "Recorded proposed kind" and says it is a code default when no answer was valid, but it cannot
  yet say which applied); the `diagnostics.py:72` defect, only as a declared protocol-hash bump; a reviewed
  gate-tightening design (RECOMMENDATION.md section 4). (Re-pinning the saved-store tests is done in the follow-up,
  section 11; it has not been reviewed separately.)
* Rule 1 is already frozen into every new Learn plan, before P4 is measured (as the spec asked). If P4 later shows the new
  message is worse, Rule 1 needs a withdrawal or a v2.
* Someone allowed to open `checks.py` should confirm that the C1-C8 public meanings match what it implements before
  Rule 2 is offered.

## 10. Fixer round (September 30, $0, offline)

Two $0 reviews (`review-integrity/`, `review-product/`) found no HIGH issue. The fixer checked every finding against the
code, fixed the real ones with tests that failed before the fix and pass after it, and explains the rest. Evidence:
`fixer/` (`before-fix-tests.log`, `after-fix-tests.log`, `mutation-checks.log`, `mutation_checks.py`, `full-test-sh.log`,
`identity-*.json`, `gate_freeze/`, `probe-dry-run.txt`, `probe-plan/`, saved-store sha256 files, git state).

| finding | verdict | change |
|---|---|---|
| MEDIUM-1 / F3 `intervention_ran` true with 0 trials | FIXED | `intervention_ran` = at least one fresh trial ran; new `intervention_experiment_recorded`; each intervention row's `early_end`; the statement names the early end; the rule text (and so its semantics hash) says so |
| MEDIUM-2 / F5(c) P1 ignores person-only flags | FIXED | GUIDE rows a person flags without a checker match count against the GUIDE bar; the review file no longer shows checker output or hints |
| MEDIUM-3 / F1 temperature 0 | FIXED (doc and reporting); the temperature itself is a PM decision | the wrong doc sentence corrected; scoring and the printed summary report distinct answers per request key; the declaration must state the frozen temperature and how repeats are read |
| F5(a, b) pre-registration only in code | FIXED | P4's "worse", P1's rule and the full decision rule are in the template, and a declaration must carry exactly that text |
| LOW-3 separate ledger, `served_model`, clock drift | FIXED | the manifest, template and printed summary say to add the charge to the project ledger; `served_model` renamed `model_id` with its meaning; `clock_drift_checked` precondition required |
| F2 / LOW-2 dashboard does not show Rule 1 | FIXED (plan display, validators, panel label); DEFERRED (showing the record) | setup form and saved plan show the rule; frontend validators; diagnosis panel label |
| LOW-4 Rule 1 never run with evidence waits | FIXED | new loop test with the real Diagnostician and Mechanic and two evidence waits; refusals name the diagnosis |
| LOW-1 / F6 report and doc accuracy | FIXED | this doc states the test.sh results, lists `requests.json`, drops "exactly", names the counting choices |
| F4 whole `checks_note` dropped | DEFERRED to the PM | not a defect: it follows the spec's include-list; section 5 asks the PM to confirm before declaring |

Negative controls (`fixer/mutation-checks.log`): each of the 17 fixes reverted on its own in a scratch copy outside the
Desktop is caught by a test; the unreverted copy passes; the scratch copy is deleted.

After the fixes: runtime `c80d86323bc82624ab22000edb37ce46d09f2e621d04ca8928903471749aa493`, algorithm `743a1520…`;
Rule 1 declaration `998744f8…`, semantics `c4dd868c…`; Rule 2 declaration `36ca790f…` (unchanged by the fixer; offered:
False; the follow-up changed it to `def60594…`, section 11);
service, contract, interpreter, scorer, native v2.1 prompt and the reference Actor source hash (`eaffac74…`, which the
fixer did not change) are as in section 8. Only `backend/app/lab/diagnosis_protocol.py` changed in `backend/app`; the
fixer also changed the probe harness, the frontend (plan display, validators, panel label) and tests. The fixer's one
`scripts/test.sh` run, after the last edit, is `fixer/full-test-sh.log`; it ran after this page was written, so its
result is stated in the fixer's report, not here. As before: nothing committed, nothing run live, the probe not run.

## 11. Follow-up (September 30, $0, offline): the PM's F4 decision and pinned saved-store tests

Evidence: `followup/` (`guide-measurement.json`, `probe-dry-run.txt`, `probe-plan/`, `probe-plan-diff-vs-fixer.txt`,
`inspect-store.json`, `mutation_checks.py`, `grow_store.py`, `mutation-checks.log`, `saved-store-tests-diff-vs-626bae4.txt`,
`full-test-sh.log`, `identity-after.json`, `identity-compare.txt`, `gate_freeze/`, `byte-identity.txt`, saved-store
sha256 files, git state). Nothing committed, nothing run live, the probe not run.

**(A) The guide keeps the draft's two neutral `checks_note` sentences (PM decision on review finding F4).** The PM's
earlier instruction dropped only the interpretive C6 sentence. The block's `checks_note` is now exactly the draft's text
minus that sentence: *"Each episode's checks row gives the fixed checks by check_id and category; the checks field gives
each check's public meaning. Explain each failed check from its own meaning."*
* `diagnosis_guide.py`: `CHECKS_NOTE`, carried in `FIXED_TEXT`, `declaration()` and `block()`; `run_plans.py`:
  `DiagnosisGuidePlan.checks_note`, bound word for word through `FIXED_TEXT` (a declaration without it, or with the C6
  sentence back, is refused); the dashboard's declaration type and validator carry it, and its one-line description says
  the meanings come with a short note on reading them. The rule's `rule` sentence is unchanged (the draft's did not list
  the note either). `interprets_checks` stays False: neither sentence names or explains a check.
* The protocol id stays `faultlab-diagnosis-guide/v1-kinds-and-checks`: the guide was never offered and no saved plan in
  any store declares it (verifier: 21 of 21 saved plans), so no plan carries the older text.
* Numbers: **+608 tokens** on each first turn (9,598 / 9,696 / 10,247 / 10,402 / 9,960; the prototype's +631 less the
  C6 sentence's 23); Rule 2 declaration `def60594d4677b89c2450079896a3f8c0433f50dbbc51693beeb934b5130c789` (was
  `36ca790f…`); block sha256 `dedf43f2…`. `DIAGNOSIS_GUIDE_OFFERED` is still False: Rule 2 is **not offered**.
* Tests: T3 (+608; the note is exactly the two sentences; no C6 sentence anywhere; no fixed sentence names a check), T1
  (13 text changes refused, among them the full draft note, plus a declaration without the note), T9 (the product's block
  is the prototype's with only the C6 sentence removed; 631 − 608 = 23), the probe test (+608), the frontend test (an
  empty note is refused).
* Probe plan regenerated (inputs unchanged, `probe-inputs/SHA256SUMS` OK): plan
  `91ca47e4aad3529605a68017a42789f80d4701ed62c6170993d56ae7bc4e5e57`, harness `b1eb7cda…` unchanged, 140 calls, maximum
  $6.9776, tighter bound $2.9065, network 0. Only the five GUIDE requests, the Rule 2 declaration hash, the tighter bound
  and the plan hash differ from the fixer's plan.

**(B) The saved-store tests read fixed snapshots.** `scripts/test.sh` exited 1 in the builder's, fixer's and verifier's
runs because two `test_history_fireability` tests read the live saved store `/Users/shree/FaultLab_Runs/2026-09-30/
native-v2b/lab.sqlite3` and pinned numbers from before live run v2g added episodes (36 vs 30 verified episodes; 14 vs 8
allowed discovery picks). The store only grows, and every record gets a higher row number than all before it
(`LabStore.max_record_rowid`), so a read at or below a recorded row number is a fixed snapshot.
* `test_history_fireability.py` (all three saved-store tests): the store at **record cutoff 6748**, the cutoff at which
  live run v2g's own saved plan (`campaign-d8d1e8cc…`) froze its history, i.e. the store as v2b-v2f left it. The new v4
  plan freezes its history there (the one "now" a plan reads, `max_record_rowid`, returns 6748 while the plan is made;
  asserted to be read exactly once), and must reproduce v2g's frozen history summary hash `d581867c…`. Its history,
  replay list and fireability table equal v2g's saved ones. Every original assertion is kept: 30 verified episodes (18
  baseline-study + 12 discovery), the table (F4 on `get_operation_status` REFUSED at 0 of 4, the rest ALLOWED or too few),
  Start accepts the plan, the five plans saved before the rule read byte for byte without the block (now counted: 5), the
  saved picks at the snapshot are refused exactly when every fault is on the status read (3 challenge and 7 discovery
  refused, 8 and 8 allowed), and the real loop refuses and re-plans a status pick (2 replays, fired share 0/4).
* Other tests that read the live store the same way, found by searching every test for saved-store paths:
  * `test_diagnosis_rules.py` T1 (every saved plan re-reads without new keys) read every plan; a plan this build saves
    declares Rule 1 and would have failed it after the next live run. It now reads the six plans at the store's reviewed
    end (row 8583) and checks their campaign ids.
  * `test_loop_limits_mechanic_context.rebuild_v2d_request` (used by that file's v2d test and by
    `test_citation_status`'s v2d candidate test) matched challenge evaluations by candidate and incumbent hash across the
    whole store, so a later campaign challenging an identical candidate would have changed the request (33,223 tokens).
    Its list reads now stop at **3022**, the cutoff at which live run v2e's plan froze its history (the store as v2d left
    it).
  * Not changed, because nothing a later run adds can change them: `test_citation_status`'s v2e/v2d diagnosis rebuilds
    (they read only those two finished campaigns' records) and its new-plan test (it asserts nothing that depends on the
    store's other records); the `artifacts/lab.sqlite3` probe tests (they already select by episode id or a `started_at`
    cutoff; that store is unchanged since September 27); JSON fixtures. No frontend test reads a saved store.
* Controls (`followup/mutation-checks.log`, scratch copy outside the Desktop, deleted afterwards): the unpinned (626bae4)
  tests fail on today's store (36 == 30, 14 == 8); on a copy grown by synthetic records standing in for a later live run
  (a valid plan that declares Rule 1, a pick mixing the status read with another fault, a challenge evaluation of v2d's
  candidate) all 8 pinned saved-store tests pass while the unpinned versions fail (36 == 30; a mixed pick; a plan with
  `mechanic_diagnosis`; 34,572 == 33,223); moving the fireability cutoff to the store's end (8583) makes the pinned tests
  fail (another summary hash), so the snapshot, not a looser assertion, is what makes them pass. 11 of 11 product
  mutations are caught: 5 for (A) (the C6 sentence back, the note left out of the block, the validator not binding the
  note, the note shortened, the dashboard validator not checking it) and 6 for (B) (fireability's 3-episode minimum and
  1/2 bar, the history ignoring its cutoff, the replay minimum, older plans gaining a null key, the request-size target).

**Result.** The one `scripts/test.sh` run after the last code change (`followup/full-test-sh.log`, 21:08-21:28 UTC)
**exited 0**: backend 3,135 passed, 180 skipped (the verifier's run: 2 failed, 3,133 passed, 180 skipped); frontend 29
files, 373 tests passed; build passed; browser 19 passed, 1 skipped; a once-a-second network monitor saw 0 non-loopback
connections in 1,113 samples. The saved stores' files had the same sha256 before and after. Identity (`followup/identity-compare.txt`, against the verifier's end state):
runtime `c80d8632…` → `1abba8a6810b6bd6b47dd5887c6305052ca87d48660977fb6277a3ff81462b2f`, algorithm `743a1520…` →
`0b34473c4db55d9c82fdb9479d6d2ed8a560c4df1f97db08e320da7680cc80df`, Rule 2 declaration `36ca790f…` → `def60594…`, and
the two example native configuration hashes (they embed the runtime fingerprint; register every agent again before a live
run, as before). The other 45 values are unchanged, among them service `3ce5bcd2…`, contract `6f9d7783…`, interpreter
`6da0714a…`, scorer `19de811c…`, native v1 prompt `22515428…`, native v2.1 prompt `fff397c9…`, reference source
`eaffac74…`, Rule 1 `998744f8…` / `c4dd868c…`, `PROTOCOL_HASH` `bfefe69b…` and C1-C8 `e792e8f0…`. `gate_freeze.py`
(audit JSONs left out): against the verified state only the algorithm, runtime and `lab` tree fingerprints changed; all 20
files (checks.py included, hashed by gate_freeze only) and all 30 functions are identical.
