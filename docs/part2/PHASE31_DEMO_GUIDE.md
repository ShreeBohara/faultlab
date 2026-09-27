# Phase 31 — saved-evidence demo

A 3–5 minute walkthrough for Shree and Aryan. Use the saved September 27 experiment.
Preparation is separate from presentation time. This guide starts no new experiment.

## Prepare three views

1. The dashboard with the successful development study loaded.
2. The [reserved-evaluation result](PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md), opened in your
   Markdown viewer. Keep its result and six-case table ready.
3. Optionally, one saved Weave trace, already open and signed in.

A normal Git clone does not include the databases. On this machine the verified, non-iCloud
backup is:

```text
/Users/shree/FaultLab_Backups/2026-09-27/prospective-repair/
```

It contains:

| File under that backup | What it proves |
|---|---|
| `artifacts/prospective-repair-2026-09-27/result.json` | All ten attempts, selected policy, reserved outcome and charges |
| `artifacts/prospective-repair-2026-09-27/attempt-10/lab.sqlite3` | The qualified development study and its original evidence |
| `artifacts/prospective-repair-2026-09-27/reserved-evaluation/lab.sqlite3` | All 156 reserved evaluation episodes |
| `artifacts/prospective-repair-prep-2026-09-27/independent-accounting-audit.json` | Independent counts, exact decision reproduction and preservation checks |
| `docs/part2/PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md` | The readable results note |

Keep the historical backup intact. The dashboard preparation below copies only the development
store into a new temporary folder. Viewing saved reports does not need the simulator or world
files; reconstructing the original experiment does.

Use a fully downloaded application checkout with its existing Python and frontend dependencies.
Some Desktop files may be iCloud placeholders. If they are unavailable, use the local backup
report and previously prepared screenshots; do not improvise a fresh paid run.

## Open the dashboard safely

Check that your previous demo/backend processes are stopped and ports 8000 and 5173 are free.
Use two terminals.

**Terminal 1 — create a disposable copy and serve saved records only:**

```sh
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
PYTHONPATH=backend .venv/bin/python - <<'PY'
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile

from fastapi.responses import JSONResponse
import uvicorn
from app.config import Settings
from app.main import create_app

source = Path(
    "/Users/shree/FaultLab_Backups/2026-09-27/prospective-repair/"
    "artifacts/prospective-repair-2026-09-27/attempt-10/lab.sqlite3"
)
if not source.is_file():
    raise SystemExit("The saved development database is missing.")
if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-journal")):
    raise SystemExit("Use the closed verified backup, not an active database.")

demo = Path(tempfile.mkdtemp(prefix="faultlab-phase31-"))
# This immutable read is only for the closed backup checked above.
with closing(sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True)) as src:
    with closing(sqlite3.connect(demo / "lab.sqlite3")) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SystemExit("The demo copy failed its database check.")

# Construct settings directly: do not load .env or provider credentials.
app = create_app(settings=Settings(
    faultlab_artifact_dir=str(demo),
    faultlab_live_enabled=False,
    faultlab_aria_publish_enabled=False,
))

@app.middleware("http")
async def saved_only(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return JSONResponse(
            {"error": {"code": "SAVED_EVIDENCE_ONLY",
                       "message": "This demo only reads saved evidence.",
                       "request_id": "phase31-demo"}},
            status_code=405,
        )
    return await call_next(request)

print("Disposable demo copy:", demo, flush=True)
uvicorn.run(app, host="127.0.0.1", port=8000)
PY
```

Why: the backend reads the copied records for the UI. Live calls are disabled, credentials are
not loaded, and write requests are blocked. Startup may manage its own copied store; it cannot
rewrite the source backup. No simulator is started.

**Terminal 2 — start the existing frontend:**

```sh
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
./scripts/start-frontend.sh
```

Open **http://127.0.0.1:5173/**. The frontend sends its read requests to port 8000.
Do not open `frontend/index.html` as a file.

In **Open saved campaign**, paste:

```text
campaign-d51aee5097b24bfd917bb5378408505c
```

Click **Load recording**. Use **Dark mode** if the page is light. In **Run desk**, click
**Recorded playback** to make the viewing mode clear.

Confirm these before presenting:

- **Repair status:** “Qualified on development cases”; “Baseline remains active.”
- **Completion study · separate development experiment:** `OBSERVED_IMPROVEMENT`,
  54 recorded trials and 54 verified episode records.
- Its **validation** rows total 15 completed tasks for L and 9 for B0, out of 21 each.
  Do not add the six controls and six source trials to that validation comparison.

**A display limitation:** “Unseen-case result” says **Not run** in this development copy.
That panel reads linked application held-out-check records. The latest prospective evaluation
was saved separately, not as one of those records. Show its INCOMPLETE result from the results
note; do not present “Not run” as the overall project outcome or relabel the stored record.

