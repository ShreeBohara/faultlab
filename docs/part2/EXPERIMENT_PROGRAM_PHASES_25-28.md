# Experiment program, Phases 25–28 (re-plan after Phase 24). September 24, 2026

This replaces Phases 25–27 of `EXPERIMENT_PROGRAM_PHASES_20-27.md`. The project owner approved
the direction ("go ahead with whatever you recommend"). Every phase is still declared, reviewed
twice, approved on its own, run once, and reported honestly.

- **Budget:** $600.65 charged, **$399.35 remaining**.
- **Scope:** all three probes use **development data only**. heldout-2 is spent and is never read
  or used to shape anything (`PHASE22_EXPERIMENT.md` §7.5).
- **Configuration:** no phase edits `backend/app`, so the Phase 22 configuration `2cf63e93…`
  and freeze `8994e962…` stay valid.

## Why these three

Phases 23–24 located three constraints:
1. **The Mechanic's slot 2 repeats slot 1** in 16 of 30 studies. That is half of every study's
   proposal budget, and the largest yield lever left.
2. **Upgrade-side gaps no generated repair closes.**
   - On transient upgrade failures (F4 on `update_order`) the baseline completes about 7% and
     the certified repairs 0 of 45 (Phases 18, 20, 24). This is descriptive.
   - Long F2 delays (d ≥ 16) are 0 for both arms.
   - If a legal policy completes them, the loop has a second repair class it could learn.
3. **The Actor's report-word slips.** A report said `PENDING` where every observation said
   `UNKNOWN`. That decided Phase 24's HARM, and Phase 21 measured about 7% PENDING on report
   turns. This slip now blocks held-out certification.

## Phase 25: Mechanic slot-2 probe (non-scoring replay; cap ~$15)

- **Question:** why does slot 2 reproduce slot 1, and does one declared change to the slot-2
  input produce distinct, step-containing and step-firing proposals, without breaking validity?
- **Method:**
  - Rebuild stored slot-2 Mechanic requests (v4-era completion studies, including Phases 17
    and 23) byte-exactly from the store. Verify each against its stored hash.
  - Arms: C (exact re-send), a temperature arm, and an arm that changes how the prior candidate
    appears in the slot-2 input (the planning review found the duplicates come from copying
    `candidate_history`; confirm or refute this from the code first).
- **Read-outs:**
  - byte-identical-to-slot-1 rate;
  - distinct valid policies;
  - step present;
  - step that can fire after a transient failure: a static check of its gating condition
    (pitfall 77);
  - a side-rule audit.
- **Statistics:** contrasts with intervals, declared.

## Phase 26: second completion gap probe (live development episodes; cap ~$25)

- **Question:** can a legal **manual-reference** policy complete the upgrade-side cases the
  baseline and the certified repairs do not?
- **Arms:**
  - **B0:** the empty baseline.
  - **MR:** the manual-reference policy, labelled `manual-reference`; never shown to the
    Mechanic, never promoted, never certified.
  - **L:** one certified Phase 23 repair, as a descriptive development replication of the
    transient-upgrade pattern. `711bddb6…` may be used on development cases now that its
    heldout-2 verdict exists.
- **Cases (development):**
  - F4 on `update_order`, counts 2–4;
  - F2 SUCCEEDED long delays: d5, d8 and d12, plus the longest one reachable within the budgets.
- **Read-outs:**
  - completion by family, MR against B0, with an exact test;
  - safety (every C1–C8 failure, per arm);
  - the mechanism from the event log.
- **Meaning:** a positive result names a candidate **source family** for a future loop. It is not
  a repair of anything.

## Phase 27: Actor report-word probe (non-scoring replay; cap ~$25)

- **Question:** on report turns where an operation's latest observation is `UNKNOWN`, how often
  does the Actor write a word no observation supports, such as `PENDING`? Does one declared,
  windowed context field (for example, "last observed status per operation") reduce that
  without changing the report words in other contexts?
- **Method:**
  - Build a new harness from `lapse_probe.py`'s pinned prompt rebuild and hash verification.
    The Phase 21 harness itself is pinned to configuration `0a33aa51…` and must not be
    reused as is.
  - Arms: C, T and a placebo P.
  - Guard populations cover every other true-status context (PENDING, SUCCEEDED, FAILED, and
    NOT_STARTED/NOT_REQUIRED). Phase 4's regression came from exactly this kind of change.
- **Read-outs:**
  - the unsupported-word rate, C against T, with an exact test and a declared threshold;
  - a guard on every other word;
  - determinism repeats to size the noise.
- **Adoption:** a passing field is recommended for a later loop, never used in a run that
  compares against earlier phases without its own declaration.

## Phase 28: event write-up and demo ($0)

The honest story from Phase 16 through the last phase run: what worked, what failed, and what
is still not shown.
