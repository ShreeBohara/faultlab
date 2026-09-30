"""Fixer ($0, offline): the dashboard poll's record reads for history fireability, old full scan vs the fixed read.

A scratch copy of the saved native-v2b store (read with mode=ro&immutable=1 through the test suite's copy helper) is
opened outside the Desktop; for each saved campaign, the builder's full-scan algorithm (as kept in
test_history_fireability_review_fixes.full_scan_summary) and the fixed fireability.campaign_summary are timed 20 times.
No saved campaign declares the rule, so both return no decisions there; the timing isolates what each poll reads.
Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/fixer/poll_cost_check.py
"""
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401
sys.path[:0] = [str(Path.cwd() / 'tests' / 'lab'), str(Path.cwd() / 'tests')]
from citation_status_saved import copy_read_only, remove_copy  # noqa: E402
from app.lab import fireability  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from test_history_fireability_review_fixes import full_scan_summary  # noqa: E402

SAVED = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer/poll-cost')
SCRATCH.mkdir(parents=True, exist_ok=True)
target = SCRATCH / 'lab.sqlite3'
copy_read_only(SAVED, str(target))
store = LabStore(str(target))
block = {'protocol': fireability.EXPLORER_SELECTION_V3, 'table_hash': 'a' * 64, 'table': {'refused_targets': []}}
try:
    campaigns = [row['campaign_id'] for row in store.list_records('campaigns')]
    selection_bytes = sum(len(json.dumps(row)) for row in store.list_records('selections'))
    result = {'selections': len(store.list_records('selections')), 'selection_json_bytes': selection_bytes, 'campaigns': len(campaigns)}
    for name, fn in (('builder_full_scan', full_scan_summary), ('fixed_campaign_scoped', fireability.campaign_summary)):
        times = []
        for _ in range(20):
            for ident in campaigns:
                started = time.perf_counter(); out = fn(store, ident, block); times.append(time.perf_counter() - started)
                assert out['decisions'] == [] and out['slots_without_request'] == []
        times.sort()
        result[name] = {'median_ms_per_poll': round(1000 * times[len(times) // 2], 2), 'max_ms': round(1000 * times[-1], 2)}
    print(json.dumps(result, indent=1))
finally:
    store.close() if hasattr(store, 'close') else None
    print('scratch copy removed:', remove_copy(str(target)))
    shutil.rmtree(SCRATCH.parent, ignore_errors=True)
