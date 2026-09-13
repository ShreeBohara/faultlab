# Trusted regression commands

The installed runner treats a bundle as data. It checks the exact inventory, source hashes, current compatible target configuration, schema and static runner digest. It never imports or executes Python from the bundle. Unknown files, path traversal, symlinks, altered runner bytes and incompatible task/oracle identities are rejected.

From the repository root, these commands make no provider or business calls:

```sh
./scripts/run-regression.sh export --regression REGRESSION_ID --output artifacts/my-bundle
./scripts/run-regression.sh validate --bundle artifacts/my-bundle
./scripts/run-regression.sh playback --bundle artifacts/my-bundle
./scripts/run-regression.sh register --agent reference
./scripts/run-regression.sh register --agent smolagents
```

The wrapper resolves relative bundle/output paths from the repository root. Direct module commands resolve them from the current directory. Registration records actual installed source, native prompt, adapter, task contract, oracle, model and caps. The native external registration requires a configured target model. Reference/internal smoke is labeled separately from independent validation.

Use the returned reviewed registration ID for a fresh execution:

```sh
./scripts/run-regression.sh execute --bundle /absolute/path/to/bundle --agent REGISTRATION_ID --profile sandbox-v1 --execute-live
```

The backend and simulator must be running. Verified live settings, current source compatibility, an immutable bundled baseline/accepted policy and complete three-trial reservation are required. The CLI validates and imports only bounded data, preserves source provenance as unverified historical evidence, creates an idle campaign and requests execution through the single-active backend scheduler. Each of the three trials gets a fresh world and conversation. The returned execution ID has a separate status and Stop boundary. A completed execution can reproduce the failure; completion does not mean the policy repaired it.

`python -m app.cli.regressions validate|playback|execute` from `backend` provides the same interface. Pytest collection of the reviewed harness stays offline. Source configuration hashes are checked for historical integrity; the target's source/model/prompt are independently frozen and shared semantics must match the installed oracle.

## Protected studies

An external study requires an accepted policy, a completed campaign, immutable core freeze and a compatible independently authored target. It runs six predeclared cases with three B0/L pairs per case and does not retune from results. Selector comparison spends eight selection slots and three trials per selected scenario for each arm; only 3/3 failures count as reproduced discoveries.

```sh
./scripts/run-portability.sh --campaign CAMPAIGN_ID --agent EXTERNAL_REGISTRATION_ID --execute-live
./scripts/compare-selectors.sh --campaign CAMPAIGN_ID --execute-live
```

These are explicit billable actions. Missing access, policy, freeze, compatibility or protected capacity rejects admission. Offline conformance tests do not fulfill the measured study gates.
