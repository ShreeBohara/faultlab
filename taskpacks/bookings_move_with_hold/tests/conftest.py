"""Offline guard for the bookings pack tests.

* No sockets at all: an audit hook refuses every socket connect, bind and name lookup in this
  process, and records the attempt. The run fails if any attempt was recorded (other than the one
  deliberate probe in test_no_network.py, which removes its own record).
* This test process never opens the project .env, the sealed audit partitions, or the order task's
  checks file (an audit hook refuses it). The order guard test runs gate_freeze.py in a separate
  child process that never opens .env or the sealed audit files; it DOES read the bytes of the
  order task's checks file (backend/app/referee/checks.py) to hash them for scorer_hash. It never
  prints or parses that content, and no agent ever sees it.
* Turns off bytecode writing for every module imported after this file loads, and puts the repo
  root on sys.path so ``taskpacks`` imports. Pytest compiles this conftest itself before that line
  runs, so run the tests with ``python -B`` (as the README says) to write no bytecode at all.
"""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NEVER_OPEN = {str(ROOT / p) for p in ('.env', 'audit/promotion.json', 'audit/final-audit.json',
                                        'backend/app/referee/checks.py')}
SOCKET_ATTEMPTS = []


def _audit(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        try:
            path = os.path.abspath(os.fsdecode(os.fspath(args[0])))
        except TypeError:
            return
        if path in NEVER_OPEN:
            raise PermissionError(f'bookings pack tests must not open {path}')
    elif event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'socket.sendmsg'):
        SOCKET_ATTEMPTS.append((event, repr(args[1:])[:200]))
        raise PermissionError('bookings pack phase 1 tests use no sockets')


sys.addaudithook(_audit)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f'bookings pack: socket attempts recorded = {len(SOCKET_ATTEMPTS)}')


def pytest_sessionfinish(session, exitstatus):
    if SOCKET_ATTEMPTS and exitstatus == 0:
        session.exitstatus = 1
