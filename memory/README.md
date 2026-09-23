# FaultLab handoff memory

Saved September 20, 2026, updated after Phase 15, for continuing in Claude Code. This folder records the current local implementation, experimental evidence, prior decisions and recommended next work. It supersedes earlier handoffs for current status, without replacing their historical evidence.

## Read first

1. `../AGENTS.md` and `../CLAUDE.md`.
2. [Project overview and code map](projects/faultlab.md).
3. [Next phase](context/next-phase.md).
4. [Runtime, budget and evidence](context/runtime-and-evidence.md).
5. [Pitfalls and decisions](context/pitfalls-and-decisions.md).
6. `../docs/part2/PHASE11_RESULTS.md` and its `PHASE11_EXPERIMENT.md`; then `PHASE10_*`, `PHASE9_*`, `PHASE8_*`, `PHASE7_*`, `PHASE6_*`, `PHASE5_*`, `PHASE4_RESULTS.md` (read its Corrections section) and `PHASE3_*` for the rounds before.

Use [the glossary](glossary.md) for terminology. [START_CLAUDE.md](START_CLAUDE.md) is the copyable starting prompt. `latest-session.json` captures the read-only handoff snapshot; process state and budget must be checked again before use.

## Where everything lives

- Application: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.
- Specifications/checklist: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/FaultLab_Specs`.
- Long-term roadmap/research: `../docs/part2/PLAN.md` and `RESEARCH.md`.
- Phase histories: `../docs/part2/PHASE1_RESULTS.md` through `PHASE11_RESULTS.md`, each with its `*_EXPERIMENT.md` protocol and `*_TASKS.md` checklist.
- Local evidence and backups: `../artifacts/phase3-2026-09-20/` through `../artifacts/phase11-2026-09-21/` (including `phase4-followup-2026-09-20/`) and `../artifacts/lab.sqlite3`.

All links above are relative to this memory folder. Open Claude Code in the application directory. These files do not depend on a Codex account or a global Claude memory directory.

## Moving machines

Use the existing full local workspace, including current modified/untracked files and local evidence. The GitHub version does not contain the latest uncommitted work or ignored `artifacts/`. Keep credentials in the existing private `.env`; do not copy them into this handoff or Git. If paths differ on the new machine, find the repository root and use relative paths. Recreate services locally rather than assuming old processes survive a move. Missing evidence means a finding cannot be independently reverified; do not invent it.

The Phase 4 session ran two declared live studies (653 Actor requests, $13.64770 conservative) and preserved every earlier record unchanged. It did not commit, push, deploy, change model settings, activate a policy or modify existing experimental results.
