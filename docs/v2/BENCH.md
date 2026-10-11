# faultlab-bench (first artifact)

Stage 2 of the plan; the first piece exists because the Claude Actor screen produced real
multi-provider data. `bench/harness/leaderboard.py` turns a directory of run stores
(`<name>/lab.sqlite3`) and envelope bundles (`*.zip`) into one board:

```bash
./.venv/bin/python -m bench.harness.leaderboard ~/FaultLab_Runs/2026-10-11/claude-actor-screen --out leaderboard.json --markdown leaderboard.md
```

Per model and adapter family: executions and task outcomes, violation and completion rates,
false-belief and conformance rates from the belief-versus-effect oracle, fault exposure
(configured, triggered, unreachable), per-scenario counts, tokens and measured dollars. Every
rate carries its 95 percent Wilson interval and its n. Nothing is ranked: the bench shows what
each agent did under each fault, with the uncertainty, instead of hiding it behind one number.

What the bench will add (Stage 2): scenario matrices per pack and fault family, a repetition
policy that stops at a declared interval width, cost accounting per run, reproducibility bundles
for every row, and the periodic Agent Fault Report built from the board.
