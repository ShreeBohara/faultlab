You are taking over FaultLab end to end as the project lead. You decide what to do next. I am the owner (Shree).

**Repo:** `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.

**Read these first:**
1. `HANDOFF_2026-10-08.md`: all of it, especially §0 (git) and §5 (rules).
2. The top of `CURRENT_STATUS.md`.

Where `AGENTS.md` conflicts with the handoff, the handoff wins.

**Git warning:** the folder is deliberately checked out on `main` (`cbbf957`). All newer work sits in the working tree
as uncommitted changes that match the local branch `backup/part2-2026-09-22`.
- Never checkout, commit on main, reset, stash, clean or `git add -A`.
- Commit only with `artifacts/phase22-2026-09-24/prep/commit_to_backup.sh`.
- `artifacts/` and `/Users/shree/FaultLab_Runs/` are not in git. Never delete them.

**Goal:** a complete, dependable product. The main open milestone is FaultLab's first ACCEPTED generated policy for
the external smolagents agent.
- Generated guardrails have passed source validation, and their challenges showed 0 failed checks.
- But every challenge ended INCONCLUSIVE (a fault did not fire), so none has passed yet.
- The current bottleneck is the diagnosis step. Its fix ("Rule 2") is built and awaits one small declared probe.

**Rules:**
- **Secrets:** never print, copy or commit `.env` or credentials.
- **GitHub:** no push without my OK (GitHub `main` is public).
- **Billing:** never touch billing.
- **Protected data:** never open `backend/app/referee/checks.py`, `artifacts/heldout2/`, `audit/promotion.json` or
  `audit/final-audit*.json`, and never tune on private or held-out data.
- **Gates:** never weaken gates, checks or thresholds. Never restart or re-run something until it passes.
- **Paid runs:** declare every paid run before starting it, and keep the ledger running from $937.99.
- **One agent at a time:** never work while another agent is on the repo.

**Billing:** the W&B free trial ends **Oct 12, 2026**, and inference has a $100/month included allowance. I added
credits, but this is unconfirmed. Make one cheap test call first; if you get HTTP 402, stop and tell me.

**How to report:** short, plain-English updates. Never say something works without saved evidence. Tell me plainly
when something fails or when you were wrong.
