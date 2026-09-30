"""What FaultLab's own models read about a native adapter v2 episode's report (protocol v2.1, shown-order labels).

The first live v2 run (campaign b05ac280) diagnosed a broker-retried send (F4) as CONTRACT_EVIDENCE_GAP: the
Mechanic thought the agent had cited an observation that was never delivered. Every citation was a label the
agent had been shown, but v2 then numbered journal positions, so the agent's labels had a gap (obs-3 was the
hidden first send attempt). These tests build the real diagnosis request and the real discovery request for
such an episode and pin what a model reader sees: the report's decoded evidence IDs (as that episode's oN
row aliases, in the same ID space as the observation rows it is shown), never an agent label, and a contract
text that describes the numbering. Offline and $0: real smolagents, in-process simulator, real runner, real
Mechanic and Explorer; only model transports are scripted.
"""
import json
import re
from types import SimpleNamespace

import pytest

from app.agents.explorer import Explorer
from app.agents.mechanic import Mechanic
from app.adapters.business_tools import WorldClient
from app.contracts.models import FaultSpec, canonical_json
from app.integrations.external_agent_v2 import PROTOCOL_VERSION, adapter_protocol
from app.lab.budgets import CampaignLedger
from app.lab.diagnosis import V2_MEMORY, Diagnostician, runtime_contract, summarize_evidence
from app.lab.evidence import EvidenceContext
from app.providers.runtime import RuntimeGeneration

from original_loop_fixture import MODEL, OfflineEvidence
from test_native_adapter_v2_product import events, planned_v2
from test_planned_agent_execution import planned_campaign, runtime

# dev-6's recipe: the first confirmation attempt and the broker's one internal retry both fail transiently, so the
# journal holds two send attempts but the agent's tool result shows only the last one.
F4_BROKER_RETRIED_SEND = FaultSpec.model_validate({'seed': 106, 'primitives': [{
    'kind': 'F4', 'occurrence': 1, 'parameters': {'failure_count': 2},
    'target_service': 'notifications', 'target_tool': 'send_confirmation'}]})
AGENT_LABEL = re.compile(r'obs-\d')


@pytest.fixture
def anyio_backend(): return 'asyncio'


class Capturing:
    """A scripted lab-model transport that records each request exactly as it was handed over."""
    def __init__(self, answer):
        self.answer, self.requests = answer, []
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        self.requests.append(messages)
        return RuntimeGeneration(canonical_json(self.answer(json.loads(messages[-1]['content']))), MODEL, 10, 10)


async def v2_f4_episode(c, campaign):
    trial = await c.runner.run(campaign, F4_BROKER_RETRIED_SEND, c.policies.baseline(), purpose='discovery')
    assert trial.lifecycle == 'COMPLETED', trial.reason
    episode = c.store.get_record('episodes', trial.episode_id)
    gateway = OfflineEvidence(c.store, 'offline-fixture/native-v2-views')
    bundle = await gateway.get(trial.episode_id, EvidenceContext(episode['campaign_id'], episode['study_id'],
                                                                 episode['evidence_context_id'], episode['selector_id']))
    return trial, episode, bundle


def episode_view(summary, episode_id):
    """One episode's observation rows and its report as a model reader is shown them."""
    row, = [row for row in summary['episodes'] if row['episode_id'] == episode_id]
    return row['observations'], summary['reports'][row['report_row']]


