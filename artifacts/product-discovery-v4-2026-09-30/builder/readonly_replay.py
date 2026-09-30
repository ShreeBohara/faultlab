"""What discovery v4 would freeze (history + replay list) for each agent in each saved run store. Read-only and $0.

Run from faultlab/backend:
    ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/builder/readonly_replay.py <out.json>

Every store under /Users/shree/FaultLab_Runs is opened ONLY with SQLite's `mode=ro&immutable=1` URI (query_only on);
sizes and modification times of every store file are recorded before and after. No write, no provider, W&B, model
or network call; the real .env is never opened (the test suite's audit hook is installed first). Only the product's
own history reader runs (development-split, discovery-purpose episodes and registration/configuration/policy/evidence
records; app.lab.agent_history), then the pure replay rule (app.lab.history_replay) on its summary.

Caveat printed with the result: a live v4 plan freezes the history of the store it is created in, at that moment, for
the registration it names; registering again under this runtime keeps the same agent identity (app.lab.agent_history
SAME_AGENT_RULE), so these lists are what a v4 plan in each store would show today, under the current code.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path
from threading import RLock

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests')]
import conftest  # noqa: F401,E402  (audit hook refusing the real .env; dotenv disabled)

from app.lab import agent_history, history_replay  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402

RUNS = Path('/Users/shree/FaultLab_Runs')


def stat(path):
    return {str(name): [os.stat(name).st_size, os.stat(name).st_mtime_ns] for name in sorted(Path(path).parent.glob(Path(path).name + '*'))}


def immutable_store(path):
    store = LabStore.__new__(LabStore)  # the installed reader methods, over an immutable read-only connection
    store.path, store.lock, store._closed, store._close_callbacks, store.read_only = str(path), RLock(), False, [], True
    store.db = sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True, check_same_thread=False, isolation_level=None)
    store.db.row_factory = sqlite3.Row
    store.db.execute('PRAGMA query_only=ON')
    return store


def main(out):
    report = {'stores': {}, 'caveat': __doc__.split('Caveat printed with the result: ')[1].strip()}
    for path in sorted(RUNS.rglob('lab.sqlite3')):
        before = stat(path)
        store = immutable_store(path)
        rows = []
        try:
            policy = store.get_record('policies', 'policy-v0')
            for registration in store.list_records('agent_registrations'):
                configuration = store.get_record('configurations', registration.get('configuration_hash'))
                if agent_history.target_identity(registration, configuration) is None or policy is None:
                    rows.append({'registration_id': registration.get('registration_id'), 'entrypoint': registration.get('adapter_entrypoint_id'),
                                 'history': 'no supported same-agent identity (not a reviewed agent registration)'})
                    continue
                block = agent_history.snapshot(store, registration=registration, configuration=configuration, policy_hash=policy['policy_hash'])
                replay = history_replay.plan_block(block)
                summary = block['summary']
                rows.append({'registration_id': registration['registration_id'], 'entrypoint': registration['adapter_entrypoint_id'],
                             'model': registration.get('model'), 'history_status': summary['status'],
                             'verified_episodes': summary['verified_episodes'], 'composition': summary['composition'],
                             'history_rows': [{'row': i, 'case': r['development_case_id'], 'verified': r['verified_episodes'],
                                               'outcomes': r['outcomes'], 'every_fault_fired': r['every_fault_fired'],
                                               'failed_checks': r['failed_checks'], 'eligible': history_replay.eligible(r)}
                                              for i, r in enumerate(summary['recipes'], 1)],
                             'summary_hash': block['summary_hash'], 'replay_status': replay['status'], 'replay_statement': replay['statement'],
                             'replay_rows': [{k: r[k] for k in ('replay', 'history_row', 'development_case_id', 'recipe', 'violation_share',
                                                                 'every_fault_fired', 'failed_checks', 'sources')} for r in replay['rows']]})
        finally:
            store.db.close()
        after = stat(path)
        report['stores'][str(path)] = {'registrations': rows, 'store_files_unchanged': before == after}
        print(path, '| unchanged', before == after)
        for row in rows:
            if 'replay_rows' not in row:
                print('   ', row['entrypoint'], '-', row['history']); continue
            print('   ', row['entrypoint'], row['registration_id'][:40], '| history', row['history_status'], row['verified_episodes'],
                  '| replay', row['replay_status'], [(r['history_row'], r['development_case_id'], r['violation_share'], r['failed_checks']) for r in row['replay_rows']])
    Path(out).write_text(json.dumps(report, indent=1, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv[1])
