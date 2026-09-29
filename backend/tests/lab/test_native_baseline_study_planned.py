"""Blocker B2 of the native baseline probe plan (artifacts/product-live-2026-09-28/plans/native/PLAN.md).

The product's baseline study (POST /api/campaigns/{id}/baseline-study) on a PLANNED live baseline
campaign whose saved plan names the native smolagents registration. Offline and $0: the model
transport is the tests' declared scripted native input (NativeReferenceInputs), the simulator is
in-process, and Weave is the local double from test_baseline_study. Nothing here is model evidence.

The runner is a plain EpisodeRunner, not OfflineRunner(offline_fixture=True): the study labels B0
'live', and an offline-fixture runner refuses that label (runner.resolve_execution). The settings
mirror the plan's section 4.3 (actor DeepSeek-V3.1 at $0.55/$1.65 per million, Explorer/Mechanic
V4-Pro-0813 at $1.31/$3.96, caps 6,000 calls / 204M tokens / $100), so the reservation and the
conservative dollar arithmetic below are the ones the paid run will use.
"""
import json

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.config import Settings
from app.contracts.models import canonical_json
from app.integrations.registry import AgentRegistry
from app.lab.baseline_study import MODEL_CALL_RESERVATION
from app.lab.budgets import PROTECTED, protected_reservations
from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceGateway
from app.lab.run_plans import read_run_plan
from app.lab.runner import B1_CONTROL_ID, B1_CONTROL_MODEL, EpisodeRunner
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app
from app.telemetry.evaluations import EvaluationPublisher
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.tracing import TraceRecorder
from original_loop_fixture import CONTROL
from test_baseline_study import StudyRemoteDouble
from test_planned_agent_execution import NativeReferenceInputs, planned_campaign

ACTOR_MODEL = 'deepseek-ai/DeepSeek-V3.1'
REASONING_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
NATIVE_ENTRYPOINT = 'smolagents-toolcalling-v1'
# Plan section 8: 32,000 x $0.55/M + 2,000 x $1.65/M per V3.1 request; 144 of them at most.
ACTOR_CALL_BOUND = 32000 * .55 / 1e6 + 2000 * 1.65 / 1e6
# Scripted token counts per generation (declared fixture values, not measurements).
IN_TOKENS, OUT_TOKENS = 1000, 50


@pytest.fixture
def anyio_backend(): return 'asyncio'


def plan_settings(path):
    """Plan 4.3's non-secret process settings; placeholder credentials never reach a provider."""
    return Settings(wandb_api_key='offline-test-no-provider', wandb_entity='offline-fixture',
        wandb_project='native-baseline-study', wandb_model=ACTOR_MODEL,
        wandb_explorer_model=REASONING_MODEL, wandb_mechanic_model=REASONING_MODEL,
        faultlab_artifact_dir=str(path), faultlab_control_token=CONTROL, faultlab_live_enabled=True,
        faultlab_confirmed_entity='offline-fixture', faultlab_model_call_cap=6000,
        faultlab_token_cap=204_000_000, faultlab_dollar_cap=100,
        faultlab_input_dollars_per_million=.55, faultlab_output_dollars_per_million=1.65,
        faultlab_pricing_model=ACTOR_MODEL, faultlab_pricing_verified=True,
        faultlab_reasoning_input_dollars_per_million=1.31, faultlab_reasoning_output_dollars_per_million=3.96,
        faultlab_reasoning_pricing_model=REASONING_MODEL, faultlab_reasoning_pricing_verified=True)


class PricedNativeInputs(NativeReferenceInputs):
    """The same public native decision fixture, returned as the frozen actor model with token counts."""
    async def complete(self, messages, *, role='actor', **kwargs):
        output = await super().complete(messages, role=role, **kwargs)
        return RuntimeGeneration(output.content, ACTOR_MODEL, IN_TOKENS, OUT_TOKENS,
                                 (IN_TOKENS * .55 + OUT_TOKENS * 1.65) / 1e6)


