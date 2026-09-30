"""Integrity review ($0, offline, read-only): every campaign plan saved in every store under /Users/shree/FaultLab_Runs
still parses under this build's SavedRunPlan and re-serialises to exactly its saved bytes (canonical JSON), keeps its
plan hash, declares no explorer_selection block, and keeps its own evidence-retry protocol. Also reports the automatic
evidence-retry cap each saved plan would run with (read from the plan, as EvidenceWait does).

Stores are opened ONLY with sqlite's mode=ro&immutable=1 URI; only kind='campaign_plans' rows are read.
Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/review-integrity/saved_plans_roundtrip.py
"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.lab.run_plans import SavedRunPlan  # noqa: E402

out = []
for path in sorted(Path('/Users/shree/FaultLab_Runs').rglob('lab.sqlite3')):
    con = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True)
    try:
        plans = [(i, json.loads(p)) for i, p in con.execute("select id, payload from records where kind='campaign_plans'")]
    except sqlite3.DatabaseError as error:
        out.append({'store': str(path), 'error': str(error)}); continue
    finally:
        con.close()
    for ident, plan in plans:
        row = {'store': str(path).replace('/Users/shree/FaultLab_Runs/', ''), 'campaign': ident, 'mode': plan.get('mode'),
               'discovery': (plan.get('discovery') or {}).get('protocol'),
               'evidence_retry': (plan.get('evidence_retry') or {}).get('protocol'),
               'evidence_retry_cap': (plan.get('evidence_retry') or {}).get('automatic_retries_per_campaign'),
               'has_explorer_selection': 'explorer_selection' in plan,
               'plan_hash_ok': plan.get('plan_hash') == content_hash({k: v for k, v in plan.items() if k != 'plan_hash'})}
        try:
            checked = SavedRunPlan.model_validate_json(canonical_json(plan)).model_dump(mode='json')
            row['parses'] = True
            row['roundtrip_byte_identical'] = canonical_json(checked) == canonical_json(plan)
            row['checked_sha'] = content_hash(checked)
        except Exception as error:
            row['parses'] = False; row['error'] = f'{type(error).__name__}: {str(error)[:300]}'
        out.append(row)

print(json.dumps({'plans': out, 'total': len(out),
                  'all_parse': all(r.get('parses') for r in out if 'campaign' in r),
                  'all_roundtrip_identical': all(r.get('roundtrip_byte_identical') for r in out if 'campaign' in r),
                  'any_explorer_selection': any(r.get('has_explorer_selection') for r in out)}, indent=1))
