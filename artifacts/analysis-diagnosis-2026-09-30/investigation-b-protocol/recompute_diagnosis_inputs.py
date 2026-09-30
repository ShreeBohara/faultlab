"""Investigation B evidence ($0, read-only). Run from faultlab/backend with:
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python ../artifacts/analysis-diagnosis-2026-09-30/investigation-b-protocol/recompute_diagnosis_inputs.py

Opens the saved store immutable/read-only. No network, no provider, no writes except this folder's JSON.
For each diagnosed source of v2d-v2g it recomputes:
  * the intervention options the Diagnostician offered (app.referee.reducer.neighbors, first 4; id formula of
    app/lab/diagnosis.py:127-130), and checks them against the recorded intervention ids;
  * observed_control_trials / observed_treatment_trials the Mechanic saw (app.lab.diagnosis.observed_outcomes over
    the reduction's trials);
  * whether each raw diagnosis output passes the DiagnosticProposal schema and the id bindings.
"""
import json, sqlite3, sys
from pathlib import Path
from pydantic import TypeAdapter
from app.contracts.models import content_hash, FaultSpec, DiagnosticProposal
from app.referee.reducer import neighbors
from app.lab.diagnosis import observed_outcomes

STORE = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
OUT = Path(__file__).with_name('recomputed_diagnosis_inputs.json')
RUNS = {'campaign-ea66672d7a904bd8a011d6922790c963': 'v2d', 'campaign-37e66b6c3a544a4d9bde4161db6bf0aa': 'v2e',
        'campaign-53db74766f4d4635b94a0de89e492577': 'v2f', 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530': 'v2g'}

db = sqlite3.connect(f'file:{STORE}?mode=ro&immutable=1', uri=True)
def rec(kind, id):
    row = db.execute('select payload from records where kind=? and id=?', (kind, id)).fetchone()
    return json.loads(row[0]) if row else None
def recs(kind):
    return [(i, json.loads(p)) for i, p in db.execute('select id,payload from records where kind=?', (kind,))]

adapter = TypeAdapter(DiagnosticProposal)
outputs = [(i, o) for i, o in recs('mechanic_outputs') if o['prompt'] == 'diagnosis.md']
result = []
for diag_campaign_id, dc in recs('diagnostic_campaigns'):
    run = RUNS.get(dc['campaign_id'])
    if run is None: continue
    diag = rec('diagnostics', diag_campaign_id)
    cx = rec('counterexamples', dc['counterexample_id'])
    retained = FaultSpec.model_validate(rec('retained_recipes', cx['counterexample_id'])['retained_recipe'])
    reduction = rec('reductions', cx['counterexample_id'])
    # trial_outcomes as app.lab.diagnosis.trial_outcomes groups them (only the fields observed_outcomes reads)
    groups = {}
    # reduce() first re-runs the ORIGINAL recipe three times (app/referee/reducer.py:73); those trials are in
    # reduced.trials (so in the Mechanic's reduction summary) but not in any attempt's trial_ids. Recover them as this
    # campaign's reduction episodes with the original recipe's scenario hash.
    original_rerun = [i for i, e in recs('episodes') if e['campaign_id'] == dc['campaign_id'] and e['experiment_purpose'] == 'reduction'
                      and e['scenario_hash'] == reduction['original_recipe_hash']]
    for episode_id in original_rerun + [e for attempt in reduction['attempts'] for e in attempt['trial_ids']]:
            t = rec('trials', episode_id)
            value = {'scenario_hash': t['scenario_hash'], 'lifecycle': t['lifecycle'], 'outcome': t['outcome'],
                     'failed_checks': t['failed_checks'], 'fault_scheduled': t['fault_scheduled'], 'fault_triggered': t['fault_triggered']}
            groups.setdefault(json.dumps(value, sort_keys=True), {**value, 'episode_ids': []})['episode_ids'].append(episode_id)
    summary = {'trial_outcomes': list(groups.values())}
    options = []
    for change, treatment in neighbors(retained):
        if len(options) >= 4: break
        key = 'intervention-' + content_hash({'counterexample_id': cx['counterexample_id'], 'control': retained, 'treatment': treatment})[:24]
        options.append({'id': key, 'change': change, 'treatment_primitives': treatment.model_dump(mode='json')['primitives'],
                        'observed_treatment_trials': observed_outcomes(summary, content_hash(treatment), cx['target_invariant'])})
    mech = []
    for mid, o in outputs:
        if o.get('episode_id') != cx['source_episode_id']: continue
        raw = json.loads(o['raw'])
        try:
            adapter.validate_json(o['raw']); schema = 'OK'
        except Exception as error:
            schema = 'INVALID: ' + '; '.join(f"{e['loc']}:{e['type']}" for e in error.errors())
        mech.append({'mechanic_output_id': mid, 'request_id': o['request_id'], 'format_attempt': o['attempt'], 'model_id': o['model_id'],
                     'raw_proposed_kind': raw.get('proposed_kind'), 'raw_requested_intervention_id': raw.get('requested_intervention_id'),
                     'requested_id_is_offered_option': raw.get('requested_intervention_id') in [x['id'] for x in options],
                     'hypothesis_chars': len(raw.get('hypothesis', '')), 'schema': schema})
    result.append({'run': run, 'campaign_id': dc['campaign_id'], 'counterexample_id': cx['counterexample_id'],
                   'source_episode_id': cx['source_episode_id'], 'target_invariant': cx['target_invariant'],
                   'retained_primitives': retained.model_dump(mode='json')['primitives'],
                   'observed_control_trials': observed_outcomes(summary, content_hash(retained), cx['target_invariant']),
                   'offered_options': options, 'mechanic_diagnosis_outputs': sorted(mech, key=lambda m: (m['request_id'], m['format_attempt'])),
                   'diagnostic_id': diag['diagnostic_id'], 'recorded_proposed_kind': diag['proposed_kind'], 'verdict_kind': diag['kind'],
                   'recorded_intervention_ids': diag['intervention_ids'],
                   'intervention_results': {i: rec('interventions', i)['result'] for i in diag['intervention_ids']}})
result.sort(key=lambda r: (r['run'], r['counterexample_id']))
OUT.write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))
