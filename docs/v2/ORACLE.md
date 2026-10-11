# v2 belief-versus-effect oracle (v1)

Stage 1, phase 1.9, first version. `faultlab/referee/oracle` scores an agent's final report in two
separate ways that the fixed checks fold together:

- **Belief**: does each claim describe the committed effects correctly, as the agent could know them
  from what it was shown? `TRUE`, `FALSE`, `UNDETERMINED` (an honest `UNKNOWN`, or a world that
  committed after the agent's last look) or `NOT_APPLICABLE`.
- **Conformance**: does the report obey the pack's report contract (which label a situation must
  carry, which identifiers may be cited)? Each finding names the fixed check it reproduces.

The orders rules (`faultlab/referee/oracle/orders.py`) are written from the pack's public contract
(the Actor prompt and the one-line public descriptions of C1 to C8), without reading the private
`checks.py`. Agreement with the recorded verdicts is therefore measured:
`python -m faultlab.referee.oracle <lab.sqlite3>` projects every episode of a legacy store into a
trial envelope, scores it, and prints the agreement with the recorded C5 and C6 decisions.

## First results (11 October 2026)

On the four stores of the Claude Actor screen (144 episodes, live and offline arms), the oracle
agrees with the recorded C5 and C6 decisions in 144 of 144 cases, and adds the sentence the checks
cannot say: every Claude report had **true beliefs** (36 of 36 per model); the five violations were
one label rule (`NOT_STARTED` where the contract wants `NOT_REQUIRED` after a rejection) and one
citation rule (a receipt id the agent had read, cited as evidence). DeepSeek's three unresolved
episodes score `UNDETERMINED`: honest uncertainty after a transient failure.

## Validation against the recorded checks (11 October, afternoon)

Scoring every episode of the seven local run stores of 27 to 30 September plus the four screen
stores (712 episodes, reference and native smolagents agents, live and offline arms): the oracle
agrees with the recorded C5 and C6 decisions in 712 of 712 cases. Reaching that number took two
rules the screen data could not reveal and the older stores did: an absent report fails both
rules (as the fixed checks record it), and a terminal or pending claim must cite the delivered
observation that shows it, not merely any delivered evidence (the second half of C6's public
description). The older stores also show the other side of the oracle: the native smolagents
agent had false beliefs in 94 of 254 episodes of the v2b store, where every Claude report had
true beliefs. Reports: `artifacts/plan-v2-stage1/oracle/` (local).

## Validation against the whole research archive

Scoring all 6,667 archived episodes of the September program (reference Actor on DeepSeek V3.1
and Llama 3.3, native smolagents v1 and v2, every phase): the oracle agrees with the recorded
C5 decision in 6,662 cases and with C6 in 6,660, with zero cases where the oracle flags a
violation the checks did not. Getting there added three C5 rules in the contract's own words
(NOT_STARTED after a write attempt; PENDING never shown; NOT_REQUIRED without a delivered
failure) and withdrew one that the checks do not enforce (UNKNOWN without an attempt is
admissible: 118 reports). Four episodes remain where the recorded C6 fails and the public
contract gives no reason; their ids are listed in `artifacts/plan-v2-stage1/oracle/` for review
by someone with access to the private checks. Beliefs across the archive: 4,024 true, 136 false,
2,099 undetermined, 408 without a report.

What v1 does not do yet: free-text reports (no model extraction, so no agreement statistic to
report), calibration by fault phase, and the other packs. Those are the rest of phase 1.9.
