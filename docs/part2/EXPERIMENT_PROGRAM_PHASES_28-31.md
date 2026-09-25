# Experiment program, Phases 28–31 (re-plan after Phase 27). September 25, 2026

The project owner approved the direction ("go ahead with whatever u recommend", 2026-09-25).
Every phase is still declared, reviewed, approved on its own, run once and reported honestly.

- **Budget:** $652.90 charged, **$347.10 remaining**.
- **Scope:** development data only. heldout-2 is spent and is never read.

## Phase 28: can the loop learn the upgrade-side repair? (the main experiment; cap ~$100–150)

**Why:** Phase 26 showed a legal policy closes a second completion gap:
- on F4 transient upgrade failures and long F2 upgrade delays, "wait, then re-send the upgrade"
  (`retry_original_request` on orders) completes 36 of 36, against the baseline's 1 of 36;
- the loop's certified repairs never re-send the upgrade (0 of 63 against 9 of 63 across four
  data sets).

The loop has only ever been pointed at notification-side gaps.

**Question:** run with an upgrade-side source case, does the full loop (Explorer, Mechanic,
source gate, validation) produce and certify a repair that re-sends the upgrade? How often?

**Design first ($0):** establish from the code what running a completion study with a different
source case requires:
- the manifest, its hash and the configuration pin;
- the certification rule's case names;
- the Mechanic brief;
- whether `backend/app` must change, which means a new freeze and configuration.

Then declare a fixed-N design (no stop at success), a certification rule that is the Phase 17
rule transposed to the new source (never loosened), routing, and a spend cap. A held-out check
of a certified upgrade repair would need a **new** partition. If one is wanted, it is declared
separately and sealed before the loop runs, as in Phase 22.

## Phase 29: Mechanic slot 2 with the prior candidate hidden (replay; cap ~$15)

**Why:** Phase 25's descriptive reference arm N, with no prior candidate in view, never
rewrote slot 1's policy (0 of 26, one draw per prompt). The declared arms did not meet their
bars.

**Question:** as a declared arm with repeats, does hiding the prior candidate from slot 2 cut
duplicates and raise working proposals without raising invalid output? A second arm hides it
**and** uses a moderate temperature.

**Method:** a new harness reusing `slot2_probe.py`'s verified request rebuild (import, never
edit). Concurrent control C. Contrasts and exact tests declared in advance.

## Phase 30: a narrower report-status field (replay; cap ~$20)

**Why:** Phase 27's field removed the `PENDING` slip (0 of 225 against 4 of 225). It failed
the guard because on terminal-rejection turns the Actor stopped filing its correct
`FAILED/NOT_REQUIRED` report and polled again (23 of 45).

**Question:** does a field shown **only** when an operation's latest status is `UNKNOWN`, and
never on terminal-rejection turns, keep the slip at or near 0 **and** pass every guard?

**Method:** reuse `report_word_probe.py`'s verified rebuild (import, never edit). The guard
populations are the same as Phase 27's. The primary is declared with honest power: at 4 of 225
baseline events, a reduction cannot be shown at this size. So the declared primary is **the
guard plus non-inferiority on slips**, stated plainly.

## Phase 31: event write-up and demo ($0)

The honest story from Phase 16 onward. It is written last.
