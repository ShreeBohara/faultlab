"""Verifier probe ($0, offline, in-process; writes nothing in the repo): the fixer's "every fault" rule, its declaration,
the saved-plan model, the request note and the challenge re-plan state, checked directly against app.lab.fireability.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/verify/spot/rule_probe.py
Synthetic table with TWO refused rows (the real native-v2b table has one) so that "every" vs "any" and "two refused
targets" are distinguishable. Scripted picks are fixture text, not model evidence.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import vguard  # noqa: F401,E402
BACKEND = os.getcwd()
assert BACKEND.endswith('/faultlab/backend'), BACKEND
sys.path[:0] = [BACKEND, os.path.join(BACKEND, 'tests'), os.path.join(BACKEND, 'tests', 'lab')]
from app.contracts.models import ExplorerOutput, canonical_json, content_hash  # noqa: E402
from app.lab import fireability as fb  # noqa: E402
from app.lab.agent_history import HistoryChanged  # noqa: E402
from app.lab.run_plans import ExplorerSelectionPlan  # noqa: E402
from pydantic import ValidationError  # noqa: E402

results = []
def check(name, ok, detail=''):
    results.append({'check': name, 'ok': bool(ok), 'detail': detail})

def P(kind, tool, service, start, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': start, 'parameters': parameters}

STATUS = P('F4', 'get_operation_status', 'orders', 1, failure_count=1)
STATUS_2 = P('F4', 'get_operation_status', 'orders', 1, failure_count=2)
DELAYED = P('F2', 'update_order', 'orders', 1, completion_delay_ticks=3, terminal_status='SUCCEEDED', failure_code=None)
CONFIRM = P('F4', 'send_confirmation', 'notifications', 1, failure_count=1)
F1_UPD = P('F1', 'update_order', 'orders', 1, response_delay_ms=2000)

def row(kind, service, tool, verified, fired):
    return {'kind': kind, 'target_service': service, 'target_tool': tool, 'verified_episodes': verified,
            'fired_episodes': fired, 'fired_share': f'{fired}/{verified}', 'status': fb.row_status(verified, fired)}

rows = sorted([row('F2', 'orders', 'update_order', 10, 10), row('F4', 'orders', 'get_operation_status', 4, 0),
               row('F4', 'notifications', 'send_confirmation', 5, 2)], key=lambda r: (r['kind'], r['target_service'], r['target_tool']))
table = {'schema_version': fb.TABLE_SCHEMA, 'meaning': fb.MEANING, 'history_summary_hash': 'a' * 64,
         'history_episode_ids_hash': 'b' * 64, 'record_cutoff': 1, 'verified_episodes': 12, 'rows': rows,
         'refused_targets': [fb.refused_text(r) for r in rows if r['status'] == 'REFUSED']}
block = {**fb.declaration(), 'table': table, 'table_hash': content_hash(table)}
check('synthetic block validates against the saved-plan model', ExplorerSelectionPlan.model_validate(block) is not None)
check('two REFUSED rows in the synthetic table', [r['status'] for r in rows].count('REFUSED') == 2, json.dumps([(r['target_tool'], r['status']) for r in rows]))

def pick(*primitives):
    return ExplorerOutput.model_validate_json(canonical_json({'fault_spec': {'seed': 1, 'primitives': list(primitives)},
                                                              'hypothesis': 'verifier probe'}))

cases = [
    ('lone status read (v2d/v2f pick)', [STATUS], fb.PICK_REFUSED),
    ('pending upgrade + status read (integrity scenario A)', [DELAYED, STATUS], fb.PICK_ALLOWED),
    ('status read + pending upgrade (order reversed)', [STATUS, DELAYED], fb.PICK_ALLOWED),
    ('two faults, both on REFUSED targets', [STATUS, CONFIRM], fb.PICK_REFUSED),
    ('two faults on the same REFUSED target', [STATUS, STATUS_2], fb.PICK_REFUSED),
    ('REFUSED target + target not in the table', [STATUS, F1_UPD], fb.PICK_ALLOWED),
    ('allowed target only', [DELAYED], fb.PICK_ALLOWED),
    ('not-in-table target only', [F1_UPD], fb.PICK_ALLOWED),
]
decisions = {}
for challenge in (True, False):
    for name, prims, want in cases:
        session = fb.Session(block, discovery_requests_max=8)
        ctx = {'campaign_id': 'c1', 'candidate_hash': 'h', 'incumbent_hash': 'i', 'proposal_index': 0, 'selection_index': 0}
        if challenge: session.challenge_state(ctx)
        decision, selected = fb.decide(session, ctx, pick(*prims), None, challenge=challenge, provenance='model')
        ok = decision['status'] == want and ((selected is None) == (want == fb.PICK_REFUSED))
        mixed_named = True
        if want == fb.PICK_ALLOWED and any(p is STATUS for p in prims):
            mixed_named = (decision['reason'] or '').startswith('Allowed: F4 on get_operation_status (orders) is REFUSED') and \
                any(t['status'] == 'REFUSED' for t in decision['targets'])
        if want == fb.PICK_ALLOWED and not any(p in (STATUS, STATUS_2, CONFIRM) for p in prims):
            mixed_named = decision['reason'] is None
        check(f"{'challenge' if challenge else 'discovery'}: {name} -> {want}", ok and mixed_named,
              f"got {decision['status']}; reason={decision['reason']!r}")
        decisions[f"{'challenge' if challenge else 'discovery'}: {name}"] = {k: decision[k] for k in ('status', 'reason', 'targets', 'refused_targets')}

# invalid output (no fallback) is never guessed
session = fb.Session(block, discovery_requests_max=8)
d, s = fb.decide(session, {'proposal_index': 0}, None, 'INVALID_EXPLORER_OUTPUT', challenge=True, provenance='invalid_slot')
check('invalid output -> INVALID_OUTPUT, no pick', d['status'] == fb.PICK_INVALID and s is None)

# challenge re-plan bookkeeping: refused first pick -> pending re-plan; refused re-plan -> no further pending
session = fb.Session(block, discovery_requests_max=8)
ctx0 = {'campaign_id': 'c1', 'candidate_hash': 'h', 'incumbent_hash': 'i', 'proposal_index': 0}
extra0 = fb.request_context(session, ctx0, challenge=True)
check('first challenge request is slot_request 1 and carries the rule, table, note', extra0['slot_request'] == 1 and
      extra0['history_fireability']['note'] == fb.EXPLORER_NOTE and extra0['history_fireability']['rows'] == rows and
      extra0['explorer_selection_protocol'] == fb.EXPLORER_SELECTION_V3)
d0, _ = fb.decide(session, {**ctx0, **extra0}, pick(STATUS), None, challenge=True, provenance='model')
fb.after_pick(session, 'sel-0', d0, challenge=True)
ctx1 = {**ctx0, 'proposal_index': 1}
extra1 = fb.request_context(session, ctx1, challenge=True)
check('after a refusal the next challenge request is its re-plan', extra1['slot_request'] == 2 and extra1['replan_of'] == 'sel-0'
      and 'every fault in it targets' in extra1['slot_feedback']['instruction'] and len(extra1['history_fireability']['refused_picks']) == 1)
d1, _ = fb.decide(session, {**ctx1, **extra1}, pick(STATUS_2), None, challenge=True, provenance='model')
fb.after_pick(session, 'sel-1', d1, challenge=True)
extra2 = fb.request_context(session, {**ctx0, 'proposal_index': 2}, challenge=True)
check('a refused re-plan gets no further re-plan', d1['status'] == fb.PICK_REFUSED and extra2['slot_request'] == 1 and 'replan_of' not in extra2
      and 'already the re-plan' in d1['reason'])
# a new challenge (other candidate) never shares refusals or the pending re-plan
extra_other = fb.request_context(session, {'campaign_id': 'c1', 'candidate_hash': 'h2', 'incumbent_hash': 'i', 'proposal_index': 0}, challenge=True)
check('a second challenge in the same Session starts clean', extra_other['slot_request'] == 1 and extra_other['history_fireability']['refused_picks'] == [])

# declaration and the saved-plan model
decl = fb.declaration()
check('declaration names pick_refused_when = every_fault_on_a_refused_target', decl['pick_refused_when'] == 'every_fault_on_a_refused_target')
check('declaration hash', True, content_hash(decl))
for other in ('any_fault_on_a_refused_target', 'every', None):
    try:
        ExplorerSelectionPlan.model_validate({**block, 'pick_refused_when': other}); ok = False
    except ValidationError:
        ok = True
    check(f'saved-plan model refuses pick_refused_when={other!r}', ok)
try:
    ExplorerSelectionPlan.model_validate({k: v for k, v in block.items() if k != 'pick_refused_when'}); ok = False
except ValidationError:
    ok = True
check('saved-plan model refuses a block without pick_refused_when (the builder\'s shape)', ok)
try:
    fb.verify(None, {**block, 'pick_refused_when': 'any_fault_on_a_refused_target'}, None); ok = False
except HistoryChanged:
    ok = True
check('fireability.verify refuses a frozen block whose rule is not the installed one', ok)
check('RULE fits the model (<= 2400 chars)', len(fb.RULE) <= 2400, str(len(fb.RULE)))
check('MEANING fits the model (<= 800 chars)', len(fb.MEANING) <= 800, str(len(fb.MEANING)))
check('RULE states the every-fault form', 'A pick is refused only if every one of its faults targets a REFUSED target' in fb.RULE)
check('RULE says the table is not neutral', 'It is not neutral' in fb.RULE)
check('MEANING states the every-fault form', 'a pick whose every fault is on a REFUSED target' in fb.MEANING)
check('the builder\'s any-fault sentence is gone', 'with a fault on a REFUSED' not in fb.RULE and 'any of its' not in fb.RULE)

out = {'ok': all(r['ok'] for r in results), 'passed': sum(r['ok'] for r in results), 'total': len(results), 'checks': results, 'decisions': decisions}
print(json.dumps(out, indent=1))
