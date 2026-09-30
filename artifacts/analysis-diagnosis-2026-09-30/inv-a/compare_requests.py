"""Investigation A ($0, offline): field-by-field comparison of the five rebuilt diagnosis requests.

Run from faultlab/backend with the project .venv after rebuild_diagnosis_requests.py:
  ../.venv/bin/python -B ../artifacts/analysis-diagnosis-2026-09-30/inv-a/compare_requests.py
Reads only the *-diagnosis-context.json / *-diagnosis-request.json files next to it; writes comparison.json.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'product-mechanic-citations-2026-09-30' / 'fixer'))
import guard  # noqa: E402,F401
from app.contracts.models import canonical_json  # noqa: E402
from app.contracts.tokens import deepseek_v4_encoding  # noqa: E402

NAMES = ['v2d-dev5', 'v2e-dev5', 'v2f-dev5', 'v2g-dev5', 'v2g-dev6']
OUTCOME = {'v2d-dev5': 'POLICY_GAP', 'v2e-dev5': 'INCONCLUSIVE', 'v2f-dev5': 'POLICY_GAP', 'v2g-dev5': 'INCONCLUSIVE', 'v2g-dev6': 'POLICY_GAP'}
TOK = deepseek_v4_encoding()
ID = re.compile(r'\b(episode|evidence|counterexample|intervention|diagnostic|campaign)-[0-9a-f]{20,32}\b|\b[0-9a-f]{64}\b')


def tokens(value):
    text = value if isinstance(value, str) else canonical_json(value)
    return len(TOK.encode(text, add_special_tokens=False).ids)


def normalize(value):
    names = {}
    def swap(match):
        key = match.group(0)
        if key not in names:
            kind = match.group(1) or 'hash'
            names[key] = f'<{kind}-{sum(1 for k in names.values() if k.startswith("<" + kind)) + 1}>'
        return names[key]
    return json.loads(ID.sub(swap, canonical_json(value)))


def episode_rows(summary):
    rows = []
    for e in summary['episodes']:
        seq = [f"t{tick}:{summary['results'][ri].get('tool')}/{summary['results'][ri].get('transport')}/{summary['results'][ri].get('status')}"
               for _, tick, ri in e['observations']]
        report = summary['reports'][e['report_row']]
        failed = [c['check_id'] for c in summary['checks'][e['check_row']] if c.get('passed') is False]
        passed = [c['check_id'] + ':' + c['category'] for c in summary['checks'][e['check_row']] if c.get('passed') is True]
        rows.append({'episode_id': e['episode_id'], 'rows': seq, 'report': report, 'failed_checks': failed, 'passed_checks': passed})
    return rows


def keyword_counts(text):
    words = {'evidence': r'evidence', 'label': r'label', 'cite/citation': r'\bcit(e|ed|es|ation|ations)\b',
             'never shown / not shown / unshown': r'never shown|not shown|unshown|never saw',
             'decode': r'decod', 'truthful': r'truthful', 'confirm': r'confirm'}
    return {k: len(re.findall(p, text, flags=re.I)) for k, p in words.items()}


def main():
    contexts = {n: json.loads((HERE / f'{n}-diagnosis-context.json').read_text()) for n in NAMES}
    requests = {n: json.loads((HERE / f'{n}-diagnosis-request.json').read_text()) for n in NAMES}
    fields = sorted(set().union(*[c.keys() for c in contexts.values()]))
    sizes = {n: {f: ({'chars': len(canonical_json(c[f])), 'tokens': tokens(c[f])} if f in c else None) for f in fields} for n, c in contexts.items()}
    for n in NAMES:
        system, user = requests[n]['turns'][0]['messages']
        sizes[n]['_system_prompt'] = {'chars': len(system['content']), 'tokens': tokens(system['content'])}
        sizes[n]['_user_message'] = {'chars': len(user['content']), 'tokens': tokens(user['content'])}
        ac = contexts[n]['runtime_contract']['actor_contract']
        for sub in ('memory', 'adapter_protocol', 'task_contract', 'transport_contract'):
            sizes[n]['runtime_contract.actor_contract.' + sub] = {'chars': len(canonical_json(ac[sub]) if not isinstance(ac[sub], str) else ac[sub]), 'tokens': tokens(ac[sub])}
    dev5 = NAMES[:4]
    equality = {}
    for f in fields:
        present = [n for n in dev5 if f in contexts[n]]
        norm = {n: canonical_json(normalize(contexts[n][f])) for n in present}
        groups = {}
        for n in present: groups.setdefault(norm[n], []).append(n)
        equality[f] = {'present_in': present, 'absent_in': [n for n in dev5 if n not in present],
                       'identical_after_id_normalization_groups': list(groups.values())}
    # Sub-field equality inside runtime_contract (dev-5 only)
    rc_equality = {}
    for sub in contexts['v2d-dev5']['runtime_contract']:
        groups = {}
        for n in dev5: groups.setdefault(canonical_json(normalize(contexts[n]['runtime_contract'][sub])), []).append(n)
        rc_equality[sub] = list(groups.values())
    ac_equality = {}
    for sub in contexts['v2d-dev5']['runtime_contract']['actor_contract']:
        groups = {}
        for n in dev5: groups.setdefault(canonical_json(contexts[n]['runtime_contract']['actor_contract'][sub]), []).append(n)
        ac_equality[sub] = list(groups.values())
    interventions = {n: [{'id': i['id'], 'change': i['change'], 'prediction': i['prediction'], 'expected_result': i['expected_result'],
                          'treatment_primitives': i['treatment_fault_spec']['primitives'],
                          'observed_treatment_trials': {k: v for k, v in (i['observed_treatment_trials'] or {}).items() if k != 'episode_ids'}}
                         for i in contexts[n]['interventions']] for n in NAMES}
    evidence = {n: episode_rows(contexts[n]['observations']) for n in NAMES}
    reduction = {n: [{k: g[k] for k in ('outcome', 'failed_checks', 'actor_calls', 'http_attempts', 'fault_scheduled', 'fault_triggered')}
                     | {'n': len(g['episode_ids']), 'scenario': g['scenario_hash'][:8]} for g in contexts[n]['reduction']['trial_outcomes']] for n in NAMES}
    keywords = {}
    for n in NAMES:
        c = contexts[n]
        keywords[n] = {'whole_user_message': keyword_counts(requests[n]['turns'][0]['messages'][1]['content']),
                       'runtime_contract.actor_contract.memory': keyword_counts(c['runtime_contract']['actor_contract']['memory']),
                       'runtime_contract.actor_contract.adapter_protocol': keyword_counts(canonical_json(c['runtime_contract']['actor_contract']['adapter_protocol'])),
                       'observations.interpretation': keyword_counts(c['observations']['interpretation']),
                       'native_citation_status': keyword_counts(canonical_json(c['native_citation_status'])) if 'native_citation_status' in c else None,
                       'system_prompt': keyword_counts(requests[n]['turns'][0]['messages'][0]['content'])}
    result = {'recorded_outcome': OUTCOME, 'sizes': sizes, 'dev5_top_level_field_equality': equality,
              'dev5_runtime_contract_subfield_equality': rc_equality, 'dev5_actor_contract_subfield_equality': ac_equality,
              'interventions': interventions, 'observed_control_trials': {n: {k: v for k, v in (contexts[n]['observed_control_trials'] or {}).items() if k != 'episode_ids'} for n in NAMES},
              'evidence_rows': evidence, 'reduction_trial_outcomes': reduction,
              'native_citation_status_rows': {n: contexts[n].get('native_citation_status', {}).get('episodes') for n in NAMES},
              'keyword_counts': keywords}
    (HERE / 'comparison.json').write_text(json.dumps(result, indent=1, sort_keys=True) + '\n')
    print(json.dumps({'sizes': {n: {k: v for k, v in s.items() if v} for n, s in sizes.items()},
                      'equality': {f: e['identical_after_id_normalization_groups'] for f, e in equality.items()},
                      'rc_equality': rc_equality, 'ac_equality': ac_equality, 'keywords': keywords}, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
