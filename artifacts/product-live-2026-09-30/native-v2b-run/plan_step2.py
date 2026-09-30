"""Step 2 planner (PLAN.md section 4): only on a GO in go-decision.json. Creates the v3-history Learn campaign in the
same store, freezes the history, writes DECLARATION-step2.json with its sha256. Does not Start."""
import json, urllib.request, pathlib, hashlib, datetime, sys
B = 'http://127.0.0.1:8000'; R = pathlib.Path('artifacts/product-live-2026-09-30/native-v2b-run')
go = json.loads((R / 'go-decision.json').read_text())
if go['decision'] != 'GO': sys.exit('NO_GO: step 2 is not run')
def get(p):
    with urllib.request.urlopen(B + p, timeout=15) as r: return json.loads(r.read())
def post(p, body, sid):
    req = urllib.request.Request(B + p, data=json.dumps(body).encode(), method='POST', headers={'Content-Type': 'application/json', 'X-FaultLab-Store-Identity': sid})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())
sid = (R / 'store-identity.txt').read_text().strip(); reg = json.loads((R / 'registration.json').read_text())
cs = get('/api/config/status'); assert cs.get('active_campaign_id') is None, cs.get('active_campaign_id')
ro = get('/api/run-options')
camp = post('/api/planned-campaigns', {'expected_store_identity': sid, 'expected_setup_hash': ro['setup_hash'], 'task_definition_id': 'orders.upgrade_then_confirm/v1',
    'agent_registration_id': reg['registration_id'], 'mode': 'learn', 'config_profile_id': 'live-v1',
    'task_text': 'Upgrade the authorized order to express shipping, then record one truthful confirmation.', 'order_id': 'order-native-baseline',
    'discovery_protocol': 'faultlab-discovery/v3-history'}, sid)
C = camp['campaign_id']; plan = get(f'/api/campaigns/{C}/plan'); conf = get(f'/api/campaigns/{C}/configuration')
for n, d in (('learn-campaign', camp), ('learn-plan-before', plan), ('learn-configuration-before', conf)): (R / f'{n}.json').write_text(json.dumps(d, indent=2))
def find(d, keys, out=None):
    out = {} if out is None else out
    if isinstance(d, dict):
        for k, v in d.items():
            if k in keys and isinstance(v, (str, int, float, bool)): out[k] = v
            find(v, keys, out)
    elif isinstance(d, list):
        for v in d: find(v, keys, out)
    return out
pl = plan.get('plan', plan); disc = pl.get('discovery', {})
hf = find(disc, {'summary_hash', 'record_cutoff', 'status', 'protocol', 'episode_ids_hash', 'adapter_entrypoint_id'})
d2 = {'step': '2 (v3-history Learn campaign on native adapter v2)', 'declared_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
      'campaign_id': C, 'plan_hash': find(plan, {'plan_hash'}).get('plan_hash'), 'configuration_hash': camp['configuration_hash'],
      'discovery': hf, 'step1_result': {k: go[k] for k in ('decision', 'dev5_c3', 'c5_outside_dev5', 'b0_violated', 'b0_c5_total', 'lab_errors', 'b1_deviations')},
      'references': 'DECLARATION.json sha256 ' + (R / 'DECLARATION.sha256').read_text().split()[0] + '; its step2_bounds and PLAN.md section 4 stop rules apply unchanged'}
(R / 'DECLARATION-step2.json').write_text(json.dumps(d2, indent=1))
h = hashlib.sha256((R / 'DECLARATION-step2.json').read_bytes()).hexdigest(); (R / 'DECLARATION-step2.sha256').write_text(h + '  DECLARATION-step2.json\n')
print(json.dumps(d2, indent=1)); print('discovery keys', list(disc.keys())); print('sha256', h)
