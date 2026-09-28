# Local data, startup and recovery

Choose the data directory explicitly. It contains `lab.sqlite3`, simulator worlds and
the local control capability. Keep active data on a local disk that remains downloaded;
cloud placeholder files are unsuitable for an active SQLite store. Existing data is never
moved or merged by these commands.

From the repository root, start a new offline workspace:

```sh
./scripts/start-local.sh --data-dir "$HOME/Library/Application Support/FaultLab/workspace"
```

The launcher starts the simulator, backend and dashboard on localhost ports 8001, 8000
and 5173, with one shared data directory. Open `http://127.0.0.1:5173`. Choose **Offline
reference smoke**, create a campaign and start it to exercise a fresh synthetic world
without a model call. This is a handwritten reference, not learned-repair evidence.
Ctrl+C stops only the services launched by this command. It keeps the simulator available
until the backend finishes cancellation. Occupied ports cause an error before services start.
Use `--no-frontend` for API-only work.

Inspect a saved experiment using its existing directory:

```sh
./scripts/start-local.sh --data-dir /absolute/path/to/saved-run --archive
```

Archive mode opens an existing database read-only. It does not run restart recovery,
initialize a policy, launch a simulator or contact a model provider. The dashboard shows
the exact data location and disables execution and saving. Saved campaigns, original
reports, verdicts, playback and bundle downloads remain available. Even unfinished records
keep their original state in an archive; that does not mean they are still executing.
A missing campaign ID can belong to a different data directory: select it from history
instead of repeatedly retrying that ID.

To permit live actions, use `--live` with the normal configured credentials, confirmed
project, exact model prices and campaign caps. Starting the launcher still makes no model
calls. Each live action remains explicit, and normal admission checks apply. The launcher
keeps Aria publication disabled. Never print credentials or put them into browser variables.

Legacy `start-backend.sh`, `start-simulator.sh` and `start-frontend.sh` commands remain
available. If using them separately, provide the same `FAULTLAB_ARTIFACT_DIR` to both backend
and simulator. `FAULTLAB_READ_ONLY=true` enables archive mode for the backend. Relative
artifact paths retain their existing repository-relative meaning; the legacy default is
still `artifacts`, so existing users do not silently switch to an empty store.

Only one coordinator may own a writable store. Its OS lease is acquired before opening
the database or recovering unfinished jobs. A second owner gets `STORE_IN_USE`; it cannot
interrupt the first owner's work. The lease ends when its process or connection closes.
Do not delete the lock file to force access, rename a live database, or create hard links
to it. Separate data directories are independent. The current lease implementation supports
local POSIX filesystems; unsupported platforms fail closed.

Dashboard reads use independent read-only SQLite snapshots, so a slow evidence query does
not hold the scheduler's connection lock. This is a local single-writer application, not
a multi-user server or a distributed worker system. Legacy research scripts are frozen
experiment programs; they are not supported concurrent writers for a running store.

Restart marks unfinished owned execution as interrupted and retains charged model calls,
worlds, partial trials and original failures. It does not replay uncertain effects or
retry model generations. Only abandoned job reservations are released; protected capacity
for future studies stays reserved. Closed historical outcomes are not re-evaluated.

For a portable evidence backup, stop the owning services first and preserve the database,
world files and exported bundles together. A SQLite database copied during active writing
without its WAL can omit committed evidence. Use SQLite's backup API for an intentional live
snapshot. A Git source checkpoint does not include ignored runtime evidence or credentials.
