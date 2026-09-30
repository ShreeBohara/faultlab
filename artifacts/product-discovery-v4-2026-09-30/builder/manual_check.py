"""Builder's manual offline check of discovery v4 (history replay) through the product API, in scratch stores ($0).

No provider, W&B, model or network call: the tests' scripted native transport (NativeReferenceInputs, which also
answers the Explorer role with one fixed handwritten recipe), the in-process simulator and the local Weave double
(tests/lab/test_native_baseline_study_planned.py), plus a socket guard that refuses every non-local connection and name
lookup. Scratch stores live outside the cloud-synced Desktop and are deleted afterwards. Nothing here is model evidence:
the scripted agent's outcomes are fixture behaviour.

Run from faultlab/backend:
    ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/builder/manual_check.py <scratch_dir> <out.json>

Run A (store A): the product baseline study (6 cases x 3 trials x 2 arms) -> a v4 plan through POST /api/planned-campaigns,
its frozen replay list, a v3 and a v1 plan for comparison, the on-demand history check -> Start through the API.
Reproduction is replaced by the tests' stub (it records the source counterexample exactly as Reproducer.source does and
reports "not reproduced") so the loop continues past the replays to the Explorer's slots without any Mechanic request;
the report says so. Then the dashboard's search-attempts, experiments and recording responses.
Run B (store B): the same history, a v4 plan, Start; the REAL reproduction runs on the first replay source, and the run is
stopped at reduction by a declared manual stop point (Reproducer.reduce raises StopRequested), so no Mechanic, challenge
or protected promotion case is reached.
Run C (store A, after run A): a counted record at or before a new v4 plan's cutoff is changed; the check says CHANGED
and Start is refused with the plain message, with no new selection record.
"""
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
import conftest  # noqa: F401,E402  (audit hook refusing the real .env, dotenv disabled)
import socket  # noqa: E402

REFUSED = []
_connect = socket.socket.connect
def _guarded_connect(sock, address):
    if sock.family == socket.AF_UNIX: return _connect(sock, address)
    REFUSED.append(repr(address)); raise RuntimeError('manual check refuses network connections')
def _refuse(*args, **kwargs):
    REFUSED.append(repr(args[:1])); raise RuntimeError('manual check refuses network connections')
socket.socket.connect = _guarded_connect
socket.create_connection = _refuse
socket.getaddrinfo = _refuse

from app.contracts.models import Counterexample, canonical_json, content_hash, new_id  # noqa: E402
from app.contracts.tokens import input_token_bound  # noqa: E402
from app.lab.budgets import StopRequested  # noqa: E402
from app.lab.configuration import runtime_fingerprints  # noqa: E402
from app.lab.run_plans import TASK, TASK_TEXT, read_run_plan  # noqa: E402
from test_native_baseline_study_planned import PricedNativeInputs, planned_campaign, study_runtime  # noqa: E402
from test_planned_agent_execution import NativeReferenceInputs  # noqa: E402
from test_native_baseline_study_planned import IN_TOKENS, OUT_TOKENS  # noqa: E402
from app.providers.runtime import RuntimeGeneration  # noqa: E402

V4 = 'faultlab-discovery/v4-history-replay'
EXPLORER_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'


class Recorder(PricedNativeInputs):
    """The scripted native transport, also keeping every Explorer message it was sent.

    PricedNativeInputs relabels every reply with the Actor's model (it was written for Actor calls only), which the
    Explorer's frozen-model check correctly refuses; Explorer requests therefore go to the unpriced scripted transport,
    whose reply names the scripted role model. A first run without this fix ended ERROR (PROVIDER_ERROR) at the first
    Explorer request, after both replay slots had run (manual_check_first_run.json).
    """
    def __init__(self, mode):
        super().__init__(mode); self.explorer_messages = []
    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'explorer':
            self.explorer_messages.append([dict(m) for m in messages])
            output = await NativeReferenceInputs.complete(self, messages, role=role, **kwargs)
            # Declared fixture token counts (a real provider reports them; the dashboard's Usage schema requires integers).
            return RuntimeGeneration(output.content, output.model_id, IN_TOKENS, OUT_TOKENS, 0.0)
        return await super().complete(messages, role=role, **kwargs)


async def baseline_history(c, api):
    baseline = planned_campaign(c)
    queued = (await api.post(f'/api/campaigns/{baseline.campaign_id}/baseline-study', json={'execute_live': True})).json()
    await c.tasks[queued['study_id']]
    study = (await api.get('/api/baseline-studies/' + queued['study_id'])).json()
    native_id = read_run_plan(c.store, baseline)['plan']['agent_registration_id']
    return study, native_id


