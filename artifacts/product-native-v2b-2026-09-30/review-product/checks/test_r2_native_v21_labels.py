"""Product review, check 2: register the updated native adapter v2 (v2.1 labels), run the product's baseline study on it
through the API, then create a v3-history Learn plan from that study. Offline and $0: the product's own study harness
(test_native_baseline_study_planned.study_runtime: in-process simulator over ASGI, local Weave double, scripted native
transport). What the agent was shown is read from the exact requests handed to the model transport, independently of the
adapter's own report_submitted claims.
"""
import json
import re
from pathlib import Path

import pytest

from app.contracts.models import content_hash
from app.integrations.external_agent_v2 import PROTOCOL_VERSION
from app.integrations.registry import NATIVE_V2, native_prompt_hash, adapter_hash
from app.lab.agent_history import target_identity
from app.lab.discovery_protocol import DISCOVERY_V3
from app.lab.run_plans import TASK, TASK_TEXT

from test_native_baseline_study_planned import PricedNativeInputs, study_runtime

FAULTLAB = Path(__file__).resolve().parents[4]
FIRST_V2 = json.loads((FAULTLAB / 'artifacts/product-live-2026-09-30/native-v2-run/registration.json').read_text())
LABEL = re.compile(r'obs-(\d+)')
REAL_ID = re.compile(r'evidence-[0-9a-f]{32}')
OUT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend(): return 'asyncio'


class Recording(PricedNativeInputs):
    def __init__(self):
        super().__init__('accepted'); self.actor_requests = []
    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'actor':
            self.actor_requests.append(json.dumps(messages, ensure_ascii=False, sort_keys=True))
        return await super().complete(messages, role=role, **kwargs)


def episode_groups(requests):
    """Split the sequential actor requests into episodes: a new episode starts at a request that shows no observation."""
    groups = []
    for text in requests:
        if not LABEL.search(text) and not REAL_ID.search(text) and '"observation"' not in text:
            groups.append([])
        groups[-1].append(text)
    return groups


