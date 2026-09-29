# Clean-install validation (2026-09-29), fresh local clone of backup/part2-2026-09-22

Written by the PM from the install agent's returned report. The agent's tool refused a direct file write. Raw logs are in `install/logs/`.

## Report

I did not write REPORT.md. The tool refused it with "Subagents should return findings as text, not write report files", so the full report is this answer. The raw logs and helper files are saved in /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-install-and-task2-2026-09-29/install/logs/ (numbered 01-19, including two dashboard screenshots) and .../install/workarounds/.

SHORT ANSWER
The install itself works. With the documented Python 3.12.8 and Node 20.19.0 (npm 10.8.2), ./scripts/setup.sh finished in 31 seconds with no errors. Every product test that does not need the owner's private files passed. The frontend, build, browser tests and offline demo all worked; the demo passed all 8 checks and made 0 model calls.

But the documented ./scripts/test.sh fails in a fresh clone. 9 backend tests fail and 24 error, and all 33 come from 2 files that git ignores, so a clone does not have them:
- artifacts/phase16-2026-09-22/settings-phase17.json
- artifacts/phase22-2026-09-24/gate-freeze-after.json

I copied those 2 files into the clone for a moment, ran the same 33 tests, and all 33 passed. Then I removed them. So this is a test-packaging problem, not an install bug. Because test.sh stops at the first failure, a new developer never sees the frontend, build or browser results.

The second big finding: the ports cannot be changed. 8000, 8001 and 5173 are hardcoded in the launcher, the three start scripts, the Vite config, the Playwright config, and the CLI used by 6 scripts. So I could not run the start and demo commands exactly as written. I kept the repository's own code and only changed the port numbers.

Cost was $0: no provider, model or W&B calls, and .env was never read. I did not open checks.py, artifacts/heldout2/, audit/promotion.json or any final-audit file. I edited nothing in the main workspace except creating the report folder.

SETUP USED
- Machine: macOS 27.0.1, arm64.
- Clean folder: /Users/shree/FaultLab_CleanInstall_0929. It did not exist before; it is 551 MB now.
- Clone: branch backup/part2-2026-09-22, HEAD 60192d9.
- python3.12 is a pyenv shim that gives 3.12.8, matching .python-version. The right interpreter was available, so that is not a finding.
- Node v20.19.0 via nvm, npm 10.8.2, Google Chrome installed.
- Another workflow was running at the same time, so timings may be a little slow.

COMMANDS, TIMINGS AND RESULTS
0. mkdir, then git clone --branch backup/part2-2026-09-22 --single-branch <main workspace> <clean folder>/faultlab. 1 s.

1. ./scripts/setup.sh. 31 s, succeeded.
   - Installed 99 locked Python packages from PyPI.
   - npm ci installed 111 packages with 0 vulnerabilities.
   - pip check was clean, and the installed packages exactly match requirements.lock.
   - It also quietly created .env, a 0600 copy of .env.example. I moved that copy out of the clone, so every later step ran with no .env.

2. Backend tests. 897 s (about 15 minutes).
   - Command: cd backend && env -u WANDB_API_KEY WANDB_MODE=disabled ../.venv/bin/python -m pytest -rs -q -p no:cacheprovider. The extra flags only print skip reasons and keep the clone clean.
   - Result: 9 failed, 2,599 passed, 199 skipped, 24 errors, and the 2 known warnings.
   - 2,831 tests were collected. The documented 2,651 passed + 180 skipped also adds up to 2,831, so the same tests ran.

3. The 7 affected test files on their own: the same 9 failures and 24 errors every time, in 11 s. With the 2 ignored files present, the 33 failing tests all pass in 4 s.

4. npm test: 312 passed in 18 files, 4 s. This matches CURRENT_STATUS exactly.

5. npm run build: succeeded in 1 s. It warns that the 559 kB bundle is large, which the docs already mention.

6. Browser tests: 15 passed and 1 opt-in test skipped, 25 s. This matches CURRENT_STATUS. I used a copy of the repo's Playwright config changed only to port 15173 and reuseExistingServer:false.

7. Offline services. I started the simulator and backend the way start-local.sh does, but on ports 18001 and 18000, with a new data folder under /Users/shree/FaultLab_CleanInstall_0929/data. The folder was created automatically. Readiness reported the simulator ready, live mode not configured, and 0 provider calls.

8. The documented demo (run-demo.sh --mode baseline --wait), run through the same CLI code with only its address changed to port 18000. 1 s.
   - Campaign campaign-59058be5... finished COMPLETED.
   - The episode passed all eight checks (C1-C8) as an offline fixture, with 0 model calls.

