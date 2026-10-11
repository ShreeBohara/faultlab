# Contributing

Thanks for looking. FaultLab is in the middle of a rebuild (see `FaultLab_Plan` notes in the docs); the shape below is what we hold to during it.

## Ground rules

1. **Evidence before claims.** A change that affects results comes with the measurement that shows it. "Done" means saved evidence, not a passing feeling.
2. **Never weaken a gate to get a result.** The fixed checks, the "an untriggered fault is never a pass" rule, and the repetition statistics are the product. A correct rejection is a success of the lab.
3. **Separate what was observed from what was inferred.** Docs and results say which is which.
4. **No secrets, ever.** `.env` is ignored; tests refuse to open it; credentials never appear in traces, logs or issues.
5. **Plain English.** Write for an engineer who has not read the history.

## Setup

```sh
./scripts/setup.sh
./scripts/test.sh            # backend, frontend, build, browser (about 20 minutes)
./scripts/test.sh frontend build browser   # the quick stages
```

Work from a folder that is not synced to a cloud drive; synced folders evict files and break test workers.

## Pull requests

- Small, reviewable changes with tests. Say what you measured.
- Keep historical result files unchanged; add a dated correction note instead.
- Run the quick stages locally; CI runs the rest.
- Commit messages describe the change and its evidence in the first line.

## Code of conduct

See `CODE_OF_CONDUCT.md`.
