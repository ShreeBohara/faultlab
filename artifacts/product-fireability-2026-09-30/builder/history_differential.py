"""Differential check ($0, read-only): the refactored agent history equals the backup branch's, on every saved store.

Run from faultlab/backend:
    ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/builder/history_differential.py <backup agent_history.py> <out.json>

The backup module is `git show 432e54b:backend/app/lab/agent_history.py` (backup/part2-2026-09-22 tip), saved outside the
Desktop. Every store under /Users/shree/FaultLab_Runs is opened ONLY with SQLite's `mode=ro&immutable=1` URI (query_only
on); sizes and modification times of every store file are recorded before and after. For every registration with a
same-agent identity, both modules compute the history at every saved plan's record cutoff and at the store's current
maximum, under policy-v0; the two results must be equal. Every saved plan with a frozen history is also re-verified
with the new code (agent_history.verify) and, separately, with the backup code, and the two outcomes must agree.
The new used_episodes() must list exactly the episodes whose ids hash to each history's episode_ids_hash.
"""
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from threading import RLock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401  (refuses the real .env and any non-loopback connection)

from app.contracts.models import content_hash  # noqa: E402
from app.lab import agent_history as new  # noqa: E402
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


def main(backup_path, out):
    spec = importlib.util.spec_from_file_location('agent_history_backup', backup_path)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    report = {'backup_module': backup_path, 'stores': {}}
    compared = equal = verified_same = used_ok = 0
    for path in sorted(RUNS.rglob('lab.sqlite3')):
        before = stat(path)
        store = immutable_store(path)
        rows = []
        try:
            policy = store.get_record('policies', 'policy-v0')
            plans = [p for p in store.list_records('campaign_plans')]
            cutoffs = sorted({((p.get('discovery') or {}).get('history') or {}).get('record_cutoff') for p in plans} - {None} | {store.max_record_rowid()})
            for registration in store.list_records('agent_registrations'):
                configuration = store.get_record('configurations', registration.get('configuration_hash'))
                identity = new.target_identity(registration, configuration)
                if identity is None or policy is None:
                    continue
                for cutoff in cutoffs:
                    a = old.compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                    b = new.compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                    used = new.used_episodes(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
                    ids_ok = content_hash(sorted(e['episode_id'] for e, _ in used)) == b['episode_ids_hash'] and len(used) == b['summary']['verified_episodes']
                    compared += 1; equal += a == b; used_ok += ids_ok
                    rows.append({'registration_id': registration['registration_id'], 'cutoff': cutoff, 'equal': a == b,
                                 'verified_episodes': b['summary']['verified_episodes'], 'summary_hash': b['summary_hash'],
                                 'used_episodes_match_episode_ids_hash': ids_ok})
            for plan in plans:
                history = (plan.get('discovery') or {}).get('history')
                if history is None:
                    continue
                registration = store.get_record('agent_registrations', plan['agent_registration_id'])
                configuration = store.get_record('configurations', plan['configuration_hash'])
                outcomes = []
                for module in (old, new):
                    try:
                        module.verify(store, history, registration=registration, configuration=configuration, policy_hash=plan['initial_policy_hash'])
                        outcomes.append('VERIFIED')
                    except Exception as error:  # recorded, never hidden
                        outcomes.append(f'{type(error).__name__}')
                verified_same += outcomes[0] == outcomes[1]
                rows.append({'plan_campaign_id': plan['campaign_id'], 'protocol': plan['discovery']['protocol'],
                             'record_cutoff': history['record_cutoff'], 'verify_backup': outcomes[0], 'verify_new': outcomes[1]})
        finally:
            store.db.close()
        after = stat(path)
        report['stores'][str(path)] = {'rows': rows, 'store_files_unchanged': before == after}
        print(path, '| unchanged', before == after, '|', sum(1 for r in rows if 'equal' in r), 'history computations,',
              sum(1 for r in rows if r.get('equal')), 'equal |', [(r['plan_campaign_id'][:17], r['verify_backup'], r['verify_new']) for r in rows if 'plan_campaign_id' in r])
    report['totals'] = {'history_computations': compared, 'equal': equal, 'used_episodes_match': used_ok,
                        'saved_plan_verifications_agree': verified_same}
    print('TOTAL', report['totals'])
    Path(out).write_text(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
