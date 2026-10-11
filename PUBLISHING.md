# What is public, what is not

Status: checklist for the owner (Shree) to sign before the first push after the v2 reset. Prepared 2026-10-10.

## Already public

- GitHub `ShreeBohara/faultlab`, branch `main`, has been public since the hackathon (September 2026). Its tip is `c4780cb` (October 5, 2026: one docs commit adding a Mermaid acceptance-path diagram to `docs/architecture.md`).
- The `audit/` partitions (`development.json`, `promotion.json`, `final-audit.json`, `portability.json`, `search-comparison.json`, `freeze.json`) are tracked and have been public on `main` since September 12. "Private" in the project's vocabulary meant "never shown to the runtime agents," not "secret." Both held-out partitions are spent for the orders task. No change needed.

## What the first push after the reset adds

- Everything on the local branch `backup/part2-2026-09-22` as of commit `0cdfa0cd` (tag `pre-v2-2026-10`): the Part 2 research docs (`docs/part2/`), the product and live-run write-ups, the memory notes, the taskpacks, the experiment scripts, the October 8 handoff, the October 8-10 increments, and 2,461 small evidence files under `artifacts/` that earlier phases tracked on that branch (declarations, results, review reports, ledgers).
- A secret scan over all 631 paths changed on October 10 found 0 hits; `.env` and every credential pattern in `.gitignore` are excluded; `.env.example` has blank keys.
- Absolute owner paths (`/Users/shree/...`) remain in 52 tracked docs, tests and scripts and in 565 tracked evidence files. They reveal the macOS username, which matches the public GitHub handle, and nothing else. Decision: leave them; new documents use `~` or repository-relative paths.

## Never published

- `.env`, API keys, tokens, `.netrc`, `.pem`, `.key`, `credentials*.json`, `secrets*.json` (all in `.gitignore`).
- The large evidence stores: `artifacts/lab.sqlite3` and every world and run database, `~/FaultLab_Runs/`, the 6 GB `artifacts/` tree beyond the tracked small files. These stay local and in `~/FaultLab_Backups/`.
- The W&B entity and project names stay out of docs (the team's; users supply their own).

## How the push will be done

1. Work happens only in the off-iCloud clone `~/FaultLab/faultlab`; the Desktop folder is the archive.
2. Merge the October 5 docs commit from `origin/main` into the working branch so GitHub's one change is not lost.
3. Push the working branch, then fast-forward `main` to it on GitHub.
4. Push the tag `pre-v2-2026-10`.
5. Enable GitHub Actions (the existing `ci.yml` has never run) and record its first result.

## Owner sign-off

- [ ] I understand that everything listed under "What the first push adds" becomes public.
- [ ] I confirm no credentials live in the tree (secret scan: 0 hits on 2026-10-10).
- [ ] License: Apache-2.0 for the whole repository.

Signed: ____________________ Date: __________
