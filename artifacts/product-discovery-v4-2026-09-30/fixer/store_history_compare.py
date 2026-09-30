"""MEDIUM-1 fix, saved-store check: every saved store's agent history is byte-identical before and after the fix ($0).

The fix makes app.lab.agent_history skip episodes of discovery v4 history replay slots. No saved store holds one (v4 has
never run), so every history block must be exactly what the unchanged code (backup/part2-2026-09-22, blob 5f4868ad)
computes. For each store under /Users/shree/FaultLab_Runs and each reviewed registration in it, this computes the
history block with the code before the fix and with the installed code, at the same record cutoff, and compares the
whole block (summary hash included); it also prints the v4 replay list the installed code would freeze.

Every store is opened ONLY through SQLite's `mode=ro&immutable=1` URI with query_only on; each store file's size and
modification time are recorded before and after. The fixer guard refuses the real .env and every non-loopback socket.

Run from faultlab/backend:
    PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/fixer/store_history_compare.py <out.json>
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from threading import RLock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

from app.lab import agent_history, history_replay  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402

RUNS = Path('/Users/shree/FaultLab_Runs')
BEFORE = HERE / 'before' / 'files' / 'backend' / 'app' / 'lab' / 'agent_history.py'


def load_before():
    blob = subprocess.run(['git', 'hash-object', str(BEFORE)], capture_output=True, text=True, check=True).stdout.strip()
    backup = subprocess.run(['git', 'rev-parse', 'backup/part2-2026-09-22:backend/app/lab/agent_history.py'],
                            capture_output=True, text=True, check=True).stdout.strip()
    assert blob == backup, (blob, backup)
    spec = importlib.util.spec_from_file_location('agent_history_before_fix', BEFORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, blob


def stat(path):
    return {str(name): [os.stat(name).st_size, os.stat(name).st_mtime_ns] for name in sorted(Path(path).parent.glob(Path(path).name + '*'))}


def immutable_store(path):
    store = LabStore.__new__(LabStore)
    store.path, store.lock, store._closed, store._close_callbacks, store.read_only = str(path), RLock(), False, [], True
    store.db = sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True, check_same_thread=False, isolation_level=None)
    store.db.row_factory = sqlite3.Row
    store.db.execute('PRAGMA query_only=ON')
    return store


def main(out):
    before_module, blob = load_before()
    report = {'before_blob': blob, 'installed_sha256': hashlib.sha256(Path(agent_history.__file__).read_bytes()).hexdigest(), 'stores': {}}
    all_same = True
    for path in sorted(RUNS.rglob('lab.sqlite3')):
        first = stat(path)
        store = immutable_store(path)
        rows = []
        try:
            replay_records = store.db.execute("SELECT count(*) FROM records WHERE kind='selections' AND "
                                              "json_extract(payload,'$.provenance')='history_replay'").fetchone()[0]
            policy = store.get_record('policies', 'policy-v0')
            for registration in store.list_records('agent_registrations'):
                configuration = store.get_record('configurations', registration.get('configuration_hash'))
                identity = agent_history.target_identity(registration, configuration)
                if identity is None or policy is None:
                    rows.append({'registration_id': registration.get('registration_id'), 'history': 'no supported same-agent identity'})
                    continue
                cutoff = store.max_record_rowid()
                old = before_module.compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                new = agent_history.compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                same = old == new and json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True)
                all_same &= same
                replay = history_replay.plan_block(new)
                rows.append({'registration_id': registration['registration_id'], 'entrypoint': registration['adapter_entrypoint_id'],
                             'record_cutoff': cutoff, 'verified_episodes': new['summary']['verified_episodes'],
                             'summary_hash_before_fix': old['summary_hash'], 'summary_hash_after_fix': new['summary_hash'],
                             'block_identical': same, 'replay_status': replay['status'],
                             'replay_rows': [(r['history_row'], r['development_case_id'], r['violation_share']) for r in replay['rows']]})
        finally:
            store.db.close()
        second = stat(path)
        report['stores'][str(path)] = {'history_replay_selection_records': replay_records, 'registrations': rows,
                                       'store_files_unchanged': first == second}
        all_same &= first == second
        print(path, '| replay records', replay_records, '| files unchanged', first == second)
        for row in rows:
            if 'block_identical' in row:
                print('   ', row['entrypoint'], row['registration_id'][:44], '| verified', row['verified_episodes'], '| identical',
                      row['block_identical'], '|', row['summary_hash_after_fix'][:12], '| replay', row['replay_status'], row['replay_rows'])
    report['all_identical_and_unchanged'] = all_same
    print('ALL HISTORY BLOCKS IDENTICAL, ALL STORE FILES UNCHANGED' if all_same else 'DIFFERENCE FOUND')
    Path(out).write_text(json.dumps(report, indent=1, sort_keys=True))
    return 0 if all_same else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
