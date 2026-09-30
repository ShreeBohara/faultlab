"""Independent verifier (discovery v4 review round, 2026-09-30), MEDIUM-1 spot check on the saved stores. $0, offline.

Written from scratch (not the fixer's script). For every lab.sqlite3 under /Users/shree/FaultLab_Runs and every
agent registration in it with a supported same-agent identity, compute the agent history block twice at the same
record cutoff and policy-v0:
  * BEFORE: backend/app/lab/agent_history.py exactly as committed at backup/part2-2026-09-22 (4d1c21b), read with
    `git show` into a scratch file outside the synced Desktop and imported under another module name;
  * AFTER: the installed working-tree module.
The two whole blocks (summary hash, episode-ids hash and every field) must be equal. Also counted per store, read only:
selection records with provenance history_replay, and campaign_plans records that mention the v4 protocol id.

Stores are opened ONLY through SQLite's `mode=ro&immutable=1` URI with PRAGMA query_only=ON; every store file's size
and mtime (lab.sqlite3, -wal, -shm) is recorded before and after. Run from faultlab/backend with the verifier guard on
PYTHONPATH (no outside connection, no .env) and PYTHONDONTWRITEBYTECODE=1.
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

ROOT = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab')
RUNS = Path('/Users/shree/FaultLab_Runs')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/verify-v4/store-check')
TIP = '4d1c21ba83fea229c23ee086e6b566000fb8640a'
V4 = 'faultlab-discovery/v4-history-replay'

from app.lab import agent_history as after_module  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402


def before_module():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    data = subprocess.run(['git', '-C', str(ROOT), 'show', f'{TIP}:backend/app/lab/agent_history.py'], capture_output=True, check=True).stdout
    path = SCRATCH / 'agent_history_at_4d1c21b.py'
    path.write_bytes(data)
    spec = importlib.util.spec_from_file_location('agent_history_at_4d1c21b', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, hashlib.sha256(data).hexdigest()


def stats(db_path):
    out = {}
    for suffix in ('', '-wal', '-shm'):
        p = Path(str(db_path) + suffix)
        if p.exists():
            st = p.stat()
            out[p.name] = [st.st_size, st.st_mtime_ns]
    return out


def open_immutable(db_path):
    store = LabStore.__new__(LabStore)
    store.path, store.lock, store._closed, store._close_callbacks, store.read_only = str(db_path), RLock(), False, [], True
    store.db = sqlite3.connect(Path(db_path).as_uri() + '?mode=ro&immutable=1', uri=True, check_same_thread=False, isolation_level=None)
    store.db.row_factory = sqlite3.Row
    store.db.execute('PRAGMA query_only=ON')
    return store


def main(out_path):
    before, before_sha = before_module()
    report = {'before_source': f'git show {TIP}:backend/app/lab/agent_history.py', 'before_sha256': before_sha,
              'after_sha256': hashlib.sha256(Path(after_module.__file__).read_bytes()).hexdigest(), 'stores': {}}
    ok = True
    blocks = 0
    for db_path in sorted(RUNS.rglob('lab.sqlite3')):
        first = stats(db_path)
        store = open_immutable(db_path)
        entry = {'registrations': []}
        try:
            q = store.db.execute
            entry['replay_selection_records'] = q("SELECT count(*) FROM records WHERE kind='selections' AND "
                                                  "json_extract(payload,'$.provenance')='history_replay'").fetchone()[0]
            entry['v4_plan_records'] = q("SELECT count(*) FROM records WHERE kind='campaign_plans' AND instr(payload, ?) > 0", (V4,)).fetchone()[0]
            policy = store.get_record('policies', 'policy-v0')
            cutoff = store.max_record_rowid()
            for registration in store.list_records('agent_registrations'):
                configuration = store.get_record('configurations', registration.get('configuration_hash'))
                identity = after_module.target_identity(registration, configuration)
                identity_before = before.target_identity(registration, configuration)
                row = {'registration_id': registration.get('registration_id'), 'entrypoint': registration.get('adapter_entrypoint_id'),
                       'identity_equal': identity == identity_before}
                ok &= row['identity_equal']
                if identity is None or policy is None:
                    row['history'] = 'no supported same-agent identity (not computed)'
                    entry['registrations'].append(row)
                    continue
                old = before.compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                new = after_module.compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                same = json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True)
                ok &= same
                blocks += 1
                s = new['summary']
                row.update({'record_cutoff': cutoff, 'block_identical': same, 'summary_hash_before': old['summary_hash'],
                            'summary_hash_after': new['summary_hash'], 'verified_episodes': s['verified_episodes'],
                            'composition': s['composition'],
                            'rows': [(r['development_case_id'], r['verified_episodes'], r['outcomes'].get('VIOLATION', 0), r['sources'])
                                     for r in s['recipes']]})
                entry['registrations'].append(row)
        finally:
            store.db.close()
        second = stats(db_path)
        entry['store_files_unchanged'] = first == second
        entry['file_stats'] = first
        ok &= entry['store_files_unchanged']
        report['stores'][str(db_path)] = entry
        print(db_path, '| replay selections', entry['replay_selection_records'], '| v4 plans', entry['v4_plan_records'],
              '| files unchanged', entry['store_files_unchanged'])
        for row in entry['registrations']:
            if 'block_identical' in row:
                print('    ', row['entrypoint'], row['registration_id'][:40], '| verified', row['verified_episodes'],
                      '| identical', row['block_identical'], '|', row['summary_hash_after'][:12], '|', row['rows'])
    report['history_blocks_compared'] = blocks
    report['all_ok'] = ok
    print('history blocks compared:', blocks, '| ALL IDENTICAL AND STORES UNCHANGED' if ok else '| DIFFERENCE FOUND')
    Path(out_path).write_text(json.dumps(report, indent=1, sort_keys=True))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