async def create(api, registration_id, protocol, order):
    options = (await api.get('/api/run-options')).json()
    response = await api.post('/api/planned-campaigns', json={
        'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
        'task_definition_id': TASK, 'agent_registration_id': registration_id, 'mode': 'learn', 'config_profile_id': 'live-v1',
        'task_text': TASK_TEXT, 'order_id': order, 'discovery_protocol': protocol})
    assert response.status_code == 201, response.text
    campaign = response.json()
    plan = (await api.get(f"/api/campaigns/{campaign['campaign_id']}/plan")).json()['plan']
    return campaign, plan, options


def own(c, campaign_id):
    rows = [row for row in c.store.list_records('selections') if (row.get('context') or {}).get('campaign_id') == campaign_id]
    return sorted(rows, key=lambda row: row['context']['selection_index'])


def stub_source(c):
    """tests' stub: record the source as Reproducer.source does, report it not reproduced (no reproduction trials)."""
    async def source(self, current, trial, recipe, incumbent, **kwargs):
        counter = Counterexample(counterexample_id=new_id('counterexample'), campaign_id=current.campaign_id,
                                 agent_registration_id=read_run_plan(c.store, current.campaign_id)['plan']['agent_registration_id'],
                                 source_episode_id=trial.episode_id, target_invariant=sorted(trial.failed_checks, key=lambda x: int(x[1:]))[0],
                                 scenario_hash=content_hash(recipe), configuration_hash=current.configuration_hash,
                                 report_ref=trial.episode_id, verdict_ref=trial.episode_id)
        c.store.put_record('counterexamples', counter.counterexample_id, counter)
        c.store.put_record('counterexample_recipes', counter.counterexample_id,
                           {'source_recipe': recipe.model_dump(mode='json'), 'fixture_id': 'standard-v1'}, immutable=True)
        from types import SimpleNamespace
        return SimpleNamespace(reproduced=False), []
    return source


