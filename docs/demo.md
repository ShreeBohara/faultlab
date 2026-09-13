# Local demonstration

Run setup and `scripts/test.sh`, then start the simulator, backend and frontend using the README commands.
The dashboard is at http://127.0.0.1:5173. Paste a campaign ID into **Open saved campaign** to replay any
recorded run without spending anything. Nothing on the page is recomputed at view time: every panel reads
persisted records, and stages that never ran are labelled as not reached.

## Recommended demo: replay a saved campaign (about 4 minutes, costs nothing)

Use `campaign-aa79023053da470984118fdb1e9d8138` (DeepSeek V3.1 under test, DeepSeek V4-Pro-0813 as the lab's
Explorer and Mechanic). It is the cleanest end-to-end story and it finished NO_CHANGE honestly.

1. **0:00–0:30 · the task and the trap.** One agent must upgrade an authorized order to express shipping and
   then record one truthful confirmation. The lab injects an upgrade completion delay, so the receipt arrives
   after the agent has used its turns.
2. **0:30–1:00 · Run summary.** Read the six stages top to bottom. This is the whole claim on one screen,
   including what did not happen.
3. **1:00–1:45 · Reproduce & reduce (panel 05).** The failure was reproduced in three fresh trials and reduced
   to a locally minimal five-tick delay. Reduction attempts that failed to reproduce the target are shown too.
4. **1:45–2:30 · Tested diagnosis (panel 06).** A controlled intervention, three paired trials, verdict
   SUPPORTED, kind POLICY_GAP. Say plainly that a supported diagnosis permits a candidate, never a promotion.
5. **2:30–3:15 · Recovery policy (panel 03).** Switch the version selector to one of the four `mechanic`
   candidates and open **Read original model proposal**. This is the strongest moment: the repair is the
   model's own text, never hand-written.
6. **3:15–4:00 · Why it was rejected.** The candidate repaired 7 of 12 source-validation trials against an
   incumbent that completed 0 of 12. Three of three is required, so it never reached the challenge. Finish on
   the honest line in the Run summary: no policy has been accepted.

To show a run that *did* reach the adversarial challenge, load
`campaign-44085f54a24144b78252d8eea211ebb8`: a candidate repaired 3/3, entered the challenge, and a 20-tick
schedule defeated it. Panel 07 shows the counterexample that blocked promotion.

## If you want something running live in front of judges

A full learning campaign takes about **10 minutes** end to end and makes real paid calls, so do not start one
cold and wait in silence. Measured stage timings from the campaign above:

| Stage | Finished by |
|---|---|
| Discovery | 0.9 min |
| Reproduction | 1.2 min |
| Reduction | 3.9 min |
| Diagnosis | 5.3 min |
| Source validation | 10.2 min |

The workable pattern is to start it at the very beginning of the talk and narrate the saved campaign while it
runs, then cut back to the live one. Start it from the dashboard: set **Campaign mode** to Learn, pick the live
execution profile, press **Create campaign**, then press **Start campaign**. Start is always a separate
explicit action; the page never begins paid execution on load. Stop is available at any time and keeps every
record already written.

Expect a fresh run to reach a different fault and possibly a different outcome. Discovery is model-chosen, so
do not promise a specific result on stage.

## What is deliberately not claimed

- **No accepted policy.** T065 is open. Do not describe the loop as having learned a fix that stuck.
- **Aria is deferred by the user.** The sponsor panel shows `PENDING` and the Aria evidence list is empty. The
  form records manually observed output only, attributed as operator evidence; a manually started Aria
  conversation does not satisfy automatic invocation. Do not invent an Aria integration on stage.
- **Weave is real.** Episode traces are independently verified by remote readback, and the Run summary shows
  the verified count. That is the sponsor claim that holds.
- The offline reference profile is B1 internal smoke. Never present it as model-generated repair evidence.

## Operator controls

Start admits one fresh execution. Duplicate Start is idempotent; another active campaign conflicts. Stop
increments the execution epoch and prevents new actions while retaining uncertain or committed remote effects.
Retry evidence resumes retrieval, never business execution. Reset prepares another fresh fixture while
preserving policy history. Exports are sanitized persisted records.

Live baseline/learning/comparison require `--execute-live` and confirmed settings. Freeze a completed campaign
before final audit with `cd backend && ../.venv/bin/python -m app.cli.freeze --campaign CAMPAIGN_ID`. Freezing
performs no calls and explicitly records when the learned arm is unavailable. A final B0/B1/L audit requires a
genuinely accepted learned policy.