def study_runtime(tmp_path, provider):
    settings = plan_settings(tmp_path / 'lab')
    c = LabCoordinator(settings)
    simulator = create_app(database_dir=tmp_path / 'worlds', control_token=CONTROL, settings=settings)
    world = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    remote = StudyRemoteDouble(); outbox = TelemetryOutbox(c.store); trace = TraceRecorder(remote, outbox)
    c.runner = EpisodeRunner(c.store, WorldClient('http://127.0.0.1:8001', CONTROL, client=world), provider, trace=trace)
    c.evidence_gateway = EvidenceGateway(c.store, 'entity/project', trace=trace, worker=remote)
    c.evaluation_publisher = EvaluationPublisher(remote, outbox)
    from app.main import create_app as backend_app
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app(coordinator=c)), base_url='http://127.0.0.1:8000')
    return c, world, api, remote


@pytest.mark.anyio
async def test_planned_native_baseline_study_runs_36_slots_through_the_product_api(tmp_path, monkeypatch):
    provider = PricedNativeInputs('accepted')
    c, world, api, remote = study_runtime(tmp_path, provider)
    verified = []
    original_verify = AgentRegistry.verify
    def spy_verify(self, registration_id, target):
        verified.append(registration_id)
        return original_verify(self, registration_id, target)
    monkeypatch.setattr(AgentRegistry, 'verify', spy_verify)
    try:
        # The plan's product path: a planned live baseline campaign naming the native registration.
        campaign = planned_campaign(c)
        plan = read_run_plan(c.store, campaign)['plan']
        native_id = plan['agent_registration_id']
        registration = AgentRegistry(c.store).get(native_id)
        assert plan['agent'] == 'smolagents' and registration.adapter_entrypoint_id == NATIVE_ENTRYPOINT
        assert campaign.mode == 'baseline' and campaign.config_profile_id == 'live-v1' and campaign.model == ACTOR_MODEL
        assert campaign.state == 'IDLE' and campaign.active_policy_version == 'policy-v0'
        assert type(c.runner) is EpisodeRunner and c.runner.offline_fixture is False
        assert c.settings.model_call_dollar_bounds['actor'] == pytest.approx(ACTOR_CALL_BOUND)
        verified.clear()

        response = await api.post(f'/api/campaigns/{campaign.campaign_id}/baseline-study', json={'execute_live': True})
        assert response.status_code == 202, response.text
        queued = response.json()
        study_id = queued['study_id']
        reservation = 'baseline:' + study_id
        ledger = c.ledgers[campaign.campaign_id]
        # Admission: whole batch reserved before any call, beside the unchanged protected reserves.
        assert queued['status'] == 'QUEUED' and queued['planned_trials'] == 36
        assert queued['reserved_model_calls'] == MODEL_CALL_RESERVATION == 144
        assert queued['source_mode_by_arm'] == {'B0': 'live', 'B1': 'offline_fixture'}
        assert ledger.reservations[reservation]['calls'] == 144
        assert ledger.reserved_calls == sum(PROTECTED.values()) + 144 == 1064 + 144
        assert provider.calls['actor'] == 0 and not c.store.list_records('episodes')
        slots = queued['slots']
        assert len(slots) == 36 and len({s['episode_id'] for s in slots}) == 36
        assert sorted(s['arm'] for s in slots) == ['B0'] * 18 + ['B1'] * 18
        cases = sorted({s['case_id'] for s in slots})
        assert len(cases) == 6 and all(sum(s['case_id'] == case for s in slots) == 6 for case in cases)

        await c.tasks[study_id]
        result = (await api.get('/api/baseline-studies/' + study_id)).json()
        assert result['status'] == 'COMPLETED', result['reason']
        assert all(slot['status'] == 'COMPLETED' for slot in result['slots'])
        assert len(result['trials']) == 36 and len({t['world_id'] for t in result['trials']}) == 36

        episodes = {e['episode_id']: e for e in c.store.list_records('episodes')}
        assert len(episodes) == 36 and {e['study_id'] for e in episodes.values()} == {study_id}
        assert {e['configuration_hash'] for e in episodes.values()} == {campaign.configuration_hash}
        b0 = [t for t in result['trials'] if t['arm'] == 'B0']
        b1 = [t for t in result['trials'] if t['arm'] == 'B1']
        assert len(b0) == len(b1) == 18

        # B0: every episode is the plan's native registration on the smolagents entry point.
        for trial in b0:
            episode = episodes[trial['episode_id']]
            execution = c.store.get_record('episode_executions', trial['episode_id'])
            assert episode['agent_registration_id'] == native_id and episode['source_mode'] == 'live'
            assert episode['model'] == ACTOR_MODEL
            assert execution['kind'] == 'reviewed_registered_agent' and execution['registration_id'] == native_id
            assert execution['adapter_entrypoint_id'] == NATIVE_ENTRYPOINT and execution['offline_fixture'] is False
            assert execution['source_hash'] == registration.source_hash and execution['prompt_hash'] == registration.prompt_hash
            assert 1 <= trial['usage']['model_calls'] <= 8
        # B1: the free handwritten reference control, zero model calls.
        for trial in b1:
            episode = episodes[trial['episode_id']]
            execution = c.store.get_record('episode_executions', trial['episode_id'])
            assert episode['agent_registration_id'] == B1_CONTROL_ID and episode['model'] == B1_CONTROL_MODEL
            assert episode['source_mode'] == 'offline_fixture'
            assert execution['kind'] == 'deterministic_reference_control'
            assert execution['selected_agent_registration_id'] == native_id
            assert trial['usage']['model_calls'] == 0
        assert result['by_arm']['B1']['usage']['model_calls'] == 0
        assert result['by_arm']['B0']['counts']['valid'] == 18 and result['by_arm']['B1']['counts']['valid'] == 18
        # Plan S2: the control's expected outcomes (dev-5 is the rejected upgrade).
        slot_case = {s['episode_id']: s['case_id'] for s in result['slots']}
        b1_outcomes = {slot_case[t['episode_id']]: set() for t in b1}
        for trial in b1: b1_outcomes[slot_case[trial['episode_id']]].add(trial['outcome'])
        assert b1_outcomes == {case: {'CORRECTLY_REJECTED' if case == 'dev-5' else 'COMPLETED'} for case in cases}

        # Accounting: every B0 generation was charged once against the batch; B1 charged nothing.
        b0_calls = sum(t['usage']['model_calls'] for t in b0)
        assert provider.calls['actor'] == b0_calls == result['charged_model_calls'] == ledger.used_calls <= 144
        assert result['usage']['model_calls'] == b0_calls
        assert ledger.unknown_token_calls == ledger.unknown_cost_calls == 0
        assert ledger.measured_input == IN_TOKENS * b0_calls and ledger.measured_output == OUT_TOKENS * b0_calls
        assert ledger.used_dollar_upper_bound == pytest.approx(b0_calls * ACTOR_CALL_BOUND)
        assert ledger.used_dollar_upper_bound <= 144 * ACTOR_CALL_BOUND == pytest.approx(3.0096)
        # The batch reservation is released; the protected reserves are exactly as before.
        budget = c.store.get_record('budgets', campaign.campaign_id)
        assert reservation not in ledger.reservations and reservation not in budget['reservations']
        assert ledger.reservations == budget['reservations'] == protected_reservations(campaign.caps)
        assert ledger.reserved_calls == 1064 and budget['used_calls'] == b0_calls

        # The campaign ends COMPLETED on the unchanged empty baseline policy; scheduler released.
        final = c.get(campaign.campaign_id)
        assert final.state == 'COMPLETED' and final.active_policy_version == 'policy-v0'
        assert len(c.policies.list()) == 1 and c.active_id is None
        # The plan's native registration was re-verified for every episode (both arms).
        assert set(verified) == {native_id} and len(verified) >= 36

        # Weave doubles: B0 remote evidence and evaluation; B1 stays local.
        assert set(result['evidence']) == {t['episode_id'] for t in b0}
        assert set(result['evidence'].values()) == {'weave_verified'}
        assert result['telemetry']['B0']['status'] == 'weave_verified'
        assert result['telemetry']['B1']['status'] == 'local_only'
        assert remote.operations[0] == 'evaluation_init' and len(c.store.list_records('telemetry_predictions')) == 36

        # A second study on the same campaign is refused (plan section 7).
        again = await api.post(f'/api/campaigns/{campaign.campaign_id}/baseline-study', json={'execute_live': True})
        assert again.status_code == 409 and provider.calls['actor'] == b0_calls

        summary = {'b0_model_calls': b0_calls, 'dollar_upper_bound': round(ledger.used_dollar_upper_bound, 4),
                   'per_case': {case: {arm: sorted(t['outcome'] for t in result['trials']
                                                   if t['arm'] == arm and slot_case[t['episode_id']] == case)
                                       for arm in ('B0', 'B1')} for case in cases},
                   'b0_calls_per_case': {case: [t['usage']['model_calls'] for t in b0 if slot_case[t['episode_id']] == case]
                                         for case in cases}}
        print('NATIVE_STUDY_SUMMARY ' + canonical_json(summary))
    finally:
        await api.aclose(); await world.aclose(); await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('change', ['runtime', 'native_source', 'native_prompt'])
