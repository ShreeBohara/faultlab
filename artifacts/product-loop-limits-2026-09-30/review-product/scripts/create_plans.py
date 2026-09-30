"""Create one Learn discovery-v4 plan per scenario through the API (the first one was created in the dashboard)."""
import json, httpx
B = 'http://127.0.0.1:18531/api'; S = '/Users/shree/FaultLab_Scratch/review-product/ui'
with httpx.Client(timeout=60) as h:
    options = h.get(B + '/run-options').json()
    regs = [r for r in h.get(B + '/agent-registrations').json() if r['adapter_entrypoint_id'] == 'smolagents-toolcalling-v2']
    assert len(regs) == 1, regs
    reg = regs[0]['registration_id']
    campaigns = h.get(B + '/campaigns').json()['campaigns']
    existing = [c['campaign_id'] for c in campaigns if c.get('mode') == 'learn']
    assert len(existing) == 1, existing
    out = {existing[0]: 'reach'}
    for name in ('policyread', 'norule', 'compact', 'unfit'):
        body = {'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
                'task_definition_id': options['task']['task_definition_id'], 'agent_registration_id': reg, 'mode': 'learn',
                'config_profile_id': 'live-v1', 'task_text': options['task']['task_text_default'], 'order_id': f'order-{name}',
                'discovery_protocol': 'faultlab-discovery/v4-history-replay'}
        r = h.post(B + '/planned-campaigns', json=body); assert r.status_code == 201, r.text
        out[r.json()['campaign_id']] = name
    for cid in out:
        plan = h.get(B + f'/campaigns/{cid}/plan').json()['plan']
        assert plan['mechanic_context']['protocol'] == 'faultlab-mechanic-context/v2-bounded' and plan['challenge_selection']['protocol'] == 'faultlab-challenge-selection/v2-candidate-reach', cid
        assert plan['discovery']['protocol'] == 'faultlab-discovery/v4-history-replay' and plan['agent'] == 'smolagents-v2', (plan['discovery']['protocol'], plan['agent'])
    json.dump(out, open(S + '/scenarios.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))
