"""Reviewer: rebuild the evidence summary the live diagnosis Mechanic of campaign b05ac280 (source 3) was given, from the
PRIVATE COPY of the saved store (ReadOnlyLabStore, query_only), with the product's own summarize_evidence. Offline, $0."""
import json, os, sys
from pathlib import Path
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'backend'))
from app.contracts.models import EvidenceBundle, canonical_json
from app.lab.diagnosis import summarize_evidence
from app.lab.storage import ReadOnlyLabStore
store = ReadOnlyLabStore(HERE / 'store-copy' / 'lab.sqlite3')
order = ['episode-3a4582d9215040fd99cd2ab799b19684', 'episode-40130001730c4d8a920380407672a97c',
         'episode-a3aab0bb9bde42acaeb6882b7f6cf3b3', 'episode-c5fb89143e934b84a280724f9846867e']
bundles = [EvidenceBundle.model_validate_json(canonical_json(store.get_record('evidence', e))) for e in order]
summary = summarize_evidence(bundles)
out = {'episodes': [{'episode_id': row['episode_id'], 'recorded_rows': len(row['observations']), 'report_row': row['report_row']}
                    for row in summary['episodes']],
       'reports_table': [{'row': i, 'evidence_ids': (r or {}).get('evidence_ids'), 'overall': (r or {}).get('overall'),
                          'notification_outcome': (r or {}).get('notification_outcome')} for i, r in enumerate(summary['reports'])]}
print(json.dumps(out, indent=1))
store.close()