async def run_a(scratch):
    from app.lab import learning
    provider = Recorder('accepted')
    c, world, api, remote = study_runtime(scratch / 'A', provider)
    report = {}
    try:
        study, native_id = await baseline_history(c, api)
        slot_case = {slot['episode_id']: slot['case_id'] for slot in study['slots']}
        report['baseline_study'] = {'status': study['status'], 'b0_by_case': {case: sorted(t['outcome'] for t in study['trials'] if t['arm'] == 'B0' and slot_case[t['episode_id']] == case)
                                                                             for case in sorted(set(slot_case.values()))}}
        v4_campaign, v4_plan, _ = await create(api, native_id, V4, 'order-v4-native')
        _, v3_plan, _ = await create(api, native_id, 'faultlab-discovery/v3-history', 'order-v3-native')
        _, v1_plan, options = await create(api, native_id, 'faultlab-discovery/v1', 'order-v1-native')
        chooser = next(row for row in options['learn']['discovery_protocols'] if row['protocol_id'] == V4)
        history, replay = v4_plan['discovery']['history'], v4_plan['discovery']['replay']
        report['plan'] = {
            'chooser': {'label': chooser['label'], 'description': chooser['description'], 'supported_agents': chooser['supported_agents']},
            'history_status': history['status'], 'verified_episodes': history['summary']['verified_episodes'],
            'history_rows': [(i, r['development_case_id'], r['verified_episodes'], r['outcomes'], r['every_fault_fired'], r['failed_checks'])
                             for i, r in enumerate(history['summary']['recipes'], 1)],
            'summary_hash': history['summary_hash'], 'record_cutoff': history['record_cutoff'],
            'replay': replay,
            'history_equals_v3_history_except_cutoff': {k: v for k, v in history.items() if k != 'record_cutoff'}
                == {k: v for k, v in v3_plan['discovery']['history'].items() if k != 'record_cutoff'},
            'budget_equals_v3': {k: v for k, v in v4_plan['discovery'].items() if k not in ('protocol', 'history', 'replay', 'dispatch_rule')}
                == {k: v for k, v in v3_plan['discovery'].items() if k not in ('protocol', 'history', 'dispatch_rule')},
            'dispatch_rule': v4_plan['discovery']['dispatch_rule'],
            'v3_plan_has_no_replay_field': 'replay' not in v3_plan['discovery'],
            'v1_plan_has_no_history_or_replay_field': not {'history', 'replay'} & set(v1_plan['discovery'])}
        report['history_check_before_start'] = (await api.get(f"/api/campaigns/{v4_campaign['campaign_id']}/plan/history-check")).json()
        # Start through the API. Declared manual stop point: reproduction is the tests' stub (see the docstring).
        learning.Reproducer.source = stub_source(c)
        start = await api.post(f"/api/campaigns/{v4_campaign['campaign_id']}/start", json={})
        await c.tasks[v4_campaign['campaign_id']]
        done = c.get(v4_campaign['campaign_id'])
        rows = own(c, v4_campaign['campaign_id'])
        episodes = {e['episode_id']: e for e in c.store.list_campaign_episodes(v4_campaign['campaign_id'])}
        first_explorer = json.loads(provider.explorer_messages[0][1]['content']) if provider.explorer_messages else None
        report['run'] = {
            'start_status': start.status_code, 'state': done.state, 'terminal_reason': done.terminal_reason,
            'explorer_requests': len(provider.explorer_messages), 'ledger_used_calls_explorer': None,
            'slots': [{'index': row['context']['selection_index'], 'provenance': row['provenance'], 'status': row['search_decision']['status'],
                       'model_calls': row['usage']['model_calls'], 'history_replay': row.get('history_replay', {}).get('history_row') if row.get('history_replay') else None,
                       'recipe': row['selected_output']['fault_spec']['primitives'] if row.get('selected_output') else None,
                       'episode_outcome': (episodes.get((row.get('history_replay') or {}).get('episode_id')) or {}).get('verdict', {}).get('outcome') if row.get('history_replay') else None}
                      for row in rows],
            'first_explorer_request': None if first_explorer is None else {
                'selection_index': first_explorer['selection_index'], 'discovery_protocol': first_explorer['discovery_protocol'],
                'agent_history_equals_frozen_summary': first_explorer['agent_history'] == history['summary'],
                'prior_selections': [(p['selection_index'], p['status'], p.get('history_replay')) for p in first_explorer['search_ledger']['prior_selections']],
                'tested_schedules': [(t['episode_id'], t['outcome']) for t in first_explorer['search_ledger']['tested_schedules']],
                'system_prompt_has_v4_section': 'Discovery protocol v4 (history replay)' in provider.explorer_messages[0][0]['content'],
                'request_token_bound': input_token_bound(provider.explorer_messages[0], EXPLORER_MODEL)},
            'counterexamples': [(x['counterexample_id'], x['source_episode_id'], x['target_invariant']) for x in c.store.list_records('counterexamples')
                                if x['campaign_id'] == v4_campaign['campaign_id']]}
        attempts = (await api.get(f"/api/campaigns/{v4_campaign['campaign_id']}/search-attempts")).json()
        experiments = (await api.get(f"/api/campaigns/{v4_campaign['campaign_id']}/experiments")).json()
        recording = (await api.get(f"/api/campaigns/{v4_campaign['campaign_id']}/recording")).json()
        report['labels'] = {
            'search_attempts': [(row['selection_index'], row['provenance'], (row.get('history_replay') or {}).get('label'),
                                 (row.get('history_replay') or {}).get('history_row'), row['usage']['model_calls']) for row in attempts],
            'experiments_sources': [(row['counterexample']['source_episode_id'], (row.get('history_replay') or {}).get('label'),
                                     (row.get('history_replay') or {}).get('history_row')) for row in experiments['counterexamples']],
            'recording_replays': {k: recording['discovery_history_replays'][k] for k in ('label', 'status', 'sources_found_by_replay', 'claim_rule')},
            'recording_replay_slots': [(s['replay'], s['history_row'], s['episode_id']) for s in recording['discovery_history_replays']['replay_slots']],
            'recording_selection_labels': [(s.get('provenance'), (s.get('history_replay') or {}).get('label')) for s in recording['selections']]}
        # ------------------------------------------------ run C: a changed history refuses Start (store A, new plan)
        c3, c3_plan, _ = await create(api, native_id, V4, 'order-v4-stale')
        included = next(row for _, row in c.store.records_upto('episodes', c3_plan['discovery']['history']['record_cutoff'])
                        if row.get('study_id') == study['study_id'] and row.get('arm') == 'B0')
        c.store.put_record('evidence', included['episode_id'], {**c.store.get_record('evidence', included['episode_id']), 'source': 'local_only'})
        before = len(c.store.list_records('selections'))
        stale = (await api.get(f"/api/campaigns/{c3['campaign_id']}/plan/history-check")).json()
        refused = await api.post(f"/api/campaigns/{c3['campaign_id']}/start", json={})
        report['stale_plan'] = {'check': stale['status'], 'start_status': refused.status_code, 'start_message': refused.json().get('error', {}).get('message'),
                                'state': c.get(c3['campaign_id']).state, 'new_selections': len(c.store.list_records('selections')) - before}
        report['provider_calls'] = dict(provider.calls)
    finally:
        await api.aclose(); await world.aclose(); await c.close()
    return report


