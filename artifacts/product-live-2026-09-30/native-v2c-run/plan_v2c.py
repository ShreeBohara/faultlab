"""Step 2 planner (PLAN.md section 4): only on a GO in go-decision.json. Creates the v3-history Learn campaign in the
same store, freezes the history, writes DECLARATION.json with its sha256. Does not Start."""
import json, urllib.request, pathlib, hashlib, datetime, sys
B = 'http://127.0.0.1:8000'; R = pathlib.Path('artifacts/product-live-2026-09-30/native-v2c-run'); S = pathlib.Path('artifacts/product-live-2026-09-30/native-v2b-run')
go = json.loads((R / 'gate_v2c.out.json').read_text())
if go['gate'] != 'PASS': sys.exit('gate FAIL: not run')
def get(p):
    with urllib.request.urlopen(B + p, timeout=15) as r: return json.loads(r.read())
def post(p, body, sid):
    req = urllib.request.Request(B + p, data=json.dumps(body).encode(), method='POST', headers={'Content-Type': 'application/json', 'X-FaultLab-Store-Identity': sid})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())
sid = (S / 'store-identity.txt').read_text().strip(); reg = json.loads((S / 'registration.json').read_text())
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
d2 = {'step': 'v2c: v3-history Learn campaign on native adapter v2.1 (separate declared experiment after v2b NO_GO)', 'declared_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
      'campaign_id': C, 'plan_hash': find(plan, {'plan_hash'}).get('plan_hash'), 'configuration_hash': camp['configuration_hash'],
      'discovery': hf, 'corrected_gate': go, 'v2b_probe': json.loads((S / 'go-decision.json').read_text())['decision'],
      'plan_sha256': hashlib.sha256((R / 'PLAN.md').read_bytes()).hexdigest(), 'gate_script_sha256': hashlib.sha256((R / 'gate_v2c.py').read_bytes()).hexdigest(), 'misreading_check_sha256': hashlib.sha256((R / 'check_evidence_gap_misreading.py').read_bytes()).hexdigest(), 'bounds': 'PLAN.md: ledger ceiling 4936 requests / about 106.87 dollars; discovery before any counterexample 144 requests / 3.47 dollars; 10 hours; 3 operator evidence retries', 'ledger_before_dollars': 895.98}
(R / 'DECLARATION.json').write_text(json.dumps(d2, indent=1))
h = hashlib.sha256((R / 'DECLARATION.json').read_bytes()).hexdigest(); (R / 'DECLARATION.sha256').write_text(h + '  DECLARATION.json\n')
print(json.dumps(d2, indent=1)); print('discovery keys', list(disc.keys())); print('sha256', h)
