"""A dropped Explorer connection no longer ends a whole campaign (campaign a301846e's failure).

The real coordinator runs a declared discovery-v2 Learn campaign through _execute: real
Explorer, ledger, plan and learning loop; a scripted Explorer model and a fake Actor runner.
No provider, simulator port, W&B or model call is made.

Since rule v2 (faultlab-transport-retry/v2-lab-backoff) every NEW Learn plan declares lab-role
backoff (tests/lab/test_lab_transport_backoff.py). The tests below pin that a Learn plan saved
before it, which declares rule v1, still runs exactly rule v1: one blind retry, no backoff.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents.transport_retry import declaration as rule_v1
from app.lab.budgets import CampaignLedger
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2
from app.lab.run_plans import read_run_plan
from app.providers.runtime import RuntimeProviderError
from test_discovery_v2_flow import DELAYED, ScriptedExplorer, learn_campaign, owner, raw  # noqa: F401  (fixture)
from test_evaluation import FakeRunner


class Flaky(ScriptedExplorer):
    """Fails the chosen request numbers with a connection error (no generation), else answers."""
    def __init__(self, answer, failing):
        super().__init__(answer); self.failing = set(failing); self.sent = 0
    async def complete(self, messages, **kwargs):
        self.sent += 1
        if self.sent in self.failing:
            raise RuntimeProviderError('scripted APIConnectionError; SDK text never stored', code='CONNECTION_ERROR',
                                       error_class='APIConnectionError')
        return await super().complete(messages, **kwargs)


def learn_campaign_v1_rule(owner, protocol=None, agent='reference'):
    """A Learn plan as saved before rule v2 existed: it declares rule v1 (one blind retry per request)."""
    from app.lab.run_plans import prepare_run_plan
    from app.lab.operator_actions import register_agent
    from test_discovery_v2_flow import request
    registration = register_agent(owner.store, owner.settings, agent)
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration, discovery_protocol=protocol))
    prepared.plan['transport_retry'] = rule_v1(prepared.plan['episode_budget']['actor_calls'])
    return owner.create(prepared.campaign_request, run_plan=prepared)


def execute(owner, campaign, provider, *, headroom=None):
    """Run the campaign's own _execute, as Start does after admission."""
    id = campaign.campaign_id
    ledger = CampaignLedger(owner.store, id, owner.get(id).caps)
    if headroom is not None:
        # Leave exactly `headroom` unreserved calls, so admission decides what may be sent.
        ledger.used_calls = ledger.caps.model_calls - ledger.reserved_calls - headroom
        ledger.used_tokens = 0
        ledger._save()
    owner.ledgers[id] = ledger
    class Evidence:
        async def get(self, episode_id, context, **kwargs):
            return SimpleNamespace(episode_id=episode_id, source='weave_verified', report=None, findings=[], observations=[])
    owner.evidence_gateway = Evidence()
    runner = FakeRunner('tie'); runner.provider = provider; original = runner.run
    async def persisted(current, recipe, policy, **kwargs):
        trial = await original(current, recipe, policy, **kwargs)
        owner.store.put_record('episodes', trial.episode_id, {'campaign_id': current.campaign_id,
            'configuration_hash': current.configuration_hash, 'policy_hash': policy.policy_hash, 'scenario_hash': trial.scenario_hash,
            'split': 'development', 'experiment_purpose': 'discovery', 'study_id': current.campaign_id,
            'evidence_context_id': current.campaign_id, 'selector_id': None,
            'verdict': {'fault_executions': [{'triggered': True, 'reason': None} for _ in recipe.primitives]}})
        return trial
    runner.run = persisted
    owner.runner = runner; owner.active_id = id
    asyncio.run(owner._execute(id, True))
    return owner.get(id), ledger, runner


@pytest.mark.parametrize('protocol', [DISCOVERY_V1, DISCOVERY_V2])
def test_one_lost_explorer_connection_is_retried_and_the_campaign_continues(owner, protocol):
    campaign = learn_campaign_v1_rule(owner, protocol)
    provider = Flaky(lambda slot, request, context: raw(DELAYED, seed=slot), failing={1})
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'NO_CHANGE', final.terminal_reason       # the campaign ran to its normal end
    retry, = owner.store.list_records('transport_retries')
    failure, = owner.store.list_records('provider_failures')
    assert retry['role'] == 'explorer' and retry['code'] == 'CONNECTION_ERROR' and retry['campaign_id'] == campaign.campaign_id
    assert retry['provider_failure_id'] == failure['failure_id'] and failure['diagnostics']['error_class'] == 'APIConnectionError'
    assert provider.sent == len(provider.contexts) + 1                # one extra request: the retry
    assert ledger.used_calls == provider.sent                          # every request, the retry included, is charged
    first = next(row for row in owner.store.list_records('selections') if row['context']['selection_index'] == 0
                 and (row['search_decision'] or {}).get('slot_request', 1) == 1)
    assert first['usage']['model_calls'] == 2 and first['transport_retries'][0]['retry_id'] == retry['retry_id']
    assert not owner.store.list_records('execution_errors')
    plan = read_run_plan(owner.store, campaign.campaign_id)['plan']
    assert plan['discovery']['explorer_transport_retries_max'] == plan['discovery']['explorer_requests_max']
    assert plan['transport_retry']['retries_per_request'] == 1


def test_two_lost_connections_on_one_request_end_the_campaign_error_as_before(owner):
    campaign = learn_campaign_v1_rule(owner, DISCOVERY_V2)
    provider = Flaky(lambda slot, request, context: raw(DELAYED, seed=slot), failing={3, 4})
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'ERROR' and final.terminal_reason.startswith('CONNECTION_ERROR:')
    error, = owner.store.list_records('execution_errors')
    assert error['code'] == 'CONNECTION_ERROR' and error['diagnostics']['error_class'] == 'APIConnectionError'
    assert provider.sent == 4 and ledger.used_calls == 4                # 2 answered + the failed request + its one retry
    assert len(owner.store.list_records('transport_retries')) == 1
    assert len(owner.store.list_records('provider_failures')) == 2


def test_a_retry_the_budget_cannot_cover_is_refused_before_sending_and_the_campaign_errors(owner):
    campaign = learn_campaign_v1_rule(owner, DISCOVERY_V2)
    provider = Flaky(lambda slot, request, context: raw(DELAYED, seed=slot), failing={1})
    final, ledger, runner = execute(owner, campaign, provider, headroom=1)
    assert final.state == 'ERROR' and final.terminal_reason.startswith('CONNECTION_ERROR:')  # the original failure
    assert provider.sent == 1                                            # the retry was never sent
    assert not owner.store.list_records('transport_retries')
    assert owner.store.get_record('budgets', campaign.campaign_id)['used_calls'] == ledger.caps.model_calls - ledger.reserved_calls
