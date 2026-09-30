"""Fixer: one-time edit of CURRENT_STATUS.md for the September 30 fixer round (kept as evidence of what was changed)."""
from pathlib import Path
p = Path('CURRENT_STATUS.md'); s = p.read_text()
edits = [
('''current code is **`18292424…`** (September 30 builder: lab-role transport backoff and native adapter v2.1 labels, below; $0, offline only;
**not committed, not reviewed**), built on `ac7a12d2…`''',
 '''current code is **`4553ebe7…`** (September 30: builder, two $0 reviews and fixer: lab-role transport backoff and native adapter v2.1 labels, below; $0, offline only;
**not committed, not run live**), built on `ac7a12d2…`'''),
('''The repairable C3 failure was never exposed (Explorer never picked a rejected upgrade) | `docs/PRODUCT_NATIVE_LEARN_RUN_2026-09-29.md` |

| Native adapter v2, first live run''',
 '''The repairable C3 failure was never exposed (Explorer never picked a rejected upgrade) | `docs/PRODUCT_NATIVE_LEARN_RUN_2026-09-29.md` |
| Native adapter v2, first live run'''),
('''**Current runtime: `182924246224e4dc33983294fcda5c160f1a458e75c5cfe938634392774562b6`** (algorithm
`b2575eb2…`): the September 30 builder round (next paragraph), **not committed and not yet reviewed**; built on
`ac7a12d2`. Simulator service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…` and scorer `19de811c…` are
unchanged; `external_agent.py` (native v1) is byte-identical, v1's adapter hash (`fa7a58db…`) and prompt hash
(`22515428…`) are unchanged. **Register every agent again before a live run** (the runtime changed, as after every
build). **Native adapter v2 is a new identity:** its adapter protocol (part of its prompt hash) changed, prompt hash
`cee3aeda…` → `fff397c9…`, adapter hash `d27c374f…` → `4ba8b785…`; a v3 agent history for v2 does not include the first
v2 build's episodes, and the two builds' results must not be pooled. The reference Actor's source hash (a tree hash of
`backend/app/agents`, which now holds the new retry code) changed `99a9034f…` → `f6d2d6eb…`; its prompt, context and
response protocols, and so its history identity and model-visible behaviour, are unchanged.''',
 '''**Current runtime: `4553ebe7db2f9e3efda6f8761e987c6f1ea58dce12d3fde2dfbc8812ebb7c057`** (algorithm
`b2575eb2…`): the September 30 round (builder, two $0 reviews, fixer; next paragraph), **not yet committed** and not
run live; built on `ac7a12d2`. Chain: `ac7a12d2` → `18292424` (September 30 builder, never committed) → **`4553ebe7`**
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
model-visible behaviour, are unchanged.'''),
('''**September 30 (builder, $0, offline; not run live, not reviewed): two fixes from the first live v2 run.**
Evidence and the full report: `artifacts/product-native-v2b-2026-09-30/builder/`.''',
 '''**September 30 (builder, two reviewers, fixer; $0, offline; not run live, not committed): two fixes from the first live
v2 run.** Evidence: `artifacts/product-native-v2b-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`,
`fixer/`).'''),
('''  exactly rule v1 or (Learn) exactly rule v2. Shown in the saved plan, the discovery budget, the Learn setup form and
  the fault-search panel. Details:''',
 '''  exactly rule v1 or (Learn) exactly rule v2. Shown in the saved plan, the discovery budget and the Learn setup form;
  a **discovery** selection's retries are shown on it in the fault-search panel, while challenge-selection and
  Mechanic retries appear only in the campaign recording and the budget counts, and nothing shows a wait while it
  happens (the campaign stays SELECTING or DIAGNOSING). Review fixes: a retry the unreserved budget cannot cover is
  refused **before** its wait (a read-only budget check; the charge after the wait stays the only admission); a
  request that got no retry says "no transport retry was sent: <reason>" instead of "after 0 transport retries"; under
  discovery v2 the dashboard states the real discovery bound (12, the campaign cap, not the declared 16). A store with a
  new Learn plan needs this runtime or a later one: an older checkout (`ac7a12d2` or earlier) reports such a plan as
  "missing, corrupt or inconsistent" (read from that code, not run). Details:'''),
('''  `cited_tokens_not_decoded` instead of `cited_unshown_labels`. The Mechanic and Explorer never saw the agent's
  labels; they see each report's decoded IDs as the episode's `oN` row aliases. That view is unchanged for the same
  citations (the hidden first attempt is still a recorded row, so a report citing only what the agent saw still
  skips it, e.g. o1, o2, o4). What changed for them is the v2 contract text: it now says unseen observations exist and
  get no label, and that `oN` counts every recorded observation, so it can differ from the agent's `obs-N` (v1 and
  reference views unchanged). Whether a Mechanic now reads such a report correctly is not yet measured. Details:''',
 '''  `cited_tokens_not_decoded` instead of `cited_unshown_labels`. A new v2 registration records this rule in its
  limitations (review fix; the builder's text still said "journal label"). The Mechanic and Explorer never see a
  label the adapter decoded; they see each report's decoded IDs as the episode's `oN` row aliases. A token the adapter
  did **not** decode (a guess such as `obs-4`) reaches them as written. That view is unchanged for the same citations
  (the hidden first attempt is still a recorded row, so a report citing only what the agent saw still skips it, e.g.
  o1, o2, o4). What changed for them is only the v2 contract text: it now says unseen observations exist and get no
  label, and that `oN` counts every recorded observation, so it can differ from the agent's `obs-N` (v1 and reference
  views unchanged). Details:'''),
('''* **Checks run by the builder (one `scripts/test.sh` after the last code edit, `builder/full-test-sh.log`):** backend
  **2,867 passed, 180 skipped, 0 failed** (43 more than `ac7a12d2`'s 2,824); frontend **338** unit tests (4 new);
  build passed; browser **17 passed, 1 opt-in skip**. Negative controls (`builder/mutation-checks.log`): all 10
  mutations caught. Repo `gate_freeze.py`: referee, promotion, evaluation, actor, actor prompt and progress files and
  `assess_pairs` unchanged. Next: two independent reviews, then register again and a declared live run.''',
 '''* **Not fixed: the September 29 misdiagnosis (review findings P-1, LOW-1; deferred to the PM).** The live
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
  (the docs now say what is and is not shown). FIXER_SUITE_RESULTS
  Next: commit (owner's OK), register every agent again, then a declared live run that exercises rule v2 and the v2.1
  labels, with the misreading check pre-registered.'''),
('''adapter v2, builder) → **`ac7a12d2`** (native adapter v2 review fixes).''',
 '''adapter v2, builder) → **`ac7a12d2`** (native adapter v2 review fixes; committed) → `18292424` (September 30
builder) → `4553ebe7` (September 30 fixer; current, not committed).'''),
]
for old, new in edits:
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)
p.write_text(s)
print('edited')
