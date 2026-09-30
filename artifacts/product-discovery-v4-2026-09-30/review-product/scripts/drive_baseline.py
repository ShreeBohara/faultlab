import json, time, httpx
B = 'http://127.0.0.1:18431/api'
with httpx.Client(timeout=60) as h:
    options = h.get(B + '/run-options').json()
    regs = h.get(B + '/agent-registrations').json()
    v2 = [r for r in regs if r['adapter_entrypoint_id'] == 'smolagents-toolcalling-v2']
    assert len(v2) == 1, regs
    reg = v2[0]['registration_id']
    body = {'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
            'task_definition_id': options['task']['task_definition_id'], 'agent_registration_id': reg, 'mode': 'baseline',
            'config_profile_id': 'live-v1', 'task_text': options['task']['task_text_default'], 'order_id': 'order-baseline',
            'development_case_id': 'dev-1'}
    r = h.post(B + '/planned-campaigns', json=body); assert r.status_code == 201, r.text
    baseline = r.json()['campaign_id']
    r = h.post(B + f'/campaigns/{baseline}/baseline-study', json={'execute_live': True}); assert r.status_code == 202, r.text
    study_id = r.json()['study_id']
    t0 = time.time()
    while True:
        s = h.get(B + '/baseline-studies/' + study_id).json()
        if s['status'] not in ('QUEUED', 'RUNNING'): break
        time.sleep(3)
    slot_case = {x['episode_id']: x['case_id'] for x in s['slots']}
    b0 = {}
    for t in s['trials']:
        if t['arm'] == 'B0': b0.setdefault(slot_case[t['episode_id']], []).append((t['outcome'], sorted(t.get('failed_checks') or [])))
    out = {'registration_id': reg, 'baseline_campaign': baseline, 'study_id': study_id, 'status': s['status'], 'reason': s.get('reason'),
           'seconds': round(time.time() - t0), 'b0_by_case': b0, 'evidence_sources': sorted(set((s.get('evidence') or {}).values()))}
    json.dump(out, open('baseline.json', 'w'), indent=2); print(json.dumps(out, indent=2))
