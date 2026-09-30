"""Product review, checks 2-3 continued: run a v3-history Learn campaign on the updated native adapter v2 (v2.1 labels,
rule v2 frozen) end to end, with discovery forced onto an F4 broker-retried send (dev-6's recipe), and read exactly what
the diagnosis Mechanic was handed about those episodes. Offline and $0: the product's study harness (in-process
simulator over ASGI, local Weave double); every model transport is scripted. The scripted agent is made to over-claim
the confirmation (report SUCCEEDED after two transient send failures) so a source exists to diagnose; this is a
declared test fixture, not model behaviour.
"""
import asyncio
import json
import re
from pathlib import Path

import pytest

from app.contracts.models import canonical_json
from app.lab.diagnosis import V2_MEMORY
from app.lab.discovery_protocol import DISCOVERY_V3
from app.lab.run_plans import TASK, TASK_TEXT
from app.providers.runtime import RuntimeGeneration

from test_native_baseline_study_planned import PricedNativeInputs, study_runtime
from test_planned_agent_execution import NativeReferenceInputs

OUT_DIR = Path(__file__).resolve().parents[1]
AGENT_LABEL = re.compile(r'obs-\d')
LABEL = re.compile(r'obs-(\d+)')
F4 = {'seed': 106, 'primitives': [{'kind': 'F4', 'occurrence': 1, 'parameters': {'failure_count': 2},
                                    'target_service': 'notifications', 'target_tool': 'send_confirmation'}]}


@pytest.fixture
def anyio_backend(): return 'asyncio'


class F4Lab(PricedNativeInputs):
    def __init__(self):
        super().__init__('accepted'); self.mechanic_requests = []; self.explorer_requests = []; self.actor_requests = []
    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'mechanic':
            self.mechanic_requests.append(messages)
        if role == 'explorer':
            self.explorer_requests.append(messages)
            context = json.loads(messages[-1]['content'])
            if context.get('purpose') != 'challenge' and 'development_history' in context:
                self.calls[role] += 1
                return RuntimeGeneration(canonical_json({'fault_spec': F4, 'hypothesis': 'Review fixture: repeated transient send failures.'}),
                                         'deepseek-ai/DeepSeek-V4-Pro-0813', 10, 10, 0.0)
        if role != 'actor':
            # Lab roles: the fixture's own scripted answers under the frozen reasoning model (not the actor pricing wrapper).
            return await NativeReferenceInputs.complete(self, messages, role=role, **kwargs)
        self.actor_requests.append(json.dumps(messages, ensure_ascii=False))
        output = await super().complete(messages, role=role, **kwargs)
        if role == 'actor':
            action = json.loads(output.content)
            answer = (action.get('arguments') or {}).get('answer') if action.get('name') == 'final_answer' else None
            if answer and answer.get('upgrade_outcome') == 'SUCCEEDED' and answer.get('notification_outcome') == 'UNKNOWN':
                answer.update(notification_outcome='SUCCEEDED', overall='COMPLETED', next_action={'kind': 'NONE'})
                return RuntimeGeneration(canonical_json(action), output.model_id, output.input_tokens, output.output_tokens, output.cost_usd)
        return output


def episode_view(summary, episode_id):
    row, = [row for row in summary['episodes'] if row['episode_id'] == episode_id]
    return row['observations'], summary['reports'][row['report_row']]


