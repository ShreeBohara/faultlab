"""Fixer manual check through the product API over HTTP ($0, offline): the product review's M4 -> M4b sequence again.

Server: the product reviewer's serve_offline.py (the REAL backend, coordinator, run plans, learning loop, Reproducer,
reduction, Diagnostician, native adapter v2, in-process simulator; scripted model transport and a local Weave double;
socket guard), started separately on a loopback port with a scratch store OUTSIDE the Desktop. The scripted answers are
fixture behaviour, not model evidence. The server's declared stop point prevents any protected promotion comparison.

Sequence: register native adapter v2 -> scripted baseline study (36 slots) -> v4 plan M4 -> Start -> wait -> read the
search attempts, experiments and recording -> a second v4 plan M4b and a v3 plan in the same store -> compare.
Expected after the fixes: M4's replays (dev-3, dev-5) never enter M4b's history (the product review saw 4/4 there before
the fix); M4 ends after the replays when their sources use up the candidate requests (F2) with 0 Explorer requests; the
v4 recording's history claim rule names v4 (F4).

Run: python manual_check_api.py <port> <out.json>   (the server must already be running on 127.0.0.1:<port>)
"""
import json
import sys
import time

import httpx

PORT, OUT = int(sys.argv[1]), sys.argv[2]
B = f'http://127.0.0.1:{PORT}/api'
V4, V3 = 'faultlab-discovery/v4-history-replay', 'faultlab-discovery/v3-history'


def wait_ready(h):
    for _ in range(120):
        try:
            if h.get(B + '/run-options').status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit('server not ready')


def plan(h, options, registration, protocol, order):
    body = {'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
            'task_definition_id': options['task']['task_definition_id'], 'agent_registration_id': registration, 'mode': 'learn',
            'config_profile_id': 'live-v1', 'task_text': options['task']['task_text_default'], 'order_id': order,
            'discovery_protocol': protocol}
    r = h.post(B + '/planned-campaigns', json=body)
    assert r.status_code == 201, r.text
    campaign = r.json()['campaign_id']
    return campaign, h.get(B + f'/campaigns/{campaign}/plan').json()['plan']


def rows(history):
    return [{'row': i, 'case': r['development_case_id'], 'verified': r['verified_episodes'], 'outcomes': r['outcomes'],
             'sources': r['sources']} for i, r in enumerate(history['summary']['recipes'], 1)]


def replay_rows(discovery):
    return [(r['replay'], r['history_row'], r['development_case_id'], r['violation_share'], r['sources']) for r in discovery['replay']['rows']]