9. The opt-in real-backend browser test from docs/setup.md (FAULTLAB_BROWSER_LOCAL=1, "actual local offline smoke"): 1 passed, 5 s. It clicked Create and then Start, got the "Offline reference smoke" row, and the result survived a reload and read-only playback.

10. A second backend on the same store: /api/health still says OK, but real requests get 409 STORE_IN_USE, as the docs say.

11. Archive-mode restart: both saved campaigns were still listed, readiness said READ_ONLY_ARCHIVE, and the database file was unchanged. My write test does not prove writes are blocked: the request was rejected as malformed (422) before that check.

12. The repo's own launcher code (launch_plan, check_ports, supervise) with only the ports changed. The dashboard showed "Backend connected", the data folder path and no console errors. Ctrl+C stopped all 3 child services in 1 s.

What I did not run exactly as written:
- ./scripts/test.sh: its backend stage fails in a clone, and its browser stage would start a server on 5173.
- start-local.sh, start-*.sh and run-demo.sh: they only use the fixed ports.

What I did not test: GitHub CI, a machine without Chrome, Linux or Windows, and live mode.

WHAT MATCHED THE DOCS
- Tool versions, pip check, and 0 npm vulnerabilities.
- Test counts: 2,831 backend, 312 frontend, and 15 browser plus 1 opt-in.
- The offline demo passed all eight checks with 0 model calls.
- Data folder creation, restart persistence, archive mode, store lease and a clean Ctrl+C shutdown.
- The tests wrote nothing into the clone's artifacts/ folder.

CURRENT STATE
- The clean install is still at /Users/shree/FaultLab_CleanInstall_0929:
  - the clone, with .venv, node_modules and a build
  - two scratch data folders under data/
  - the template .env that setup created, now named setup-created-template.env
  - my two untracked alternate-port configs under frontend/

  You can delete the whole folder when you no longer need it.
- No services are running, and nothing is listening on 18000, 18001, 18010 or 15173.
- Ports 8000, 8001 and 5173 were never used.
- Nothing was committed or pushed.

## Findings

