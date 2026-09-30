"""Verifier ($0, offline, read-only): spot-check the corrected v2d facts (I-MEDIUM-2 / P-MED-1) and the token breakdown.

Copies /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (opened ?mode=ro&immutable=1) to a scratch folder
OUTSIDE the Desktop, reads it with ReadOnlyLabStore, prints JSON, deletes the copy. Run from the scratch tree's backend/.
"""
import json, os, shutil, sqlite3, sys
from pathlib import Path
V = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/verify'
sys.path[:0] = [V, os.getcwd(), os.path.join(os.getcwd(), 'tests'), os.path.join(os.getcwd(), 'tests', 'lab')]
import vguard  # noqa: F401
from app.lab.storage import ReadOnlyLabStore
from app.lab import loop_limits
from app.lab.reachability import readable_recipe

SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/verify-loop-limits/v2d-copy')
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'
shutil.rmtree(SCRATCH, ignore_errors=True); SCRATCH.mkdir(parents=True)
copy = SCRATCH / 'v2d.sqlite3'
src = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
try:
    src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
finally:
    dst.close(); src.close()
out = {}
try:
    store = ReadOnlyLabStore(copy)
    try:
        q = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == V2D)
        cand = q['candidate_hash']
        reach = loop_limits.candidate_reach(store, V2D, cand)
        out['source_validation_basis'] = reach
        challenge = store.get_record('challenges', q['challenge_ref'])
        out['challenge'] = {k: challenge.get(k) for k in ('status', 'stopping_reason', 'failed_checks')}
        picks = []
        for ref in challenge['selection_refs']:
            spec = (store.get_record('selections', ref).get('output') or {}).get('fault_spec')
            picks.append(readable_recipe(spec) if spec else None)
        out['picks_in_order'] = picks
        calls = {}
        for call in store.list_records('tool_calls'):
            calls.setdefault(call.get('episode_id'), []).append(call)
        batches = [b for b in store.list_records('evaluations') if b.get('purpose') == 'challenge' and b.get('candidate_hash') == cand]
        out['challenge_batches'] = []
        for b in batches:
            arms = {}
            for t in b['trials']:
                targets = loop_limits._call_targets(store, t['episode_id'], calls.get(t['episode_id'], []))
                a = arms.setdefault(t['arm'], {'episodes': 0, 'fault_triggered': 0, 'agent_orders_status_reads': [], 'agent_send_confirmation': 0,
                                               'agent_notifications_status': 0, 'policy_targets': set()})
                a['episodes'] += 1; a['fault_triggered'] += bool(t['fault_triggered'])
                a['agent_orders_status_reads'].append(sum(1 for c, x in targets if c == 'actor' and x == 'get_operation_status:orders'))
                a['agent_send_confirmation'] += any(c == 'actor' and x.startswith('send_confirmation') for c, x in targets)
                a['agent_notifications_status'] += any(c == 'actor' and x == 'get_operation_status:notifications' for c, x in targets)
                a['policy_targets'] |= {x for c, x in targets if c != 'actor'}
            for a in arms.values(): a['policy_targets'] = sorted(a['policy_targets'])
            spec = b.get('fault_spec') or ((b.get('trials') or [{}])[0].get('fault_spec'))
            out['challenge_batches'].append({'batch_id': b.get('batch_id'), 'scenario_hashes': sorted({t['scenario_hash'][:12] for t in b['trials']}),
                                             'arms': arms})
        grammar = ['get_order:orders', 'update_order:orders', 'get_operation_status:orders', 'send_confirmation:notifications',
                   'get_operation_status:notifications']
        out['targets_the_withdrawn_rule_would_refuse'] = [g for g in grammar if g not in reach['agent']]
        # Token breakdown (design note section 1): rebuild the refused request with the product test's own rebuild helper.
        from test_loop_limits_mechanic_context import rebuild_v2d_request
        from types import SimpleNamespace
        from pydantic import TypeAdapter
        from app.contracts.models import MechanicOutput
        counter, context = rebuild_v2d_request(store)
        m = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: 'deepseek-ai/DeepSeek-V4-Pro-0813'), metadata=None)
        bound = lambda v: loop_limits.mechanic_request_bound(m, 'mechanic.md', TypeAdapter(MechanicOutput), v)
        full = bound(context)
        cc = context['challenge_counterexamples']
        out['tokens'] = {'full': full,
                         'challenge_counterexamples': full - bound({**context, 'challenge_counterexamples': []}),
                         'challenge_evidence_table': full - bound({**context, 'challenge_counterexamples': [{k: v for k, v in cc[0].items() if k != 'evidence'}]}),
                         'development_evidence': full - bound({k: v for k, v in context.items() if k != 'development_evidence'})}
    finally:
        store.close()
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)
    out['scratch_copy_removed'] = not SCRATCH.exists()
print(json.dumps(out, indent=1, sort_keys=True, default=str))
