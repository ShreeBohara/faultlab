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
- New documents keep the W&B entity and project names out (users supply their own). The entity name itself has been public since September in nine hackathon-era docs on `main`, and the research docs and evidence files on the working branch mention it in 90 more; it is a team name, not a credential, so it stays.

## How the push will be done

1. Work happens only in the off-iCloud clone `~/FaultLab/faultlab`; the Desktop folder is the archive.
2. Merge the October 5 docs commit from `origin/main` into the working branch so GitHub's one change is not lost.
3. Push the working branch, then fast-forward `main` to it on GitHub.
4. Push the tag `pre-v2-2026-10`.
5. Enable GitHub Actions (the existing `ci.yml` has never run) and record its first result.
   Recorded 2026-10-11: the first run, on the pushed commit `fca3502b`, succeeded (backend tests and the
   frontend, build and browser job; 21 minutes 50 seconds).

## Pre-push audit (2026-10-10, night)

Run over all 81 commits that the push publishes (`origin/main..HEAD`), by the agent, before pushing:

- Exact-value search for every credential in the owner's `.env` (W&B key, Anthropic key, control token): 0 commits match.
- Credential-shaped patterns (`sk-...`, `sk-ant-...`, AWS, GitHub, Slack tokens, private keys, bearer headers, key assignments):
  the only matches are the placeholder `sk-000...0001` in the golden native requests and `task-<32 hex>` record ids whose
  tail happens to spell `sk-`; nothing else.
- The seven tracked `settings.env.txt` snapshots under `artifacts/product-native-v2-2026-09-29/` are empty files.
- The two tracked `probe-ledger.sqlite3` files hold probe records and no key-shaped strings.
- `artifacts/heldout2/` never appears in the history; the `audit/` partitions were already public.
- Largest blobs 7.5 MB (tokenizer files already public); pack 35 MB.

## Owner sign-off

- [x] I understand that everything listed under "What the first push adds" becomes public.
- [x] I confirm no credentials live in the tree (secret scan: 0 hits on 2026-10-10; pre-push audit above).
- [x] License: Apache-2.0 for the whole repository.

Signed: the owner authorized the push in chat on 2026-10-10 ("go ahead with your recommendation", after the
recommendation "publish, then start Stage 1"); the agent ran the audit above and pushed the same night.