async def run_b(scratch):
    from app.lab import learning
    provider = Recorder('accepted')
    c, world, api, remote = study_runtime(scratch / 'B', provider)
    report = {}
    try:
        _, native_id = await baseline_history(c, api)
        campaign, plan, _ = await create(api, native_id, V4, 'order-v4-real-reproduction')
        async def reduce(self, *args, **kwargs):
            raise StopRequested('Manual check stop point: reduction is not part of this check')
        learning.Reproducer.reduce = reduce
        start = await api.post(f"/api/campaigns/{campaign['campaign_id']}/start", json={})
        await c.tasks[campaign['campaign_id']]
        done = c.get(campaign['campaign_id'])
        rows = own(c, campaign['campaign_id'])
        counters = [x for x in c.store.list_records('counterexamples') if x['campaign_id'] == campaign['campaign_id']]
        experiments = (await api.get(f"/api/campaigns/{campaign['campaign_id']}/experiments")).json()
        report = {'start_status': start.status_code, 'state': done.state, 'terminal_reason': done.terminal_reason,
                  'replay_rows': [(r['replay'], r['history_row'], r['development_case_id'], r['violation_share']) for r in plan['discovery']['replay']['rows']],
                  'selections': [(row['context']['selection_index'], row['provenance'], row['usage']['model_calls']) for row in rows],
                  'explorer_requests': len(provider.explorer_messages),
                  'counterexamples': [{'source_episode_id': x['source_episode_id'], 'target_invariant': x['target_invariant'], 'reproduced': x.get('reproduced'),
                                       'target_violation_count': x.get('target_violation_count'), 'valid_count': x.get('valid_count'),
                                       'reproduction_trials': len(x.get('reproduction_trial_ids') or [])} for x in counters],
                  'source_is_replay_episode': bool(counters) and counters[0]['source_episode_id'] == (rows[0].get('history_replay') or {}).get('episode_id'),
                  'experiments_label': [((row.get('history_replay') or {}).get('label'), (row.get('history_replay') or {}).get('history_row'))
                                        for row in experiments['counterexamples']],
                  'provider_calls': dict(provider.calls)}
    finally:
        await api.aclose(); await world.aclose(); await c.close()
    return report


async def main(scratch, out):
    from app.lab import learning
    source, reduce = learning.Reproducer.source, learning.Reproducer.reduce
    report = {'runtime': runtime_fingerprints()}
    report['run_a'] = await run_a(scratch)
    learning.Reproducer.source, learning.Reproducer.reduce = source, reduce
    report['run_b'] = await run_b(scratch)
    learning.Reproducer.source, learning.Reproducer.reduce = source, reduce
    report['network_connections_refused'] = REFUSED
    Path(out).write_text(json.dumps(report, indent=1, sort_keys=True, default=str))
    a, b = report['run_a'], report['run_b']
    print('baseline B0 by case:', a['baseline_study']['b0_by_case'])
    print('history rows:', a['plan']['history_rows'])
    print('replay list:', [(r['replay'], r['history_row'], r['development_case_id'], r['violation_share']) for r in a['plan']['replay']['rows']], a['plan']['replay']['status'])
    print({k: v for k, v in a['plan'].items() if isinstance(v, bool)})
    print('history check before start:', a['history_check_before_start']['status'])
    print('run A:', a['run']['state'], '| explorer requests', a['run']['explorer_requests'])
    for slot in a['run']['slots']: print('   ', slot)
    print('first explorer request:', a['run']['first_explorer_request'])
    print('labels:', json.dumps(a['labels'], default=str)[:1500])
    print('stale plan:', a['stale_plan'])
    print('run B:', {k: v for k, v in b.items() if k != 'counterexamples'})
    print('run B counterexamples:', b['counterexamples'])
    print('provider calls A', a['provider_calls'], 'B', b['provider_calls'], '| refused network', REFUSED)


if __name__ == '__main__':
    scratch = Path(sys.argv[1]).resolve(); scratch.mkdir(parents=True, exist_ok=False)
    asyncio.run(main(scratch, sys.argv[2]))