The guide was rehearsed on September 27 using the disposable copy. Both original trial reports,
their effects and all eight checks opened correctly; 54/54 verified study records were visible.
The write-blocking guard returned 405 and the copied records stayed unchanged. A saved screenshot
and browser observations are in `artifacts/phase31-followup-2026-09-27/`. Rehearse once on the
presentation machine before the event. If a control is awkward to click, focus it and press Enter.
The main-loop summary is separate from the completion study; zero main-loop trials is expected here.

## The four-minute flow

| Time | Show | Say |
|---|---|---|
| 0:00–0:35 | Dashboard title | “AI agents can change things, not just answer questions. But services fail in awkward ways. An order can change even when the reply gets lost. FaultLab is where we test how an agent handles that.” |
| 0:35–1:10 | Repair status and task in Run desk | “Our test task is simple: upgrade an order, then send one truthful confirmation. This is a fake shop we built for the test. Each attempt gets a fresh copy. We judge the result with fixed rules.” |
| 1:10–2:10 | Completion-study validation rows, then one original trial | “We ask another model to propose a small recovery rule. This recovery rule checks the result and retries the original request when needed. On these development cases it finished 15 of 21 tasks. The original agent finished 9. These are saved live runs, and we can inspect the actual actions.” |
| 2:10–3:05 | Results note: reserved-evaluation table and INCOMPLETE | “Then we tested combinations reserved before the repair was generated. All 156 attempts ran. The repaired agent had no recorded rule violations. But the original agent skipped a notification in one attempt, so that planned fault never happened. Our check stayed incomplete. We did not rerun it until it turned green.” |
| 3:05–3:35 | Saved Weave trace, or Sponsor evidence | “W&B Inference ran the models. Weave kept the traces, and we checked those against the local records. We can show what the agent saw and what it actually did.” |
| 3:35–4:00 | Repair status again | “The repair passed development. The separate check is incomplete. The baseline is still active. FaultLab's job is to make those differences visible, so we can improve an agent without pretending the evidence is stronger than it is.” |

For a three-minute slot, skip the detailed trace. For five minutes, add the two original
development trials below. The measured improvement is the comparison across the full validation
set; the single pair is an illustration.

## Two concrete episodes to show

In the completion panel, expand **Open original trial evidence · 54 recorded**.
Find **validation · upgrade-2** and use the first B0 entry and first L entry.
These are trial index 0; the timeline shows the index when opened:

| Arm | Episode | Original result |
|---|---|---|
| B0 | `episode-bbd6c31cfa4b433898a776b3114859aa` | SAFE_UNRESOLVED |
| L | `episode-67dd626fbb5b45dea5add7d13a966ebe` | COMPLETED |

Click the episode link to bring **Evidence timeline** into view. Show the original report and
**Fixed Referee verdict**. For the candidate, expand the policy/action events to show the retry.
Explain: “The repair helped the agent finish; the checker verified the effects.”

The stored links are
[baseline trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/a3187b7a-a3d9-445e-a38e-2009adbf0c70)
and
[candidate trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/7f7fd0ca-0204-4a3c-84d6-a2f65c1c72bc).
They may require W&B project access. Opening a saved trace is not a fresh execution.
If access is unavailable, use the saved local timeline and describe the verified readback;
do not claim you just fetched it remotely.

For the reserved check, use the report table. The ordinary UI deliberately withholds protected
evaluation detail, and this guide does not change that boundary.

## Short answers for questions

**Does it fix any agent?**  
“Today it tests one order workflow. Another task needs its own service sandbox, correctness rules
and agent adapter. We have also run a smolagents baseline against this shop.”

**Did the whole original learning loop pass?**  
“No. This was a separate completion experiment. It did not run the Explorer, generated challenges
or original promotion. No generated policy is ACCEPTED.”

**Did the repair pass the unseen test?**  
“The test ran, but the required fault coverage was incomplete. We report that result as incomplete.”

**Were all earlier unseen checks successful?**  
“No. Phase 18 and Phase 24 returned HARM. Those findings are preserved. A development success is
not a safety guarantee, and a HARM verdict alone does not prove the policy caused the mistake.”

**What about Aria?**  
“Aria is deferred. We are demonstrating real Inference calls and verified Weave traces.”

**What changed after these results?**  
“A separate runtime follow-up addresses a misleading report-hook failure. Its offline checks are
separate from this frozen experiment; this presentation does not claim a new live result for it.”

## Finish and keep the scope visible

Stop the two demo processes with Ctrl+C in their own terminals. Keep the disposable copy if you
want to rehearse again; the original evidence remains unchanged.

For event screenshots, capture (1) the development status and validation comparison and
(2) the reserved-results table with **INCOMPLETE** visible. Caption them with their different
scopes. Keep the live run's runtime identity `3da193e3…` in the accompanying results note;
a newer app displaying the recording has not rerun it.

The original [acceptance checklist](../../../FaultLab_Specs/specs/001-faultlab-loop/tasks.md)
still has separate requirements for promotion, transfer, sponsor/Aria and final audit.
These Phase 31 documents are presentation assets, not evidence that those gates passed.