@pytest.mark.anyio
async def test_v21_registration_baseline_study_labels_and_v3_history(tmp_path):
    provider = Recording()
    c, world, api, remote = study_runtime(tmp_path, provider)
    summary = {}
    try:
        options = (await api.get('/api/run-options')).json()
        response = await api.post('/api/agent-registrations', json={'expected_store_identity': options['data_store']['identity'],
                                                                    'agent': 'smolagents-v2'})
        assert response.status_code == 201, response.text
        registration = response.json()
        # A new identity, distinct from the first v2 build that ran live on September 29.
        assert registration['adapter_entrypoint_id'] == NATIVE_V2
        assert registration['prompt_hash'] == native_prompt_hash(NATIVE_V2) != FIRST_V2['prompt_hash']
        assert registration['adapter_hash'] == adapter_hash(NATIVE_V2) != FIRST_V2['adapter_hash']
        assert registration['registration_id'] != FIRST_V2['registration_id']
        configuration = c.store.get_record('configurations', registration['configuration_hash'])
        new_identity = target_identity(registration, configuration)
        summary['registration'] = {k: registration[k] for k in ('registration_id', 'prompt_hash', 'adapter_hash', 'configuration_hash', 'limitations')}
        summary['first_v2_build'] = {k: FIRST_V2[k] for k in ('registration_id', 'prompt_hash', 'adapter_hash', 'configuration_hash')}
        summary['new_history_identity_hash'] = content_hash(new_identity)
        summary['new_identity_prompt_hash_differs_from_first_build'] = new_identity['prompt_hash'] != FIRST_V2['prompt_hash']

        options = (await api.get('/api/run-options')).json()
        response = await api.post('/api/planned-campaigns', json={
            'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
            'task_definition_id': TASK, 'agent_registration_id': registration['registration_id'], 'mode': 'baseline',
            'config_profile_id': 'live-v1', 'task_text': TASK_TEXT, 'order_id': 'order-selected', 'development_case_id': 'dev-1'})
        assert response.status_code == 201, response.text
        baseline = response.json()
        plan = (await api.get(f"/api/campaigns/{baseline['campaign_id']}/plan")).json()['plan']
        assert plan['agent'] == 'smolagents-v2' and plan['transport_retry']['protocol'] == 'faultlab-transport-retry/v1'

        queued = (await api.post(f"/api/campaigns/{baseline['campaign_id']}/baseline-study", json={'execute_live': True})).json()
        await c.tasks[queued['study_id']]
        study = (await api.get('/api/baseline-studies/' + queued['study_id'])).json()
        assert study['status'] == 'COMPLETED', study['reason']
        slot_case = {slot['episode_id']: slot['case_id'] for slot in study['slots']}
        b0 = [episode_id for episode_id in study['trial_ids'] if next(s for s in study['slots'] if s['episode_id'] == episode_id)['arm'] == 'B0']
        groups = episode_groups(provider.actor_requests)
        assert len(groups) == len(b0) == 18

        rows = []
        for episode_id, requests in zip(b0, groups):
            events = c.store.events(episode_id)['events']
            journal = [e['payload']['observation']['evidence_id'] for e in events if e['type'] == 'observation_delivered']
            submitted, = [e['payload'] for e in events if e['type'] == 'report_submitted']
            episode = c.store.get_record('episodes', episode_id)
            per_request = []
            for text in requests:
                numbers = sorted({int(n) for n in LABEL.findall(text)})
                assert numbers == list(range(1, len(numbers) + 1)), (slot_case[episode_id], numbers)   # contiguous, from 1
                assert not REAL_ID.search(text)                                                         # no raw IDs shown
                per_request.append(len(numbers))
            final_numbers = sorted({int(n) for n in LABEL.findall(requests[-1])})
            assert submitted['citation_protocol'] == PROTOCOL_VERSION
            assert submitted['labels_shown_to_agent'] == [f'obs-{n}' for n in final_numbers]
            assert submitted['cited_tokens_not_decoded'] == [] and 'cited_unshown_labels' not in submitted
            assert episode['report']['evidence_ids'] == submitted['decoded_evidence_ids']
            assert set(submitted['decoded_evidence_ids']) <= set(journal)
            hidden = [evidence_id for evidence_id in journal if evidence_id not in submitted['evidence_labels']]
            rows.append({'case': slot_case[episode_id], 'episode_id': episode_id, 'journal_rows': len(journal),
                         'labels_per_request': per_request, 'labels_shown': submitted['labels_shown_to_agent'],
                         'cited': submitted['cited_evidence_tokens'], 'hidden_journal_rows': len(hidden),
                         'hidden_row_positions': [journal.index(h) + 1 for h in hidden],
                         'outcome': episode['verdict']['outcome'] if episode.get('verdict') else None,
                         'failed_checks': [ch['check_id'] for ch in (episode.get('verdict') or {}).get('checks', []) if not ch['passed']]})
        summary['baseline_b0_episodes'] = rows
        dev6 = [row for row in rows if row['case'] == 'dev-6']
        # dev-6 (F4, two transient send failures inside one tool call): the journal holds a row the agent never saw,
        # and the agent's labels are still obs-1..obs-n with no gap.
        assert dev6 and all(row['hidden_journal_rows'] >= 1 for row in dev6)
        assert all(row['labels_shown'] == [f'obs-{n}' for n in range(1, len(row['labels_shown']) + 1)] for row in dev6)

        # A v3-history Learn plan from this study: its frozen history is this build's own 18 B0 trials.
        options = (await api.get('/api/run-options')).json()
        response = await api.post('/api/planned-campaigns', json={
            'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
            'task_definition_id': TASK, 'agent_registration_id': registration['registration_id'], 'mode': 'learn',
            'config_profile_id': 'live-v1', 'task_text': TASK_TEXT, 'order_id': 'order-learn', 'discovery_protocol': DISCOVERY_V3})
        assert response.status_code == 201, response.text
        learn = response.json()
        learn_plan = (await api.get(f"/api/campaigns/{learn['campaign_id']}/plan")).json()['plan']
        history = learn_plan['discovery']['history']
        assert history['agent_identity'] == new_identity and history['status'] == 'AVAILABLE'
        assert history['summary']['verified_episodes'] == 18
        assert history['episode_ids_hash'] == content_hash(sorted(b0))
        assert learn_plan['transport_retry']['protocol'] == 'faultlab-transport-retry/v2-lab-backoff'
        summary['learn_plan'] = {'campaign_id': learn['campaign_id'], 'history_status': history['status'],
                                 'verified_episodes': history['summary']['verified_episodes'],
                                 'recipes': [(r['development_case_id'], r['verified_episodes']) for r in history['summary']['recipes']],
                                 'transport_retry': learn_plan['transport_retry']['protocol'],
                                 'discovery_protocol': learn_plan['discovery']['protocol'],
                                 'explorer_transport_retries_max': learn_plan['discovery'].get('explorer_transport_retries_max')}
    finally:
        (OUT_DIR / 'r2-native-v21-summary.json').write_text(json.dumps(summary, indent=1, sort_keys=True, default=str) + '\n')
        await world.aclose(); await api.aclose(); await c.close()
