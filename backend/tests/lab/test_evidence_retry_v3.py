"""faultlab-evidence-retry/v3 (app.lab.evidence_wait), offline and $0.

Live run v2f (docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md) had 10 evidence waits; they used up rule v2's 6 automatic retries
per campaign and the PM stopped the campaign early. Rule v3 keeps the per-wait rule (3 automatic retries, 30 s, 120 s and
300 s) and raises the campaign cap to 24. Every new Learn plan freezes v3; a plan saved under v2 still starts and keeps
its cap of 6 (EvidenceWait reads the cap from the plan). The real coordinator, learning loop, evidence wait, retry-evidence
job, ledger and plan run with the doubles of tests/lab/test_evidence_wait.py; no provider, W&B, model or network call.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.contracts.models import content_hash
from app.lab import evidence_wait
from app.lab.discovery_protocol import DISCOVERY_V1
from app.lab.run_plans import EvidenceRetryPlan, EvidenceRetryPlanV3, read_run_plan, validate_run_plan
from app.lab.storage import StoreConflict
from test_discovery_v2_flow import learn_campaign, owner  # noqa: F401  (fixture)
from test_evidence_wait import api_get, assert_nothing_ran_during_waits, harness, purpose_is, retries, until, verified_record, waits

# content_hash(declaration()) of rule v2 before v3 existed (identity-before.json of this build, runtime 95042e4d): every
# saved v2 plan froze exactly this block, and Start must still accept it.
V2_DECLARATION_HASH = '3d84989305183a30635f268621af38f79206c0f80a26aa87386e5d20db64dd0d'


def test_new_learn_plans_declare_v3_with_24_per_campaign_and_v2_is_unchanged(owner):
    rule = evidence_wait.declaration()
    assert (rule['protocol'], rule['automatic_retries_per_wait'], rule['automatic_retries_per_campaign'], rule['delays_seconds']) == \
        ('faultlab-evidence-retry/v3', 3, 24, [30, 120, 300])
    assert 'at most 3 times per wait and at most 24 times per campaign' in rule['rule']
    v2 = evidence_wait.declaration_v2()
    assert content_hash(v2) == V2_DECLARATION_HASH and v2['automatic_retries_per_campaign'] == 6
    assert {k: v for k, v in rule.items() if k not in ('protocol', 'automatic_retries_per_campaign', 'rule')} == \
        {k: v for k, v in v2.items() if k not in ('protocol', 'automatic_retries_per_campaign', 'rule')}
    assert rule['rule'].replace('24 times', '6 times') == v2['rule']
    EvidenceRetryPlanV3.model_validate(rule); EvidenceRetryPlan.model_validate(v2)
    campaign = learn_campaign(owner, DISCOVERY_V1)
    plan = read_run_plan(owner.store, campaign.campaign_id)['plan']
    assert plan['evidence_retry'] == rule
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))['plan_hash'] == plan['plan_hash']


def test_a_plan_saved_under_v2_still_starts_and_keeps_its_cap_of_six(owner, monkeypatch):
    from app.lab import run_plans
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration', evidence_wait.declaration_v2)   # saved before v3
    campaign = learn_campaign(owner, DISCOVERY_V1)
    monkeypatch.undo()
    plan = read_run_plan(owner.store, campaign.campaign_id)['plan']
    assert plan['evidence_retry'] == evidence_wait.declaration_v2()
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))['plan_hash'] == plan['plan_hash']
    assert evidence_wait.campaign_rule(owner.store, owner.get(campaign.campaign_id))['automatic_retries_per_campaign'] == 6
    # An installed rule that is neither v2 nor v3 (for example another v3 text) refuses it, as before.
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration_v2', lambda: {**evidence_wait.declaration_v2(), 'rule': 'x'})
    with pytest.raises(StoreConflict, match='automatic evidence retry rule differs'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))


def wait_with_prior_attempts(owner, rule, prior):
    """An EvidenceWait of a campaign whose earlier waits already made ``prior`` automatic retries."""
    campaign = learn_campaign(owner, DISCOVERY_V1)
    ident = campaign.campaign_id
    for index in range(0, prior, 3):
        made = min(3, prior - index)
        owner.store.put_record('evidence_waits', f'evidence-wait-prior-{index}', {
            'wait_id': f'evidence-wait-prior-{index}', 'campaign_id': ident, 'started_at': f'2026-09-30T00:00:{index:02d}+00:00',
            'ended_at': f'2026-09-30T00:00:{index:02d}+00:00', 'status': 'RESOLVED',
            'automatic_attempts': [{'attempt': n + 1} for n in range(made)]})
    return evidence_wait.EvidenceWait(owner, ident, 'episode-blocked', ['episode-blocked'], rule)


@pytest.mark.parametrize('rule,cap', [(evidence_wait.declaration(), 24), (evidence_wait.declaration_v2(), 6)])
def test_the_campaign_cap_comes_from_the_plan(owner, rule, cap):
    assert wait_with_prior_attempts(owner, rule, cap - 1)._limit_reached() is None           # one more is allowed
    assert wait_with_prior_attempts(owner, rule, cap)._limit_reached() == 'PER_CAMPAIGN'     # the cap is reached


def test_under_v3_the_flaky_batch_that_stopped_v2_at_six_keeps_retrying(owner, monkeypatch):
    """The six-episode flaky batch of test_evidence_wait.test_the_campaign_limit_ends_automatic_retries_for_a_flaky_batch:
    under v2 its third wait showed "needs operator" after 6 retries. Under v3 every wait gets its 3 retries and every
    episode's evidence is verified: 18 automatic retries, telemetry only, no "needs operator". (This is the scenario v2's
    cap was added for: v3 accepts up to 24 retries, about 60 declared minutes, before "needs operator".)"""
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('source_validation'), mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    assert read_run_plan(owner.store, ident)['plan']['evidence_retry'] == evidence_wait.declaration()
    first_listed = {}
    async def services():
        weave.jobs += 1
        class Worker:
            async def start(self): pass
            async def close(self): weave.closed += 1
        class OnlyTheBlockedEpisodeOnItsThirdTry:
            first = True
            async def retry(self, episode_id, **kwargs):
                weave.retried.append(episode_id); weave.snapshots.append(('retry', weave.counts()))
                is_first, self.first = self.first, False
                if is_first:
                    first_listed[episode_id] = first_listed.get(episode_id, 0) + 1
                    if first_listed[episode_id] >= 3:
                        weave.cleared.add(episode_id)
                        owner.store.put_record('evidence', episode_id, verified_record(episode_id))
                        return SimpleNamespace(source='weave_verified')
                raise RuntimeError('fake partial outage')
        return Worker(), OnlyTheBlockedEpisodeOnItsThirdTry(), object()
    owner._evidence_retry_services = services
    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: len(waits(owner, ident)) >= 6 and all(w['status'] == 'RESOLVED' for w in waits(owner, ident)[:6]), seconds=60)
        observed = (waits(owner, ident)[:6], len(retries(owner, ident)),
                    (await api_get(owner, f'/api/campaigns/{ident}/evidence-wait'))[1])
        await owner.stop(ident); await task
        return observed
    six, made, body = asyncio.run(scenario())
    assert [len(w['automatic_attempts']) for w in six] == [3] * 6 and made == 18 > 6
    assert all(w['automatic_retries_campaign_max'] == 24 and w['limit_reached'] is None for w in six)
    assert not any(w['status'] == 'NEEDS_OPERATOR' for w in waits(owner, ident))
    assert body['declared'] == evidence_wait.declaration() and body['automatic_retries_total'] == 18
    assert_nothing_ran_during_waits(weave)
    assert owner.get(ident).state == 'STOPPED'
