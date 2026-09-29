# Trusted regression commands

The installed runner treats a bundle as data. It checks the exact inventory, source hashes, current compatible target configuration, schema and static runner digest. It never imports or executes Python from the bundle. Unknown files, path traversal, symlinks, altered runner bytes and incompatible task/oracle identities are rejected.

An incident fixture records a reproduced failure. A candidate comparison records what broke a tested candidate, even if the candidate was rejected. An accepted-policy bundle alone means the bundled policy was accepted. New learning runs save an incident after reduction and a comparison after a failed challenge; acceptance is not required to export either.

From the repository root, these commands make no provider or business calls:

```sh
./scripts/run-regression.sh export --regression REGRESSION_ID --output artifacts/my-bundle
./scripts/run-regression.sh validate --bundle artifacts/my-bundle
./scripts/run-regression.sh playback --bundle artifacts/my-bundle
./scripts/run-regression.sh register --agent reference
./scripts/run-regression.sh register --agent smolagents
```

To export an existing reproduced source that has no regression ID yet:

```sh
./scripts/run-regression.sh export --counterexample COUNTEREXAMPLE_ID --output artifacts/my-incident
```

To export the fault that broke a saved candidate during its challenge:

```sh
./scripts/run-regression.sh export --counterexample COUNTEREXAMPLE_ID --policy CANDIDATE_POLICY_VERSION --challenge CHALLENGE_ID --output artifacts/my-failed-challenge
```

Export only packages saved evidence; it does not run the model. Each new bundle includes the policy, actual runnable fault recipe, initial fixture and task, related public development episodes and event timelines, reduction/diagnosis/challenge evidence, and campaign-owned proposals. The manifest labels its artifact kind. Files are limited to 8 MiB each and 16 MiB together; an oversized complete artifact is rejected instead of silently truncated. Older version-1 bundles retain their original hashes and remain readable by the trusted runner.

The wrapper resolves relative bundle/output paths from the repository root. Direct module commands resolve them from the current directory. Registration records actual installed source, native prompt, adapter, task contract, oracle, model and caps. The native external registration requires a configured target model. Reference/internal smoke is labeled separately from independent validation.

The CLI reads its own terminal environment and `.env`. Inline overrides used to launch the backend do not automatically carry into another terminal: export the same model, role, pricing, live-enable, confirmed-entity and budget settings there before registering or executing. A mismatched model/configuration is rejected. For an incident already in the running dashboard, use **Portable regression**, inspect the bundle, then select the reviewed agent by its displayed model and registration ID and select the exact immutable bundled policy.

Use the returned reviewed registration ID for a fresh execution:

```sh
./scripts/run-regression.sh execute --bundle /absolute/path/to/bundle --agent REGISTRATION_ID --profile sandbox-v1 --execute-live
```

The backend and simulator must be running. Verified live settings, current source compatibility, the exact immutable bundled policy and complete three-trial reservation are required. Incident/comparison bundles can rerun a policy with a recorded baseline, rejected, incomplete or no-change decision; accepted-policy bundles still require acceptance. Execution never promotes the bundled policy. The CLI validates and imports only bounded data, preserves source provenance as unverified historical evidence, creates an idle campaign and requests execution through the single-active backend scheduler. Each of the three trials gets a fresh world and conversation. The returned execution ID has a separate status and Stop boundary. A completed execution can reproduce the failure; completion does not mean the policy repaired it.

`python -m app.cli.regressions validate|playback|execute` from `backend` provides the same interface. Pytest collection of the reviewed harness stays offline. Source configuration hashes are checked for historical integrity; the target's source/model/prompt are independently frozen and shared semantics must match the installed oracle.

For the complete public campaign record, with the backend running:

```sh
./scripts/export-evidence.sh --campaign CAMPAIGN_ID --output artifacts/my-campaign.json
```

This read-only export includes every development episode and all event pages, campaign-owned raw proposals (including invalid, duplicate and rejected attempts), policy decisions and qualification results. It excludes credentials, private evaluator data and protected cases. Older raw attempts without saved campaign ownership cannot safely be attributed; the recording states that limitation. This JSON file is an evidence archive, not an offline dashboard or a new execution.

## Protected studies

An external study requires an accepted policy, a completed campaign, immutable core freeze and a compatible independently authored target. It runs six predeclared cases with three B0/L pairs per case and does not retune from results. Selector comparison spends eight selection slots and three trials per selected scenario for each arm; only 3/3 failures count as reproduced discoveries.

```sh
./scripts/run-portability.sh --campaign CAMPAIGN_ID --agent EXTERNAL_REGISTRATION_ID --execute-live
./scripts/compare-selectors.sh --campaign CAMPAIGN_ID --execute-live
```

These are explicit billable actions. Missing access, policy, freeze, compatibility or protected capacity rejects admission. Offline conformance tests do not fulfill the measured study gates.
