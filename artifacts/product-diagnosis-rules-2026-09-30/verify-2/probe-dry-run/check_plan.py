"""Verifier-2: independent checks of the probe plan written by the dry run ($0, offline, no network).
Checks: plan hash self-consistency; GUIDE = CONTROL + exactly the product diagnosis_guide block (product code) with the
campaign's own task text; token deltas; C6 sentence absent; CONTROL/REPAIR requests byte-identical to the pre-follow-up
plan (verify/probe-dry-run/plan-out); the declaration hash in the plan and template."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vguard  # noqa: F401
BACKEND = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend'
sys.path.insert(0, BACKEND); os.chdir(BACKEND)
from app.contracts.models import content_hash
from app.lab import diagnosis_guide as dg
HERE = os.path.dirname(os.path.abspath(__file__))
plan = json.load(open(f'{HERE}/plan-out/plan.json')); reqs = json.load(open(f'{HERE}/plan-out/requests.json'))
old_reqs = json.load(open(f'{HERE}/../../verify/probe-dry-run/plan-out/requests.json'))
old_plan = json.load(open(f'{HERE}/../../verify/probe-dry-run/plan-out/plan.json'))
tmpl = json.load(open(f'{HERE}/plan-out/DECLARATION.template.json'))
ok = []
def check(name, cond): ok.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name)
check('plan_hash self-consistent', plan['plan_hash'] == content_hash({k: v for k, v in plan.items() if k != 'plan_hash'}))
check('plan_hash is 91ca47e4...', plan['plan_hash'].startswith('91ca47e4'))
check('template plan_hash equals plan', tmpl.get('plan_hash') == plan['plan_hash'])
check('template harness sha equals plan', tmpl.get('harness_sha256') == plan['harness_sha256'])
print('plan diagnosis_guide field:', json.dumps(plan['diagnosis_guide'])[:300])
check('plan declares the installed Rule 2 declaration hash', content_hash(dg.declaration()) in json.dumps(plan['diagnosis_guide']))
check('Rule 2 declaration hash is def60594...', content_hash(dg.declaration()).startswith('def60594'))
check('schedule has 140 calls', len(plan['schedule']) == 140)
check('14 request keys', len(reqs) == 14)
tok = {k: v for k, v in (plan.get('requests') or {}).items()}
C6 = "citations met it"
check('C6 sentence absent from requests.json', C6 not in json.dumps(reqs) and 'where C6 passed' not in json.dumps(reqs))
for key, messages in sorted(reqs.items()):
    run, arm = key.split('/')
    if arm == 'GUIDE':
        control = reqs[f'{run}/CONTROL']
        g_user = json.loads(messages[-1]['content']); c_user = json.loads(control[-1]['content'])
        added = set(g_user) - set(c_user)
        same_other = all(g_user[k] == c_user[k] for k in c_user) and messages[:-1] == control[:-1] and set(c_user) <= set(g_user)
        block = g_user.get('diagnosis_guide')
        expected = dg.block(block['task']) if block else None
        check(f'{key}: adds only diagnosis_guide, all other keys and messages identical', added == {'diagnosis_guide'} and same_other)
        check(f'{key}: block == product dg.block(task) and checks_note == CHECKS_NOTE', block == expected and block['checks_note'] == dg.CHECKS_NOTE)
    else:
        check(f'{key}: byte-identical to the pre-follow-up plan', json.dumps(messages, sort_keys=True) == json.dumps(old_reqs.get(key), sort_keys=True))
print('per-request token entries:', json.dumps(plan['requests'])[:0])
for key, info in sorted(plan['requests'].items()):
    run, arm = key.split('/')
    if arm == 'GUIDE':
        d = info['input_tokens'] - plan['requests'][f'{run}/CONTROL']['input_tokens']
        check(f'{key}: GUIDE - CONTROL = 608 tokens (got {d})', d == 608)
old_keys = set(old_plan) | set(plan)
diffs = [k for k in sorted(old_keys) if old_plan.get(k) != plan.get(k)]
print('top-level plan keys that differ from the pre-follow-up plan:', diffs)
print('charge:', json.dumps(plan['charge']))
print('sampling temperature:', plan['sampling'].get('temperature'))
print(f'{sum(ok)} of {len(ok)} checks passed')