- A1 [HIGH, missing git-ignored files, not an install bug] 33 backend tests hard-require two git-ignored files. They fail or error instead of skipping. 31 need artifacts/phase16-2026-09-22/settings-phase17.json (30 FileNotFoundError, plus 1 wrong-message failure in test_report_narrow_probe.py:99). 2 need artifacts/phase22-2026-09-24/gate-freeze-after.json (test_run_full_loop_fixed_n.py:179 and test_run_heldout2_check.py:31/378). Per file: test_lapse_probe 1 error/1 failure (fixture line 1018, test 1706); test_report_narrow_probe 11/2 (1086; 99, 275); test_report_word_probe 6/2 (1388; 263, 279); test_slot2_hidden_probe 1/1 (190; 323); test_slot2_probe 5/1 (91; 349). With the two files present, all 33 pass (logs 04, 05). Fix: skip them like their sibling tests already do ('needs the Phase 17 settings file'), or commit the two small non-secret files, as was done for artifacts/phase28-2026-09-26/*.
- A2 [INFO] A clone shows 199 skips instead of the documented 180. All 199 are in backend/tests/experiments, and every skip reason is about the owner's local stores, frozen trees or settings files. The extra 19 come from the same missing files.
- A3 [HIGH, consequence of A1] test.sh uses set -e, so it stops after the backend stage and a new developer never gets frontend, build or browser results. The GitHub 'Offline checks' workflow runs the same setup.sh and test.sh on a fresh checkout, so it will very likely fail the same way. Its timeout-minutes: 20 is also likely too short: the backend stage alone took 15 minutes here on Apple silicon (not run on CI; both points are inferred).
- B1 [HIGH] Ports cannot be changed. Fixed in: backend/app/local.py (8001/8000/5173, and the simulator URL forced to :8001); start-simulator.sh, start-backend.sh and start-live-backend.sh; frontend/vite.config.ts (5173 strictPort, /api always proxied to :8000); tests/playwright.config.ts (baseURL 5173 with reuseExistingServer:true); backend/app/cli/client.py (BASE_URL fixed to :8000, used by run-demo, export-evidence, run-audit, run-baseline-study, run-completion-study and run-context-study). You cannot run a second checkout next to the main workspace. Hazard: a second checkout's run-demo.sh or export-evidence.sh will act on whatever backend owns :8000, and the browser tests silently reuse any dashboard already on :5173. Fix: port settings or flags, an --api-url option for the CLI, a proxy target and baseURL read from the environment, and reuseExistingServer:false.
- C5 [HIGH for a new developer] The documented product exists only on the local branch backup/part2-2026-09-22, which is 44 commits ahead and never pushed. Local main and origin/main are at cbbf957 (2026-09-14). Anyone who clones GitHub gets code that matches none of these docs.
- D1 [MEDIUM] The README start method differs from the user guide. README 'Run it yourself' uses the old three-terminal scripts, which store data in the default repo artifacts/ folder. In a clone that folder already holds 78 force-added tracked evidence files. user-guide.md and local-operation.md instead say to use start-local.sh --data-dir. That gives two different start methods and store locations.
- D2 [MEDIUM] docs/setup.md is a dated history log; the actual commands are buried at line 187. Test counts contradict each other: setup.md top says 2,224 backend / 219 frontend, CURRENT_STATUS says 2,651 / 312, and README Phase 1 says 422 / 34. No doc tells a new developer the backend stage takes about 15 minutes, or that experiment tests skip (and some currently fail) in a clone.
- C1 [MEDIUM] Absolute paths to the owner's machine: user-guide.md section 1 ('cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab' and '--data-dir /Users/shree/FaultLab_Runs/my-workspace'); CURRENT_STATUS 'App root'; scripts/experiments/check_reachability_caller.py:46 (its test skips cleanly); /Users/shree paths inside backend/tests/fixtures/c701e850_explorer_outputs.json.
- C2 [MEDIUM] user-guide.md tells readers to open campaign IDs (ba37f756, 9bc991df, 9a412c88, 3f20fcd4, 892eee83, cd872e2d, 65e356eb, add97a95, 5a0af912, c59a93f8, 1c19ec5b), an execution ID (dcf7936a) and 127.0.0.1:8000 study links that exist only in the owner's local store. A fresh install shows 'No saved campaigns yet'. Only the Phase 2 command section warns about this.
- C3 [MEDIUM, live only] Live instructions in user-guide.md section 2 and setup.md hardcode the owner's W&B entity 'shreetbohara-quinstreet' and project 'Faultlab'. They should use placeholders.
- C4 [LOW-MEDIUM] Links to files a clone lacks: CURRENT_STATUS.md has 9 broken markdown links (8 into git-ignored artifacts/, 1 to the sibling ../FaultLab_Specs/specs/001-faultlab-loop/tasks.md). Paths written in backticks that are missing from the clone: setup.md 4, user-guide.md 1, CURRENT_STATUS.md 11 (for example the budget ledgers and artifacts/product-retry-2026-09-29/fixer/). README, local-operation.md and the markdown links in setup.md and user-guide.md are all fine.
- B2/D5 [LOW-MEDIUM] setup.sh quietly creates .env as a 0600 copy of .env.example. The README only says to copy it yourself for live work, and no doc says setup already does it. The whole offline path worked with no .env at all.
- B3 [LOW] The README lists Python, Node and npm but not the browser-test need for Google Chrome or 'npx playwright install chromium'; only docs/setup.md mentions it. Not reproducible here because Chrome is installed.
- B4 [LOW] The README says 'Node 20.19 or newer', but package.json engines is ^20.19.0 || >=22.12.0, which excludes 21.x and 22.0-22.11. .nvmrc pins 20.19.0 while CI uses Node '22' with no minor version.
- B5 [LOW] requirements.lock has exact versions but no hashes, so pip does not check downloaded files. B6 [LOW] A second backend on a store it cannot own still answers /api/health with 200; only real store requests return 409 STORE_IN_USE. The docs are accurate, but a startup check would be clearer.
- OK: Everything else behaved as documented. Python 3.12.8 and Node 20.19.0 were available; setup.sh took 31 s; pip check was clean; installed packages equal the lock; npm had 0 vulnerabilities. Frontend 312 tests in 18 files, build OK, browser 15 passed plus 1 opt-in skip, all matching CURRENT_STATUS exactly. The offline demo (on ports 18000/18001) COMPLETED with checks C1-C8 passing and 0 model calls. The real-dashboard Create then Start browser test passed. Saved campaigns survived a restart, archive mode reported read-only, a second owner got STORE_IN_USE, and the launcher logic stopped all services cleanly on Ctrl+C.
- PRIORITISED FIXES (none applied): 1) Make the 33 A1 tests skip when their file is missing, or commit the two files. 2) Push or publish the current source, or document which branch to use (C5). 3) Make ports settable everywhere and stop reusing an existing server (B1). 4) Raise or split the CI timeout and pin Node (A3, B4). 5) Write one short install section and link it from the README: setup, test, expected counts, the ~15-minute backend run, skips in a clone, the Chrome/Playwright need, start-local.sh with a data folder outside the repo; move the history out of setup.md (D1, D2, B3). 6) Replace /Users/shree paths and the owner's W&B entity with placeholders (C1, C3). 7) Label the owner-store-only IDs and links, and fix links into ignored artifacts/ and FaultLab_Specs (C2, C4). 8) Minor: document or stop the automatic .env copy, consider hashed requirements, report STORE_IN_USE at startup (B2, B5, B6).
