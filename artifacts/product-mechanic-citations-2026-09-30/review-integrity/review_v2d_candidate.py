"""Integrity review ($0, read-only copy): v2d's refused candidate request with and without the block, through the real
compaction. Scratch copy under /Users/shree/FaultLab_Scratch/review-integrity/, deleted after."""
import json, sys, shutil
from pathlib import Path
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/builder')
import guard  # noqa
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))
import citation_status_saved as saved
from test_loop_limits_mechanic_context import rebuild_v2d_request
from app.lab import citation_status, loop_limits
from app.lab.storage import ReadOnlyLabStore
from pydantic import TypeAdapter
from app.contracts.models import MechanicOutput, canonical_json
S = Path('/Users/shree/FaultLab_Scratch/review-integrity/store2'); S.mkdir(parents=True, exist_ok=True); t = S / 'lab.sqlite3'
saved.copy_read_only(saved.SAVED_STORE, t); out = {}
try:
    store = ReadOnlyLabStore(t)
    counter, ctx = rebuild_v2d_request(store)
    mech = type('M', (), {'provider': type('P', (), {'role_model': staticmethod(lambda role: saved.MECHANIC_MODEL)})(), 'metadata': None})()
    bound = lambda v: loop_limits.mechanic_request_bound(mech, 'mechanic.md', TypeAdapter(MechanicOutput), v)
    prot = [counter.source_episode_id, *counter.reproduction_trial_ids]
    for name, c in (('without_block', ctx), ('with_block', citation_status.attach(store, ctx, request_kind='mechanic_proposal'))):
        full = bound(c)
        req, summ = loop_limits.compact_request(c, request_kind='mechanic_proposal', protected_episode_ids=prot, store=store, bound=bound, full_bound=full)
        out[name] = {'full': full, 'attempts': [a['request_tokens'] for a in summ['attempts']], 'fits': summ['fits'], 'stage': summ['stages_applied'][-1],
                     'block_rows': len(req.get('native_citation_status', {}).get('episodes', [])) if req else None,
                     'block_identical_after_compaction': (req or {}).get('native_citation_status') == c.get('native_citation_status'),
                     'kept_in_full': len(req['development_evidence']['episodes']) if req else None,
                     'block_tokens_alone': bound({'native_citation_status': c['native_citation_status']}) - bound({}) if 'native_citation_status' in c else 0}
        if name == 'with_block':
            rows = c['native_citation_status']['episodes']
            out[name]['rows_all_decoded'] = all(r['cited'] == r['decoded'] and r['undecoded'] == [] for r in rows)
            listed = [e['episode_id'] for e in ctx['development_evidence']['episodes']] + [e['episode_id'] for it in ctx['challenge_counterexamples'] for e in it['evidence']['episodes']]
            out[name]['rows_equal_first_listing'] = [r['episode_id'] for r in rows] == list(dict.fromkeys(listed))
            out['headroom_at_stage3_tokens'] = loop_limits.COMPACTION_TARGET_TOKENS - out[name]['attempts'][-1]
            out['approx_tokens_per_row'] = round(out[name]['block_tokens_alone'] / len(rows), 1)
    store.close()
finally:
    saved.remove_copy(t); shutil.rmtree(S, ignore_errors=True); out['scratch_removed'] = not S.exists()
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True) + '\n'); print(json.dumps(out, indent=1, sort_keys=True))
