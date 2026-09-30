"""Verifier ($0, offline): where the two test_history_fireability failures (14 == 8 and 36 == 30) come from. Copies the saved
native-v2b store via sqlite backup from file:...?mode=ro&immutable=1 to the scratch folder, counts the saved Explorer picks
the failing test counts (non-challenge, not every primitive on the orders status read, provenance not history_replay) per
campaign, and lists each campaign's plan time. If live run v2g's campaign (campaign-d8d1e8cc..., the probe's sampling
source) holds exactly the 6 extra picks, the failure is the saved store's growth, not this change. Copy deleted after."""
import hashlib, json, sqlite3, sys, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vguard  # noqa
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend')
from app.lab.storage import ReadOnlyLabStore
SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCR = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/fireability-origin'); SCR.mkdir(parents=True, exist_ok=True)
before = hashlib.sha256(SAVED.read_bytes()).hexdigest()
copy = SCR / 'copy.sqlite3'
src = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy); src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE'); dst.close(); src.close()
store = ReadOnlyLabStore(copy)
per = {}
for s in store.list_records('selections'):
    spec = (s.get('output') or {}).get('fault_spec')
    if spec is None or s.get('provenance') == 'history_replay': continue
    status_read = all(p['target_tool'] == 'get_operation_status' and p['target_service'] == 'orders' for p in spec['primitives'])
    key = (s.get('context') or {}).get('campaign_id') or '?'
    row = per.setdefault(key, {'discovery_allowed': 0, 'discovery_refused': 0, 'challenge_allowed': 0, 'challenge_refused': 0})
    row[('challenge_' if s.get('challenge') else 'discovery_') + ('refused' if status_read else 'allowed')] += 1
plans = {p['campaign_id']: p.get('created_at') or p.get('frozen_at') for p in store.list_records('campaign_plans')}
store.close()
for suffix in ('', '-wal', '-shm', '-journal'): Path(str(copy) + suffix).unlink(missing_ok=True)
SCR.rmdir()
after = hashlib.sha256(SAVED.read_bytes()).hexdigest()
v2g = 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530'
tot = {k: sum(r[k] for r in per.values()) for k in ('discovery_allowed', 'discovery_refused', 'challenge_allowed', 'challenge_refused')}
wo = {k: sum(r[k] for c, r in per.items() if c != v2g) for k in tot}
print(json.dumps({'per_campaign': per, 'plan_times': plans, 'totals': tot, 'totals_without_v2g': wo, 'v2g_campaign': v2g,
                  'store_sha256_unchanged': before == after}, indent=1))
