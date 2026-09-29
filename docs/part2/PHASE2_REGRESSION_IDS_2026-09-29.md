# Phase 2: the two saved regression IDs (note added 2026-09-29)

A new note, not an edit to a historical results file. On September 29 the user guide stopped naming IDs
that exist only in the team's local store (a fresh install does not have them). Every other ID it removed
is in [Phase 2 results](PHASE2_RESULTS.md) or [the Phase 2 experiment](PHASE2_EXPERIMENT.md). These two
were only in the guide, so they are recorded here, with what the guide said about each.

| regression ID | what the guide said |
|---|---|
| `regression-9a121aa5527840dcafc4ba07272d35de` | To inspect the three fresh trials of the saved B incident (execution `execution-dcf7936ab295477fb7588f38584f8bbe`, campaign `campaign-1c19ec5bb8db4988b8493d3ea19d48df`): load that campaign, select this regression under **Portable regression → Saved regression**, click **Inspect saved bundle**, then open the saved execution. |
| `regression-3312dfc637c54cc98b201bf5fe5b9dc4` | The regression named in the optional command `./scripts/run-regression.sh export --regression … --output …`, which packages the same saved B incident again without running it. |

Both exist only in the team's local Phase 2 store. The guide's earlier text is in git history
(`docs/user-guide.md` on branch `backup/part2-2026-09-22`).
