# Local demonstration

Run setup and `scripts/test.sh`, then start the simulator, backend and frontend using the README commands. Open the dashboard and select the offline reference profile for a credential-free smoke episode. An explicit Start creates a fresh world; refresh and playback read persisted evidence.

The useful sequence is task → original report → delivered tool observations → fixed checks → actual effects. The offline reference is B1/internal smoke. Do not present it as model-generated repair evidence.

## Under two minutes of recording

1. 0:00–0:20: explain the upgrade-and-confirm task and fault being investigated.
2. 0:20–0:45: open the source failure, three fresh reproduction trials and retained reduction. If no live failure exists, label these views pending and show the real offline HTTP diagnostic instead.
3. 0:45–1:15: show the tested hypothesis, diagnosis, original generated proposal and active challenge only when recorded. Show rejected/no-change outcomes truthfully.
4. 1:15–1:40: compare valid outcome counts and overhead; show a fresh regression execution ID only if actually executed. Playback has a separate label.
5. 1:40–1:55: open verified Weave/Aria links if available, then show remaining gates and external provenance.

For a three-minute explanation, allow another minute for the finite evidence-gap witness and why stable operation identities prevent duplicate effects. The actual artifact is `docs/diagnostic-evidence.json`, generated from loopback HTTP tests. Its available-status control distinguishes terminal success; the gap pair remains observationally equivalent only for the declared probe set.

## Operator controls

Start admits one fresh execution. Duplicate Start is idempotent; another active campaign conflicts. Stop increments the execution epoch and prevents new actions while retaining uncertain or committed remote effects. Retry evidence resumes retrieval, never business execution. Reset prepares another fresh fixture while preserving policy history. Exports are sanitized persisted records.

Live baseline/learning/comparison require `--execute-live` and confirmed settings. Freeze a completed campaign before final audit with `cd backend && ../.venv/bin/python -m app.cli.freeze --campaign CAMPAIGN_ID`. Freezing performs no calls and explicitly records when the learned arm is unavailable. A final B0/B1/L audit requires a genuinely accepted learned policy.
