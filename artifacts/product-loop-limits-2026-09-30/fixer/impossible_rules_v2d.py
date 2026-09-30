"""Fixer ($0, offline, pure function): would the reachability labeller's agent-independent IMPOSSIBLE rules (S1-S4,
app/lab/reachability.fixed_rules) refuse any of live run v2d's three challenge picks? And can its FORCED caller model
describe a candidate policy or a native agent? Reads the pick specs from the fixer's verify-v2d-picks.json (made from a
read-only store copy). Run from faultlab/backend."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401
from app.lab.reachability import UnsupportedTarget, caller_model_for, fixed_rules, readable_recipe  # noqa: E402
picks = json.loads((HERE / 'verify-v2d-picks.json').read_text())['picks']
candidate_rules = json.loads((HERE / 'verify-v2d-picks.json').read_text())['candidate_rules']
out = {'picks': [{'recipe': readable_recipe(p['fault_spec']), 'impossible_rule_per_fault': fixed_rules(p['fault_spec']['primitives'])} for p in picks]}
for agent, rules in (('reference', []), ('reference', candidate_rules), ('smolagents-v2', [])):
    try:
        caller_model_for(agent, rules); verdict = 'MODELLED'
    except UnsupportedTarget as error:
        verdict = error.code
    out.setdefault('forced_caller_model', []).append({'agent': agent, 'policy': 'candidate policy-c65cc08e rules' if rules else 'policy-v0', 'result': verdict})
print(json.dumps(out, indent=1))
