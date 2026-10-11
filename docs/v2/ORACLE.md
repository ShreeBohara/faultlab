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

What v1 does not do yet: free-text reports (no model extraction, so no agreement statistic to
report), calibration by fault phase, and the other packs. Those are the rest of phase 1.9.
