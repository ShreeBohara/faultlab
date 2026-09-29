# Local data, startup and recovery

Choose the data directory explicitly. It contains `lab.sqlite3`, simulator worlds and
the local control capability. Keep active data on a local disk that remains downloaded;
cloud placeholder files are unsuitable for an active SQLite store. Existing data is never
moved or merged by these commands.

Install first with [Setup](setup.md#install-and-test-start-here). Then, from the repository root,
start a new offline workspace:

```sh
./scripts/start-local.sh --data-dir "$HOME/Library/Application Support/FaultLab/workspace"
```

The launcher starts the simulator, backend and dashboard on localhost ports 8001, 8000
and 5173 (see [Ports](#ports) to change them), with one shared data directory. Open `http://127.0.0.1:5173`. Choose **Offline
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
and simulator. They read the same port settings. When `FAULTLAB_SIMULATOR_PORT` is set, the two
backend scripts point the backend at that port, unless `FAULTLAB_SIMULATOR_URL` is also set in
the terminal. Without either, the backend uses `FAULTLAB_SIMULATOR_URL` from `.env` or its default,
`http://127.0.0.1:8001`. `FAULTLAB_READ_ONLY=true` enables archive mode for the backend. Relative
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

## Ports

Three environment settings choose the ports. Unset or empty means the usual port:

| setting | service | default |
|---|---|---|
| `FAULTLAB_SIMULATOR_PORT` | simulator | 8001 |
| `FAULTLAB_BACKEND_PORT` | backend API | 8000 |
| `FAULTLAB_DASHBOARD_PORT` | dashboard | 5173 |

- **Where they apply:** the paired launcher and the separate start scripts; the dashboard's `/api`
  proxy and the browser tests; and the command-line tools behind `run-demo.sh`,
  `export-evidence.sh`, `run-audit.sh` and the `run-*-study.sh` scripts.
- **Set them in every terminal.** Export them before any FaultLab script, including the command-line
  tools. Otherwise a command may reach a different backend that still owns port 8000.
- **Checked before anything starts.** A value that is not a whole number from 1 to 65535 is refused.
  The paired launcher also refuses two services on the same port.
- **The launcher connects the services.** It points the backend at the selected simulator port and
  the dashboard at the selected backend port.
- **With no settings, every command is the same as before.** The only difference is that the launcher
  now also passes `FAULTLAB_BACKEND_PORT` and `FAULTLAB_DASHBOARD_PORT` (8000 and 5173) to the services
  it starts. Nothing in the backend or simulator reads them, and the dashboard resolves the same values.
- **The command-line tools say which backend they use.** Before they create, start or stop anything they
  print `Using the FaultLab backend at http://127.0.0.1:PORT.` If no backend answers, they name the
  address they tried and whether `FAULTLAB_BACKEND_PORT` was set.

A second checkout can run beside the first with its own ports and its own data directory:

```sh
export FAULTLAB_SIMULATOR_PORT=18001 FAULTLAB_BACKEND_PORT=18000 FAULTLAB_DASHBOARD_PORT=15173
./scripts/start-local.sh --data-dir "$HOME/FaultLab_Runs/second-workspace"
```