async def test_study_refuses_when_plan_registration_differs_from_current_runtime(tmp_path, monkeypatch, change):
    provider = PricedNativeInputs('accepted')
    c, world, api, remote = study_runtime(tmp_path, provider)
    try:
        campaign = planned_campaign(c)
        native_id = read_run_plan(c.store, campaign)['plan']['agent_registration_id']
        before_budget = c.store.get_record('budgets', campaign.campaign_id)
        # Simulate the installed runtime moving after registration and planning.
        if change == 'runtime':
            import app.lab.configuration as configuration
            original = configuration.runtime_fingerprints
            monkeypatch.setattr(configuration, 'runtime_fingerprints', lambda: {**original(), 'runtime_hash': '0' * 64})
        elif change == 'native_source':
            monkeypatch.setattr('app.integrations.registry.verify_native_source', lambda: 'f' * 64)
        else:
            # Takes the adapter entry point since native adapter v2 was added (v1 is its default).
            monkeypatch.setattr('app.integrations.registry.native_prompt_hash', lambda *entrypoint: 'e' * 64)
        response = await api.post(f'/api/campaigns/{campaign.campaign_id}/baseline-study', json={'execute_live': True})
        assert response.status_code == 409, response.text
        assert response.json()['error']['code'] == 'CONFLICT'
        assert response.json()['error']['message'] == ('Current source, model or campaign limits differ from the saved plan. '
                                                       'Register the agent again and create a new campaign; this saved plan stays readable')
        # Refused before admission: no study, reservation, episode, world or model call.
        assert not c.store.list_records('baseline_studies') and not c.tasks
        assert not c.store.list_records('episodes') and provider.calls['actor'] == 0
        assert not list((tmp_path / 'worlds').glob('*.sqlite3'))
        ledger = c.ledgers.get(campaign.campaign_id)
        assert ledger is None or ledger.reserved_calls == 1064
        assert c.store.get_record('budgets', campaign.campaign_id) == before_budget
        assert c.get(campaign.campaign_id).state == 'IDLE' and c.active_id is None
        assert AgentRegistry(c.store).get(native_id).adapter_entrypoint_id == NATIVE_ENTRYPOINT
    finally:
        await api.aclose(); await world.aclose(); await c.close()
