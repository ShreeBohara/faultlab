"""Launch paired localhost services with an explicitly selected data directory."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading


ROOT = Path(__file__).resolve().parents[2]


def launch_plan(data_dir, *, archive=False, live=False, frontend=True):
    path = Path(data_dir).expanduser().resolve()
    if archive and live:
        raise ValueError('Archive mode cannot enable live execution.')
    if archive and not (path / 'lab.sqlite3').is_file():
        raise ValueError('Archive mode requires an existing lab.sqlite3 in the selected data directory.')
    if path.exists() and not path.is_dir():
        raise ValueError('Select a data directory, not a file.')
    environment = dict(os.environ)
    environment.update(FAULTLAB_ARTIFACT_DIR=str(path),
                       FAULTLAB_READ_ONLY='true' if archive else 'false',
                       FAULTLAB_LIVE_ENABLED='true' if live else 'false',
                       FAULTLAB_ARIA_PUBLISH_ENABLED='false',
                       FAULTLAB_SIMULATOR_URL='http://127.0.0.1:8001')
    commands = []
    if not archive:
        commands.append(('simulator', [sys.executable, '-m', 'uvicorn',
                         'app.simulator.main:app', '--host', '127.0.0.1', '--port', '8001',
                         '--timeout-keep-alive', '75'], ROOT / 'backend', 8001))
    commands.append(('backend', [sys.executable, '-m', 'uvicorn',
                     'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'], ROOT / 'backend', 8000))
    if frontend:
        npm = shutil.which('npm')
        if npm is None:
            raise ValueError('npm is required for the dashboard; use --no-frontend for API-only work.')
        commands.append(('dashboard', [npm, 'run', 'dev'], ROOT / 'frontend', 5173))
    return path, environment, commands


def check_ports(commands):
    # Fail before any service creates a world directory or claims a store.
    for name, _, _, port in commands:
        with socket.socket() as listener:
            try:
                # Match Uvicorn's reuse behavior: a recently stopped listener's
                # TIME_WAIT sockets are not an active service on this port.
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('127.0.0.1', port))
            except OSError:
                raise ValueError(f'Port {port} is in use. Stop the existing {name} before launching these services.') from None


def supervise(commands, environment):
    children = []
    stopped = threading.Event()
    previous = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, lambda *_: stopped.set())
    try:
        for _, command, directory, _ in commands:
            children.append(subprocess.Popen(command, cwd=directory, env=environment, start_new_session=True))
        while not stopped.wait(.2):
            for child in children:
                code = child.poll()
                if code is not None:
                    return code if code else 1
        return 0
    finally:
        # Only processes launched here are signalled. Let their normal shutdown
        # finish owned jobs, flush evidence and release leases before escalation.
        # Reverse dependency order keeps the simulator available while the
        # backend cancels work and records its final world/evidence state.
        for child in reversed(children):
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, type=Path,
                        help='Explicit directory for this store and its worlds; existing history is never moved.')
    parser.add_argument('--archive', action='store_true', help='Read an existing store without a simulator, recovery or writes.')
    parser.add_argument('--live', action='store_true', help='Allow explicit live actions after the normal configuration checks.')
    parser.add_argument('--no-frontend', action='store_true', help='Start API services only.')
    args = parser.parse_args(argv)
    try:
        path, environment, commands = launch_plan(args.data_dir, archive=args.archive,
                                                  live=args.live, frontend=not args.no_frontend)
        check_ports(commands)
    except ValueError as error:
        parser.error(str(error))
    print(f'FaultLab {"read-only archive" if args.archive else "local workspace"}: {path}', flush=True)
    print('Dashboard: http://127.0.0.1:5173' if not args.no_frontend else 'API: http://127.0.0.1:8000', flush=True)
    print('Press Ctrl+C to stop these services. Starting services makes no model calls.', flush=True)
    return supervise(commands, environment)


if __name__ == '__main__':
    raise SystemExit(main())