@pytest.mark.anyio
async def test_diagnosis_context_for_a_v2_f4_episode_has_no_label_gap_or_undecoded_label(tmp_path):
    c = await runtime(tmp_path)
    try:
        campaign, _ = planned_v2(c, mode='learn')
        trial, episode, bundle = await v2_f4_episode(c, campaign)
        journal = [(o.result.tool, o.result.error_code) for o in bundle.observations]
        assert journal == [('get_order', None), ('update_order', None),
                           ('send_confirmation', 'TRANSIENT_UNAVAILABLE'), ('send_confirmation', 'TRANSIENT_UNAVAILABLE')]
        ids = [o.evidence_id for o in bundle.observations]
        # The agent's side: contiguous labels, every cited token was shown and decoded (no gap, nothing undecoded).
        submitted, = events(c, trial.episode_id, 'report_submitted')
        payload = submitted['payload']
        assert payload['citation_protocol'] == PROTOCOL_VERSION == 'faultlab-native-adapter/v2.1-shown-order-labels'
        assert payload['labels_shown_to_agent'] == ['obs-1', 'obs-2', 'obs-3']
        assert payload['cited_evidence_tokens'] == ['obs-1', 'obs-2', 'obs-3'] and payload['cited_tokens_not_decoded'] == []
        assert payload['decoded_evidence_ids'] == episode['report']['evidence_ids'] == [ids[0], ids[1], ids[3]]

        # The diagnosis Mechanic's actual request for this episode.
        provider = Capturing(lambda context: {'proposed_kind': 'INCONCLUSIVE', 'hypothesis': 'Scripted reader.',
                                              'evidence_ids': context['evidence_ids'][:1], 'requested_intervention_id': None})
        ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps)
        counter = SimpleNamespace(counterexample_id='counterexample-f4', target_invariant='C5', attempted_count=3,
                                  valid_count=3, target_violation_count=3)
        diagnostic, _ = await Diagnostician(c.store, c.runner, ledger, Mechanic(provider, c.store, ledger)).run(
            campaign, counter, F4_BROKER_RETRIED_SEND, c.policies.baseline(), [], evidence=[bundle])
        assert diagnostic.kind == 'INCONCLUSIVE'
        messages, = provider.requests
        request = messages[-1]['content']
        context = json.loads(request)
        # No agent label anywhere in what the Mechanic reads: not in the report, not in the observations.
        assert not AGENT_LABEL.search(request)
        assert context['evidence_ids'] == ids
        rows, report = episode_view(context['observations'], trial.episode_id)
        assert [row[0] for row in rows] == ids                              # every recorded observation, exact IDs
        # The report is shown decoded, in the rows' own alias space: o1, o2, o4. o3 is the hidden first send attempt,
        # which the agent was never shown and did not cite; every alias names a row of this episode.
        assert report['evidence_ids'] == ['o1', 'o2', 'o4']
        assert all(1 <= int(alias[1:]) <= len(rows) for alias in report['evidence_ids'])
        contract = context['runtime_contract']['actor_contract']
        assert contract['memory'] == V2_MEMORY and contract['adapter_protocol'] == adapter_protocol()
        assert contract['adapter_protocol']['version'] == PROTOCOL_VERSION
        assert 'order the observations were first shown' in V2_MEMORY and 'can differ from' in V2_MEMORY
        assert 'journal label' not in canonical_json(contract)             # the first v2 build's (now wrong) wording
    finally:
        await c.close()


@pytest.mark.anyio
async def test_the_explorer_reads_the_same_decoded_view_of_that_episode(tmp_path):
    c = await runtime(tmp_path)
    try:
        campaign, _ = planned_v2(c, mode='learn')
        trial, episode, bundle = await v2_f4_episode(c, campaign)
        baseline = c.policies.baseline()
        provider = Capturing(lambda context: {'fault_spec': F4_BROKER_RETRIED_SEND.model_dump(mode='json'),
                                              'hypothesis': 'Scripted reader.'})
        ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps)
        explorer = Explorer(provider, c.store, ledger)
        slot = {'campaign_id': campaign.campaign_id, 'configuration_hash': campaign.configuration_hash,
                'policy_hash': baseline.policy_hash, 'selection_index': 0, 'development_history': [],
                'development_evidence': summarize_evidence([bundle]), 'runtime_contract': runtime_contract(c.store, campaign)}
        await explorer.select(slot)
        messages, = provider.requests
        request = messages[-1]['content']
        assert not AGENT_LABEL.search(request)
        context = json.loads(request)
        rows, report = episode_view(context['development_evidence'], trial.episode_id)
        assert report['evidence_ids'] == ['o1', 'o2', 'o4'] and len(rows) == 4
        assert context['runtime_contract']['actor_contract']['memory'] == V2_MEMORY
    finally:
        await c.close()


@pytest.mark.anyio
async def test_v1_and_reference_views_are_unchanged(tmp_path):
    from app.agents.actor import ACTOR_PROMPT
    c = await runtime(tmp_path)
    try:
        v1 = runtime_contract(c.store, planned_campaign(c))['actor_contract']
        assert v1['memory'] == ('Fresh native agent and empty native memory for each episode; original reports cite full '
                                'delivered evidence IDs.')
        assert 'adapter_protocol' not in v1
        assert runtime_contract()['actor_contract'] == ACTOR_PROMPT
    finally:
        await c.close()
