"""Independent verifier probes ($0, offline). Copied into a SCRATCH tree's backend/tests/lab/ (never into the product tree)
and run there with the verifier guard as a pytest plugin. They reuse the product's own test fixtures.

A  HIGH-1: with the challenge-pick rule DECLARED, the integrity scenario passes (the rule hides C4); without it, the
   counterexample is found. Shows the withdrawal matters and the fixer's test is sensitive to it.
B  I-LOW-3(b): a later candidate request whose FIRST turn the Mechanic refuses, after an earlier request's answers were
   saved, is recorded BEFORE_SEND (the record-row cutoff must ignore the earlier request's saved answer).
C  I-LOW-3(a): the NO_CHANGE reason with the size-rule note stays within the 600-character reason limit for 1..12 ended
   searches, names at most 3 record ids, and a campaign's final reason is valid for the Campaign model.
D  Withdrawal end to end: a new Learn plan, read back through the real API's plan route, carries the Mechanic rule
   only (run options are covered by the product test; the route reads audit/promotion.json, refused by the guard).
"""
import asyncio

import pytest

from app.contracts import tokens
from app.contracts.tokens import ModelInputLimit
from app.lab import loop_limits
from app.lab.loop_limits import challenge_selection_declaration, mechanic_context_declaration


@pytest.fixture
def anyio_backend(): return 'asyncio'


def test_A_the_declared_rule_would_hide_the_counterexample_and_the_withdrawal_restores_it(tmp_path):
    from test_loop_limits_challenge_reach import confirmation_sensitive_challenge
    declared = asyncio.run(confirmation_sensitive_challenge(tmp_path / 'declared', challenge_selection_declaration()))
    undeclared = asyncio.run(confirmation_sensitive_challenge(tmp_path / 'undeclared', None))
    assert declared.status == 'PASSED_OBSERVED' and not declared.failed_checks
    assert (undeclared.status, undeclared.failed_checks) == ('COUNTEREXAMPLE_FOUND', ['C4'])


@pytest.mark.anyio
async def test_B_a_later_first_turn_refusal_is_before_send_despite_an_earlier_saved_answer(tmp_path, monkeypatch):
    import app.agents.mechanic as mechanic_module
    from app.lab.learning import run_learning_cycle
    from test_loop_limits_mechanic_context import learning_loop, records
    # Request 1: two invalid answers (first turn + its format-repair turn), both sent and saved: an invalid candidate.
    # Request 2: the Mechanic's own check refuses its FIRST turn (the 3rd admission check), so nothing is sent.
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, ['not json', 'still not json'], limit=None)
    campaign.caps.candidates = 2; c.save(campaign)
    original = tokens.validate_model_input; checks = []
    def admit(messages, model):
        checks.append(len(messages))
        if len(checks) == 3: raise ModelInputLimit(40000)
        return original(messages, model)
    monkeypatch.setattr(mechanic_module, 'validate_model_input', admit)
    await run_learning_cycle(c, campaign, runner)
    assert c.get(campaign.campaign_id).state == 'NO_CHANGE' and len(provider.sent) == 2 and checks[:3] == [2, 4, 2]
    ended, = records(c)
    assert ended['stage'] == 'BEFORE_SEND' and 'Nothing was sent' in ended['reason'] and 'first_turn_output_ref' not in ended
    proposals = c.store.list_records('campaign_proposals')
    assert len(proposals) == 1 and proposals[0].get('reason') != 'FORMAT_REPAIR_OVER_LIMIT'   # only request 1's own record


def test_C_the_no_change_reason_stays_within_the_limit(tmp_path):
    from app.contracts.models import Campaign
    from app.lab.storage import LabStore
    store = LabStore(tmp_path / 'lab.db')
    base = 'No verified strict improvement within declared development bounds; all outcomes retained'
    longest = 0
    for n in range(1, 13):
        loop_limits._record(store, campaign_id='campaign-probe', outcome='SEARCH_ENDED', stage='BEFORE_SEND', reason='x',
                            provider_dispatch=False)
        note = loop_limits.search_ended_note(store, 'campaign-probe')
        reason = base + '; ' + note
        longest = max(longest, len(reason))
        assert len(reason) <= 600 and note.count('mechanic-context-') == min(n, 3)
        assert (f'and {n - 3} more' in note) == (n > 3)
        field = Campaign.model_fields['terminal_reason']
        from pydantic import TypeAdapter
        TypeAdapter(field.annotation).validate_python(reason)          # the Campaign model accepts it
    store.close()
    print('longest NO_CHANGE reason with the note:', longest)


def test_D_the_real_api_offers_and_freezes_the_mechanic_rule_only(owner):
    import httpx
    from app.main import create_app
    from test_discovery_v2_flow import learn_campaign
    from app.lab.run_plans import read_run_plan
    async def get(path):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            response = await api.get(path)
            return response.status_code, response.json()
    # (GET /api/run-options is not called here: it reads audit/promotion.json, which the verifier guard refuses.
    #  The product test test_run_options_and_every_new_learn_plan_... covers run options in the suite.)
    campaign = learn_campaign(owner, None, 'reference')
    plan = read_run_plan(owner.store, campaign)['plan']
    assert plan['mechanic_context'] == mechanic_context_declaration() and 'challenge_selection' not in plan
    code, shown = asyncio.run(get(f'/api/campaigns/{campaign.campaign_id}/plan'))
    assert code == 200, shown
    if True:
        text = str(shown)
        assert 'faultlab-mechanic-context/v2-bounded' in text and 'faultlab-challenge-selection' not in text


from test_discovery_v2_flow import owner  # noqa: E402,F401  (a fixture)