def main():
    out = {}
    with httpx.Client(timeout=120) as h:
        wait_ready(h)
        options = h.get(B + '/run-options').json()
        r = h.post(B + '/agent-registrations', json={'expected_store_identity': options['data_store']['identity'], 'agent': 'smolagents-v2'})
        assert r.status_code == 201, r.text
        registration = r.json()['registration_id']
        options = h.get(B + '/run-options').json()
        out['registration_id'] = registration
        # Scripted baseline study (fixed six development cases x three trials, B0 and B1).
        body = {'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
                'task_definition_id': options['task']['task_definition_id'], 'agent_registration_id': registration, 'mode': 'baseline',
                'config_profile_id': 'live-v1', 'task_text': options['task']['task_text_default'], 'order_id': 'order-baseline',
                'development_case_id': 'dev-1'}
        r = h.post(B + '/planned-campaigns', json=body); assert r.status_code == 201, r.text
        baseline = r.json()['campaign_id']
        r = h.post(B + f'/campaigns/{baseline}/baseline-study', json={'execute_live': True}); assert r.status_code == 202, r.text
        study_id = r.json()['study_id']
        while (study := h.get(B + '/baseline-studies/' + study_id).json())['status'] in ('QUEUED', 'RUNNING'):
            time.sleep(2)
        cases = {x['episode_id']: x['case_id'] for x in study['slots']}
        b0 = {}
        for t in study['trials']:
            if t['arm'] == 'B0':
                b0.setdefault(cases[t['episode_id']], []).append(t['outcome'])
        out['baseline'] = {'study_id': study_id, 'status': study['status'], 'b0_by_case': b0}
        # M4: the first v4 plan, then Start.
        m4, m4_plan = plan(h, options, registration, V4, 'order-m4')
        out['m4'] = {'campaign_id': m4, 'history_rows': rows(m4_plan['discovery']['history']),
                     'composition': m4_plan['discovery']['history']['summary']['composition'],
                     'summary_hash': m4_plan['discovery']['history']['summary_hash'], 'replay_rows': replay_rows(m4_plan['discovery']),
                     'replay_statement': m4_plan['discovery']['replay']['statement'],
                     'history_check': h.get(B + f'/campaigns/{m4}/plan/history-check').json()['status']}
        r = h.post(B + f'/campaigns/{m4}/start', json={}); assert r.status_code == 202, r.text
        for _ in range(900):
            state = h.get(B + f'/campaigns/{m4}').json()
            if state['state'] in ('NO_CHANGE', 'COMPLETED', 'ERROR', 'STOPPED', 'WAITING_EVIDENCE', 'REJECTED_FINAL'):
                break
            time.sleep(1)
        attempts = h.get(B + f'/campaigns/{m4}/search-attempts').json()
        experiments = h.get(B + f'/campaigns/{m4}/experiments').json()
        recording = h.get(B + f'/campaigns/{m4}/recording').json()
        out['m4_run'] = {'state': state['state'], 'terminal_reason': state.get('terminal_reason'),
                         'attempts': [{'selection_index': a['selection_index'], 'provenance': a['provenance'],
                                       'model_calls': a['usage']['model_calls'], 'status': a['search_decision']['status'],
                                       'history_replay': (a.get('history_replay') or {}).get('history_row')} for a in attempts],
                         'explorer_rows': sum(1 for a in attempts if 'history_replay' not in a),
                         'sources_found_by': [(x['counterexample']['source_episode_id'], (x.get('history_replay') or {}).get('history_row'))
                                              for x in experiments['counterexamples']],
                         'candidate_proposals': len(recording.get('campaign_proposals') or []),
                         'history_claim_rule': recording['discovery_history_matches']['claim_rule'],
                         'replay_claim_rule': recording['discovery_history_replays']['claim_rule'],
                         'replay_slots': [(s['replay'], s['history_row'], s['development_case_id']) for s in recording['discovery_history_replays']['replay_slots']]}
        out['m4_search_attempts_raw'] = attempts
        out['m4_experiments_raw'] = experiments
        # M4b (second v4 plan) and a v3 plan, in the same store, after M4.
        m4b, m4b_plan = plan(h, options, registration, V4, 'order-m4b')
        v3, v3_plan = plan(h, options, registration, V3, 'order-v3')
        hist, hist3 = m4b_plan['discovery']['history'], v3_plan['discovery']['history']
        out['m4b'] = {'campaign_id': m4b, 'history_rows': rows(hist), 'composition': hist['summary']['composition'],
                      'verified_episodes': hist['summary']['verified_episodes'], 'summary_hash': hist['summary_hash'],
                      'replay_rows': replay_rows(m4b_plan['discovery'])}
        out['v3_same_history_as_m4b'] = {k: v for k, v in hist3.items() if k != 'record_cutoff'} == {k: v for k, v in hist.items() if k != 'record_cutoff'}
        out['m4b_history_equals_m4_history_except_cutoff'] = (
            {k: v for k, v in hist.items() if k not in ('record_cutoff',)} == {k: v for k, v in m4_plan['discovery']['history'].items() if k not in ('record_cutoff',)})
    json.dump(out, open(OUT, 'w'), indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in out.items() if not k.endswith('_raw')}, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
