"""Read-only proof that the order task's identities are unchanged by this pack.

Run:  .venv/bin/python -B -m taskpacks.bookings_move_with_hold.order_guard [--out FILE]

What it does, in plain words:

1. Runs scripts/experiments/gate_freeze.py in a child process, read-only. gate_freeze.py is
   standard library only and prints hashes. The child executes its source text directly (so no
   bytecode file is written under scripts/), leaves the two sealed audit files out of its file list
   (the same rule the September 29 verifier used; they are never opened), and an audit hook refuses
   any open of .env or of those sealed files, and any socket. gate_freeze.py does read the bytes of
   the order task's checks file to compute scorer_hash; the guard never prints or parses them.
2. Compares the five order-task identities (service, contract, scorer, interpreter and dependency
   lock hashes) with the values recorded when this phase started (order_identity_baseline.json)
   and with the latest working-tree freeze found in artifacts/.
3. Lists backend/, contracts/, audit/, frontend/, scripts/ and docs/ by name only and confirms that
   nothing carrying this pack's names was added there.

Other fingerprints (algorithm_hash, runtime_hash, ...) are reported for information: another
workflow (discovery v3) is editing backend/ now, so they may move for reasons outside this pack.
Standard library only; never imports app.*.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / 'order_identity_baseline.json'
ORDER_IDENTITIES = ('service_hash', 'contract_hash', 'scorer_hash', 'interpreter_hash', 'dependency_lock_hash')
SEALED = ('audit/promotion.json', 'audit/final-audit.json')
GUARDED_DIRS = ('backend', 'contracts', 'audit', 'frontend', 'scripts', 'docs')
PRUNE = {'node_modules', '.venv', '__pycache__', '.npm-cache', '.git'}
MARKERS = ('taskpack', 'task_pack', 'move_with_hold', 'hk-dev')
NEVER_READ_PARTS = ('heldout2', 'final-audit', 'final_audit', 'promotion.json', 'product-taskpack-')

CHILD = r'''
import os, sys
sys.dont_write_bytecode = True
root = sys.argv[1]
forbidden = {os.path.join(root, p) for p in ('.env', 'audit/promotion.json', 'audit/final-audit.json')}
def refuse(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.abspath(os.fsdecode(os.fspath(args[0])))
        if path in forbidden:
            raise PermissionError('order guard must not open ' + path)
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
        raise PermissionError('order guard makes no network calls')
sys.addaudithook(refuse)
path = os.path.join(root, 'scripts', 'experiments', 'gate_freeze.py')
with open(path, encoding='utf-8') as handle:
    source = handle.read()
namespace = {'__name__': 'gate_freeze_readonly', '__file__': path}
exec(compile(source, path, 'exec'), namespace)
namespace['FILES'] = [f for f in namespace['FILES'] if f not in ('audit/promotion.json', 'audit/final-audit.json')]
sys.argv = ['gate_freeze.py', '--root', root]
namespace['main']()
'''


def run_gate_freeze(root=ROOT):
    env = {'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
           'PYTHONUTF8': '1'}
    done = subprocess.run([sys.executable, '-c', CHILD, str(root)], capture_output=True, text=True, timeout=180,
                          env=env, cwd=str(root))
    if done.returncode != 0:
        raise RuntimeError('gate_freeze.py failed: ' + done.stderr[-2000:])
    return json.loads(done.stdout)


def latest_freeze(root=ROOT):
    """The newest working-tree gate-freeze output in artifacts/ (checkpoint freezes are other trees)."""
    best = None
    for directory, dirs, files in os.walk(root / 'artifacts'):
        dirs[:] = [d for d in dirs if not any(part in d for part in NEVER_READ_PARTS)]
        for name in files:
            if not name.endswith('.json') or 'checkpoint' in name or any(p in name for p in NEVER_READ_PARTS):
                continue
            path = Path(directory) / name
            if 'freeze' not in name and 'gate_freeze' not in path.parent.name:
                continue
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(value, dict) and value.get('schema_version') == 'faultlab-gate-freeze/v1' \
                    and isinstance(value.get('fingerprints'), dict):
                mtime = path.stat().st_mtime
                if best is None or mtime > best[0]:
                    best = (mtime, path, value)
    return (best[1], best[2]) if best else (None, None)


def listing_check(root=ROOT):
    hits = []
    for top in GUARDED_DIRS:
        for directory, dirs, files in os.walk(root / top):
            dirs[:] = [d for d in dirs if d not in PRUNE]
            for name in [*dirs, *files]:
                if any(marker in name.lower() for marker in MARKERS):
                    hits.append(str((Path(directory) / name).relative_to(root)))
    return {'guarded_dirs': list(GUARDED_DIRS), 'markers': list(MARKERS), 'hits': sorted(hits),
            'passed': not hits}


def guard(root=ROOT):
    baseline = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
    current = run_gate_freeze(root)['fingerprints']
    latest_path, latest = latest_freeze(root)
    latest_fp = (latest or {}).get('fingerprints', {})
    identities = {}
    for name in ORDER_IDENTITIES:
        identities[name] = {'baseline': baseline['order_identities'][name], 'current': current[name],
                            'latest_freeze': latest_fp.get(name),
                            'equal': current[name] == baseline['order_identities'][name]
                            and (latest_fp.get(name) in (None, current[name]))}
    others = {name: {'at_phase_start': baseline['informational_at_start'].get(name), 'current': value,
                     'latest_freeze': latest_fp.get(name), 'unchanged_since_phase_start':
                         value == baseline['informational_at_start'].get(name)}
              for name, value in sorted(current.items()) if name not in ORDER_IDENTITIES}
    listing = listing_check(root)
    unchanged = all(v['equal'] for v in identities.values())
    return {'schema_version': 'faultlab-pack-order-guard/v1', 'baseline_file': str(BASELINE_PATH.relative_to(root)),
            'latest_freeze_file': str(latest_path.relative_to(root)) if latest_path else None,
            'order_identities': identities, 'all_order_identities_unchanged': unchanged,
            'other_fingerprints_informational': others, 'listing_check': listing,
            'passed': unchanged and listing['passed']}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only order-task identity guard for the bookings pack.')
    parser.add_argument('--out', help='also write the JSON result to this file')
    args = parser.parse_args(argv)
    result = guard()
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)
    print(('PASS' if result['passed'] else 'FAIL') + ': order-task identities '
          + ('unchanged' if result['all_order_identities_unchanged'] else 'CHANGED')
          + '; listing check ' + ('clean' if result['listing_check']['passed'] else 'FOUND PACK FILES'),
          file=sys.stderr)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