@pytest.mark.anyio
async def test_v3_learn_on_v21_with_an_f4_source_and_the_mechanic_view(tmp_path):
    provider = F4Lab()
    c, world, api, remote = study_runtime(tmp_path, provider)
    out = {}
    try:
        options = (await api.get('/api/run-options')).json()
        registration = (await api.post('/api/agent-registrations', json={'expected_store_identity': options['data_store']['identity'],
                                                                         'agent': 'smolagents-v2'})).json()
        options = (await api.get('/api/run-options')).json()
        common = {'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
                  'task_definition_id': TASK, 'agent_registration_id': registration['registration_id'],
                  'config_profile_id': 'live-v1', 'task_text': TASK_TEXT}
        baseline = (await api.post('/api/planned-campaigns', json={**common, 'mode': 'baseline', 'order_id': 'order-selected',
                                                                   'development_case_id': 'dev-1'})).json()
        queued = (await api.post(f"/api/campaigns/{baseline['campaign_id']}/baseline-study", json={'execute_live': True})).json()
        await c.tasks[queued['study_id']]
        options = (await api.get('/api/run-options')).json()
        common.update(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'])
        response = await api.post('/api/planned-campaigns', json={**common, 'mode': 'learn', 'order_id': 'order-learn',
                                                                  'discovery_protocol': DISCOVERY_V3})
        assert response.status_code == 201, response.text
        learn = response.json(); id = learn['campaign_id']
        plan = (await api.get(f'/api/campaigns/{id}/plan')).json()['plan']
        assert plan['transport_retry']['protocol'] == 'faultlab-transport-retry/v2-lab-backoff'
        assert plan['discovery']['history']['summary']['verified_episodes'] == 18
        started = await api.post(f'/api/campaigns/{id}/start', json={})
        assert started.status_code == 202, started.text
        await asyncio.wait_for(c.tasks[id], timeout=600)
        final = (await api.get(f'/api/campaigns/{id}')).json()
        out['final'] = {'state': final['state'], 'terminal_reason': final['terminal_reason']}
        out['execution_errors'] = c.store.list_records('execution_errors')
        counters = [x for x in c.store.list_records('counterexamples') if x['campaign_id'] == id]
        out['counterexamples'] = [{k: x[k] for k in ('counterexample_id', 'target_invariant', 'target_violation_count', 'source_episode_id')} for x in counters]
        out['diagnostics'] = [{k: d.get(k) for k in ('kind', 'proposed_kind', 'explanation')} for d in c.store.list_records('diagnostics')]

        # Every Learn-campaign agent request: contiguous labels from obs-1, no raw evidence ID.
        learn_episodes = [e for e in c.store.list_records('episodes') if e['campaign_id'] == id]
        submitted = {}
        for e in learn_episodes:
            rows = [x['payload'] for x in c.store.events(e['episode_id'])['events'] if x['type'] == 'report_submitted']
            if rows: submitted[e['episode_id']] = rows[-1]
        for text in provider.actor_requests:
            numbers = sorted({int(n) for n in LABEL.findall(text)})
            assert numbers == list(range(1, len(numbers) + 1))
            assert not re.search(r'evidence-[0-9a-f]{32}', text)
        out['learn_reports'] = {'episodes': len(learn_episodes), 'with_report': len(submitted),
                                'not_decoded_tokens': sorted({t for p in submitted.values() for t in p['cited_tokens_not_decoded']}),
                                'label_sets': sorted({tuple(p['labels_shown_to_agent']) for p in submitted.values()})}
        assert all(p['cited_tokens_not_decoded'] == [] for p in submitted.values())

        # What the diagnosis Mechanic was handed.
        diagnosis = [m for m in provider.mechanic_requests if 'intervention_ids' in json.loads(m[-1]['content'])]
        assert diagnosis, 'no diagnosis request was made'
        request = diagnosis[0][-1]['content']
        context = json.loads(request)
        views = []
        for row in context['observations']['episodes']:
            observations, report = episode_view(context['observations'], row['episode_id'])
            episode = c.store.get_record('episodes', row['episode_id'])
            payload = submitted.get(row['episode_id'], {})
            journal = [x['payload']['observation']['evidence_id'] for x in c.store.events(row['episode_id'])['events'] if x['type'] == 'observation_delivered']
            views.append({'episode_id': row['episode_id'], 'recorded_rows': len(observations),
                          'report_aliases': (report or {}).get('evidence_ids'),
                          'agent_labels_shown': payload.get('labels_shown_to_agent'),
                          'agent_cited': payload.get('cited_evidence_tokens'),
                          'hidden_rows': [journal.index(i) + 1 for i in journal if i not in payload.get('evidence_labels', {})]})
        out['diagnosis_request'] = {'agent_label_tokens_in_request': AGENT_LABEL.findall(request),
                                    'memory_is_V2_MEMORY': context['runtime_contract']['actor_contract']['memory'] == V2_MEMORY,
                                    'episode_views': views,
                                    'legend': context['observations']['interpretation']}
        assert not AGENT_LABEL.search(request)
        assert context['runtime_contract']['actor_contract']['memory'] == V2_MEMORY
        # Every alias names a real row of its own episode (no undecoded label, no out-of-range alias).
        for view in views:
            assert all(alias.startswith('o') and 1 <= int(alias[1:]) <= view['recorded_rows'] for alias in view['report_aliases'] or [])
    finally:
        (OUT_DIR / 'r3-v3-learn-mechanic-view.json').write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + '\n')
        await world.aclose(); await api.aclose(); await c.close()
