"""Product review probes for native adapter v2 (smolagents-toolcalling-v2). Offline and $0.

Written by the product reviewer, not by the builder. No provider, model, W&B, Weave or network call:
the repository's own offline guards (tests/conftest.py: network refusal outside marked loopback,
.env audit hook, scratch simulator import) are loaded as a plugin. The model transport is always a
declared scripted replacement from the repository's tests; the simulator is in-process (or an owned
loopback port for the one Learn-loop probe, exactly as the repository's own loop test does).

Run from faultlab/backend:
  PYTHONPATH=tests:tests/lab:tests/integration:tests/integrations PYTHONDONTWRITEBYTECODE=1 \
    ../.venv/bin/python -m pytest -q -c pytest.ini --rootdir . -p conftest -p no:cacheprovider \
    ../artifacts/product-native-v2-2026-09-29/review-product/test_review_native_v2.py

Every probe records what it saw into review_probes.out.json beside this file.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest
import uvicorn

from app.adapters.business_tools import WorldClient
from app.config import Settings
from app.contracts.models import CampaignBudget, FaultSpec, canonical_json, content_hash
from app.integrations.external_agent import SmolagentsActor
from app.integrations.external_agent_v2 import SmolagentsActorV2
from app.integrations.registry import (NATIVE_V1, NATIVE_V2, AgentRegistry, adapter_hash, native_prompt_hash)
from app.lab.configuration import frozen_configuration
from app.lab.coordinator import LabCoordinator
from app.lab.dashboard import store_descriptor
from app.lab.operator_actions import register_agent
from app.lab.run_plans import RunPlanRequest, build_run_options, prepare_run_plan, read_run_plan
from app.lab.storage import StoreConflict
from app.main import create_app
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError
from app.simulator.main import create_app as simulator_app

from original_loop_fixture import (CONTROL, ManualPolicies, OfflineEvidence, OfflineRunner, fixture_settings,
                                   localhost_simulator)
from test_planned_agent_execution import NativeReferenceInputs, runtime
from test_native_adapter_v2 import Scripted, episode, events as adapter_events, transport
from test_native_adapter_v1_golden import MODEL as GOLDEN_MODEL, SCRIPTS, report_citing, shown_evidence_ids

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name('review_probes.out.json')
TASK = 'orders.upgrade_then_confirm/v1'
V2_LABEL = 'smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)'


@pytest.fixture
def anyio_backend(): return 'asyncio'


def record(section, value):
    """Merge one probe's observations into the output file (sorted, pretty, stable)."""
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data[section] = value
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True, default=str) + '\n')


def api_client(c):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://test')


async def plan_via_api(api, options, *, registration_id, mode, case=None, protocol=None, profile='live-v1'):
    body = {'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
            'task_definition_id': TASK, 'mode': mode, 'config_profile_id': profile,
            'task_text': options['task']['task_text_default'], 'order_id': 'order-review'}
    if registration_id is not None: body['agent_registration_id'] = registration_id
    if case: body['development_case_id'] = case
    if protocol: body['discovery_protocol'] = protocol
    return await api.post('/api/planned-campaigns', json=body)


def report_events(store, episode_id):
    return [e for e in store.events(episode_id)['events'] if e['type'] == 'report_submitted']


# ============================================================================ 1. operator flow through the API

@pytest.mark.anyio
async def test_1_api_register_plan_start_v2_and_v1_and_reference_still_work(tmp_path):
    """Register v2 via the API, see it in run options, plan baseline and Learn (v1 and v3 history), press Start."""
    provider = NativeReferenceInputs('accepted')
    c = await runtime(tmp_path, provider=provider)
    c.evidence_gateway = OfflineEvidence(c.store, 'offline-fixture/review-v2')
    out = {}
    try:
        async with api_client(c) as api:
            options = (await api.get('/api/run-options')).json()
            rows = {row['agent']: row for row in options['agents']}
            out['run_options_agents_before'] = {k: {f: v[f] for f in ('label', 'status', 'registered', 'reason_code')} for k, v in rows.items()}
            assert rows['smolagents-v2']['status'] == 'READY' and rows['smolagents-v2']['registered'] is False
            identity = options['data_store']['identity']
            first = await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents-v2'})
            assert first.status_code == 201, first.text
            again = await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents-v2'})
            out['register_v2'] = {'status': first.status_code, 'registration_id': first.json()['registration_id'],
                                  'name': first.json()['name'], 'adapter_entrypoint_id': first.json()['adapter_entrypoint_id'],
                                  'second_identical_register_status': again.status_code,
                                  'second_identical_register_body': again.json() if again.status_code >= 400 else 'same registration returned'}
            v2_id = first.json()['registration_id']
            options = (await api.get('/api/run-options')).json()
            rows = {row['agent']: row for row in options['agents']}
            assert rows['smolagents-v2']['registered'] is True and rows['smolagents-v2']['registration_id'] == v2_id
            assert rows['smolagents']['registered'] is False                   # v2 registration does not register v1
            listed = (await api.get('/api/agent-registrations')).json()
            out['registrations_listed'] = [(r['registration_id'], r['adapter_entrypoint_id']) for r in listed]
            out['v2_limitations'] = rows['smolagents-v2']['limitations']

            # Baseline plan, then the real Start (injected offline runner; scripted native transport).
            planned = await plan_via_api(api, options, registration_id=v2_id, mode='baseline', case='dev-1')
            assert planned.status_code == 201, planned.text
            baseline = planned.json()
            plan = (await api.get(f"/api/campaigns/{baseline['campaign_id']}/plan")).json()
            assert plan['status'] == 'PLANNED' and plan['plan']['agent'] == 'smolagents-v2'
            assert plan['plan']['agent_registration_id'] == v2_id
            c.validate_core_configuration(c.get(baseline['campaign_id']))     # Start's own pre-check, directly
            started = await api.post(f"/api/campaigns/{baseline['campaign_id']}/start", json={})
            assert started.status_code == 202, started.text
            await asyncio.wait_for(c.tasks[baseline['campaign_id']], timeout=60)
            done = (await api.get(f"/api/campaigns/{baseline['campaign_id']}")).json()
            episodes = c.store.list_campaign_episodes(baseline['campaign_id'])
            ep = episodes[0]
            execution = c.store.get_record('episode_executions', ep['episode_id'])
            submitted, = report_events(c.store, ep['episode_id'])
            events_api = (await api.get(f"/api/episodes/{ep['episode_id']}/events")).json()
            api_report = [e for e in events_api['events'] if e['type'] == 'report_submitted']
            recording = (await api.get(f"/api/campaigns/{baseline['campaign_id']}/recording"))
            out['baseline_v2_start'] = {'campaign_state': done['state'], 'episodes': len(episodes),
                'outcome': ep['verdict']['outcome'] if ep.get('verdict') else None, 'lifecycle': ep['lifecycle'],
                'adapter_entrypoint_id': execution['adapter_entrypoint_id'],
                'report_submitted_payload_keys': sorted(submitted['payload']),
                'cited_evidence_tokens': submitted['payload']['cited_evidence_tokens'],
                'decoded_equals_episode_report': submitted['payload']['decoded_evidence_ids'] == ep['report']['evidence_ids'],
                'events_api_shows_raw_and_decoded': bool(api_report) and 'cited_evidence_tokens' in api_report[0]['payload'],
                'recording_status': recording.status_code,
                'recording_contains_cited_tokens': 'cited_evidence_tokens' in recording.text}
            assert done['state'] == 'COMPLETED' and execution['adapter_entrypoint_id'] == NATIVE_V2

            # Learn plans for v2: default discovery v1, v3 history; refused pre-check protocols; refused compare.
            learn_v1 = await plan_via_api(api, options, registration_id=v2_id, mode='learn')
            learn_v3 = await plan_via_api(api, options, registration_id=v2_id, mode='learn', protocol='faultlab-discovery/v3-history')
            refused_v2 = await plan_via_api(api, options, registration_id=v2_id, mode='learn', protocol='faultlab-discovery/v2-reachability')
            refused_v3p = await plan_via_api(api, options, registration_id=v2_id, mode='learn', protocol='faultlab-discovery/v3-history-reachability')
            refused_compare = await plan_via_api(api, options, registration_id=v2_id, mode='compare')
            assert learn_v1.status_code == learn_v3.status_code == 201, (learn_v1.text, learn_v3.text)
            v3_plan = (await api.get(f"/api/campaigns/{learn_v3.json()['campaign_id']}/plan")).json()['plan']
            history = v3_plan['discovery']['history']
            check = (await api.get(f"/api/campaigns/{learn_v3.json()['campaign_id']}/plan/history-check")).json()
            for ident in (learn_v1.json()['campaign_id'], learn_v3.json()['campaign_id']):
                c.validate_core_configuration(c.get(ident))                   # what Start re-checks before admission
            readiness = (await api.get('/api/readiness')).json()
            out['learn_v2'] = {
                'default_protocol_plan_status': learn_v1.status_code,
                'v3_plan_status': learn_v3.status_code,
                'v3_history_agent_identity_entrypoint': history['agent_identity']['adapter_entrypoint_id'],
                'v3_history_summary_agent': history['summary']['agent'],
                'v3_history_status': history['status'],
                'v3_history_note': 'the single-case baseline run above is never history (operator-chosen case), so NO_PRIOR_HISTORY is expected',
                'history_check': check['status'],
                'v3_plan_evidence_retry': v3_plan.get('evidence_retry', {}).get('protocol'),
                'v3_plan_transport_retry': v3_plan.get('transport_retry'),
                'refused_v2_reachability': [refused_v2.status_code, refused_v2.json()],
                'refused_v3_history_reachability': [refused_v3p.status_code, refused_v3p.json()],
                'refused_compare_without_accepted_policy': [refused_compare.status_code, refused_compare.json()],
                'readiness_ready': readiness['ready'], 'readiness_provider_calls': readiness['provider_calls']}
            assert history['agent_identity']['adapter_entrypoint_id'] == NATIVE_V2
            assert refused_v2.status_code == refused_v3p.status_code == 409

            # v1 still registers, plans and runs exactly as before; the reference offline smoke still runs.
            v1 = await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents'})
            options = (await api.get('/api/run-options')).json()
            v1_plan = await plan_via_api(api, options, registration_id=v1.json()['registration_id'], mode='baseline', case='dev-1')
            await api.post(f"/api/campaigns/{v1_plan.json()['campaign_id']}/start", json={})
            await asyncio.wait_for(c.tasks[v1_plan.json()['campaign_id']], timeout=60)
            v1_ep = c.store.list_campaign_episodes(v1_plan.json()['campaign_id'])[0]
            v1_submitted, = report_events(c.store, v1_ep['episode_id'])
            v1_learn_v3 = await plan_via_api(api, options, registration_id=v1.json()['registration_id'], mode='learn', protocol='faultlab-discovery/v3-history')
            v1_history = (await api.get(f"/api/campaigns/{v1_learn_v3.json()['campaign_id']}/plan")).json()['plan']['discovery']['history']
            offline = await plan_via_api(api, options, registration_id=None, mode='baseline', case='dev-2', profile='offline-v1')
            await api.post(f"/api/campaigns/{offline.json()['campaign_id']}/start", json={})
            await asyncio.wait_for(c.tasks[offline.json()['campaign_id']], timeout=60)
            reference = await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'reference'})
            options = (await api.get('/api/run-options')).json()
            ref_plan = await plan_via_api(api, options, registration_id=reference.json()['registration_id'], mode='learn',
                                          protocol='faultlab-discovery/v2-reachability')
            out['v1_and_reference'] = {
                'v1_register': v1.status_code, 'v1_campaign_state': c.get(v1_plan.json()['campaign_id']).state,
                'v1_adapter': c.store.get_record('episode_executions', v1_ep['episode_id'])['adapter_entrypoint_id'],
                'v1_report_submitted_payload_keys': sorted(v1_submitted['payload']),
                'v1_v3_history_entrypoint': v1_history['agent_identity']['adapter_entrypoint_id'],
                'v1_v3_history_status': v1_history['status'],
                'offline_reference_smoke_state': c.get(offline.json()['campaign_id']).state,
                'reference_register': reference.status_code, 'reference_learn_v2_reachability_plan': ref_plan.status_code}
            assert sorted(v1_submitted['payload']) == ['report']
            assert c.get(offline.json()['campaign_id']).state == 'COMPLETED'
    finally:
        record('1_api_operator_flow', out)
        await c.close()


# ============================================================================ 2. CLI registration, real code path

def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


@pytest.mark.localhost_http
def test_2_cli_register_v2_offline_fallback_and_through_a_running_backend(tmp_path, monkeypatch, capsys):
    """The real `regressions register` command: no backend (offline fallback), then a running loopback backend."""
    from app.cli import client, regressions
    out = {}
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'cli-lab'), wandb_model='deepseek-ai/DeepSeek-V3.1')
    monkeypatch.setattr(regressions.Settings, 'from_env', classmethod(lambda cls, **_: settings))   # never the real .env
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', str(_free_port()))                              # nothing listens there
    monkeypatch.setattr(client, 'BASE_URL', None)
    monkeypatch.setattr(sys, 'argv', ['regressions', 'register', '--agent', 'smolagents-v2'])
    code = regressions.main()
    printed = capsys.readouterr().out
    registration = json.loads(printed)
    out['offline_fallback'] = {'exit': code, 'adapter_entrypoint_id': registration['adapter_entrypoint_id'],
                               'registration_id': registration['registration_id'], 'name': registration['name']}
    assert code == 0 and registration['adapter_entrypoint_id'] == NATIVE_V2
    # It is really in the store the backend will open.
    owner = LabCoordinator(settings)
    try:
        saved = AgentRegistry(owner.store).get(registration['registration_id'])
        assert saved.adapter_entrypoint_id == NATIVE_V2
        rows = {row['agent']: row for row in build_run_options(owner.settings, owner.store)['agents']}
        out['offline_fallback']['dashboard_row_registered'] = rows['smolagents-v2']['registered']
        # Now the same command against a running backend (loopback uvicorn owning the store).
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(create_app(coordinator=owner), host='127.0.0.1', port=port, log_level='error', lifespan='off'))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline: time.sleep(.02)
        monkeypatch.setenv('FAULTLAB_BACKEND_PORT', str(port))
        monkeypatch.setattr(sys, 'argv', ['regressions', 'register', '--agent', 'smolagents'])
        try:
            code_v1 = regressions.main(); v1 = json.loads(capsys.readouterr().out)
            monkeypatch.setattr(sys, 'argv', ['regressions', 'register', '--agent', 'smolagents-v2'])
            code_v2 = regressions.main(); v2_again = json.loads(capsys.readouterr().out)
        finally:
            server.should_exit = True; thread.join(timeout=10)
        out['through_backend'] = {'v1_exit': code_v1, 'v1_entrypoint': v1['adapter_entrypoint_id'],
                                  'v2_exit': code_v2, 'v2_same_id_as_offline': v2_again['registration_id'] == registration['registration_id']}
        assert v1['adapter_entrypoint_id'] == NATIVE_V1 and v2_again['registration_id'] == registration['registration_id']
    finally:
        asyncio.run(owner.close())
    monkeypatch.setattr(sys, 'argv', ['regressions', 'register', '--agent', 'smolagents-v3'])
    with pytest.raises(SystemExit) as refused:
        regressions.main()
    out['unknown_agent'] = {'exit': refused.value.code, 'stderr_tail': capsys.readouterr().err.strip().splitlines()[-1]}
    record('2_cli_register', out)


# ============================================================================ 3. v2 baseline study -> v2's own history -> v3 Learn Start

@pytest.mark.anyio
async def test_3_v2_baseline_study_feeds_only_v2_history_and_a_v3_learn_campaign_runs(tmp_path):
    from test_native_baseline_study_planned import PricedNativeInputs, study_runtime
    provider = PricedNativeInputs('accepted')
    c, world, api, remote = study_runtime(tmp_path, provider)
    c.policies = ManualPolicies(c.store)
    out = {}
    try:
        identity = store_descriptor(c.store)['identity']
        v1 = (await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents'})).json()
        v2 = (await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents-v2'})).json()
        options = (await api.get('/api/run-options')).json()
        baseline = (await plan_via_api(api, options, registration_id=v2['registration_id'], mode='baseline', case='dev-1')).json()
        queued = await api.post(f"/api/campaigns/{baseline['campaign_id']}/baseline-study", json={'execute_live': True})
        assert queued.status_code == 202, queued.text
        await c.tasks[queued.json()['study_id']]
        study = (await api.get('/api/baseline-studies/' + queued.json()['study_id'])).json()
        b0 = [t for t in study['trials'] if t['arm'] == 'B0']
        adapters = {c.store.get_record('episode_executions', t['episode_id'])['adapter_entrypoint_id'] for t in b0}
        tokens = [report_events(c.store, t['episode_id'])[0]['payload'].get('cited_evidence_tokens') for t in b0 if report_events(c.store, t['episode_id'])]
        out['baseline_study'] = {'status': study['status'], 'trials': len(study['trials']), 'b0': len(b0),
            'b0_adapters': sorted(adapters), 'b0_outcomes': sorted({t['outcome'] for t in b0}),
            'b0_evidence': sorted(set(study['evidence'].values())), 'b0_reports_with_label_tokens': sum(1 for t in tokens if t and all(str(x).startswith('obs-') for x in t)),
            'charged_model_calls': study.get('charged_model_calls'), 'b1_model_calls': study['by_arm']['B1']['usage']['model_calls']}
        assert study['status'] == 'COMPLETED' and adapters == {NATIVE_V2}

        options = (await api.get('/api/run-options')).json()
        v2_learn = await plan_via_api(api, options, registration_id=v2['registration_id'], mode='learn', protocol='faultlab-discovery/v3-history')
        v1_learn = await plan_via_api(api, options, registration_id=v1['registration_id'], mode='learn', protocol='faultlab-discovery/v3-history')
        assert v2_learn.status_code == v1_learn.status_code == 201, (v2_learn.text, v1_learn.text)
        v2_hist = (await api.get(f"/api/campaigns/{v2_learn.json()['campaign_id']}/plan")).json()['plan']['discovery']['history']
        v1_hist = (await api.get(f"/api/campaigns/{v1_learn.json()['campaign_id']}/plan")).json()['plan']['discovery']['history']
        out['histories'] = {
            'v2': {'status': v2_hist['status'], 'verified_episodes': v2_hist['summary']['verified_episodes'],
                   'agent': v2_hist['summary']['agent'], 'builds': v2_hist['summary']['builds'],
                   'episode_ids_hash_matches_study_b0': v2_hist['episode_ids_hash'] == content_hash(sorted(t['episode_id'] for t in b0)),
                   'recipes': [(r['development_case_id'], r['verified_episodes'], r['outcomes']) for r in v2_hist['summary']['recipes']]},
            'v1': {'status': v1_hist['status'], 'verified_episodes': v1_hist['summary']['verified_episodes'], 'agent': v1_hist['summary']['agent']}}
        assert v2_hist['summary']['verified_episodes'] == 18 and v1_hist['status'] == 'NO_PRIOR_HISTORY'
        assert v2_hist['summary']['builds'][0]['adapter_hash'] == adapter_hash(NATIVE_V2)[:12]

        # Start the v2 v3 Learn campaign: the frozen v2 history must reach every Explorer request.
        explorer_contexts = []
        async def spy(messages, *, role='actor', **kwargs):
            if role == 'actor':
                return await PricedNativeInputs.complete(provider, messages, role=role, **kwargs)
            # Explorer / Mechanic: the repository's scripted loop answers, returned as the frozen reasoning model
            # (PricedNativeInputs relabels every answer as the actor model, which is a fixture limit, not product).
            if role == 'explorer': explorer_contexts.append(json.loads(messages[-1]['content']))
            return await NativeReferenceInputs.complete(provider, messages, role=role, **kwargs)
        provider.complete = spy
        learn_id = v2_learn.json()['campaign_id']
        started = await api.post(f'/api/campaigns/{learn_id}/start', json={})
        assert started.status_code == 202, started.text
        await asyncio.wait_for(c.tasks[learn_id], timeout=300)
        final = c.get(learn_id)
        learn_eps = c.store.list_campaign_episodes(learn_id)
        errors = [e for e in c.store.list_records('execution_errors') if e.get('campaign_id') == learn_id]
        discovery = [ctx for ctx in explorer_contexts if 'agent_history' in ctx]
        out['v3_learn_start'] = {'state': final.state, 'terminal_reason': final.terminal_reason,
            'explorer_requests': len(explorer_contexts), 'explorer_requests_with_history': len(discovery),
            'every_discovery_request_shows_exactly_the_frozen_v2_summary': bool(discovery) and all(
                ctx['agent_history'] == v2_hist['summary'] for ctx in discovery),
            'episode_purposes': sorted({e['experiment_purpose'] for e in learn_eps}),
            'episode_adapters': sorted({(c.store.get_record('episode_executions', e['episode_id']) or {}).get('adapter_entrypoint_id') for e in learn_eps}),
            'qualification': [q['decision'] for q in c.store.list_records('candidate_qualifications')],
            'execution_errors': [{k: e.get(k) for k in ('code', 'error_class', 'message', 'locations')} for e in errors[:3]]}
        assert discovery and all(ctx['agent_history'] == v2_hist['summary'] for ctx in discovery)
    finally:
        record('3_baseline_study_history_learn', out)
        await api.aclose(); await world.aclose(); await c.close()


# ============================================================================ 4. v2 original Learn loop with Stop, rejection, acceptance, compare

def _planned(c, agent, mode, protocol=None):
    registration = register_agent(c.store, c.settings, agent)
    options = build_run_options(c.settings, c.store)
    request = RunPlanRequest(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'],
        task_definition_id=TASK, agent_registration_id=registration.registration_id, mode=mode, config_profile_id='live-v1',
        task_text=options['task']['task_text_default'], order_id='order-selected', discovery_protocol=protocol)
    prepared = prepare_run_plan(c.store, c.settings, request)
    return c.create(prepared.campaign_request, run_plan=prepared), registration


@pytest.mark.anyio
@pytest.mark.localhost_http
@pytest.mark.parametrize('mode', ['accepted', 'rejected', 'interrupted'])
async def test_4_v2_learn_loop_stop_reject_accept_and_compare(tmp_path, mode):
    """The repository's own native Learn-loop fixture, with the campaign's agent chosen as adapter v2."""
    settings = fixture_settings(tmp_path / 'lab')
    provider = NativeReferenceInputs(mode)
    out = {'mode': mode}
    with localhost_simulator(tmp_path, settings) as url:
        c = LabCoordinator(settings)
        c.runner = OfflineRunner(c.store, WorldClient(url, CONTROL), provider, offline_fixture=True)
        c.policies = ManualPolicies(c.store)
        c.evidence_gateway = OfflineEvidence(c.store, 'offline-fixture/native-v2-loop')
        campaign, registration = _planned(c, 'smolagents-v2', 'learn')
        try:
            await c.start(campaign.campaign_id)
            if mode == 'interrupted':
                await asyncio.wait_for(provider.pause_after_write.wait(), timeout=15)
                await c.stop(campaign.campaign_id)
                provider.release.set()
            await asyncio.wait_for(c.tasks[campaign.campaign_id], timeout=240)
            current = c.get(campaign.campaign_id)
            rows = c.store.list_campaign_episodes(campaign.campaign_id)
            adapters = {c.store.get_record('episode_executions', e['episode_id'])['adapter_entrypoint_id'] for e in rows}
            out.update(state=current.state, terminal_reason=current.terminal_reason, active_policy=current.active_policy_version,
                       episodes=len(rows), lifecycles=sorted({e['lifecycle'] for e in rows}), adapters=sorted(adapters),
                       purposes=sorted({e['experiment_purpose'] for e in rows}),
                       registrations=sorted({e['agent_registration_id'] for e in rows}),
                       qualification=[q['decision'] for q in c.store.list_records('candidate_qualifications')],
                       execution_errors=[{k: e.get(k) for k in ('code', 'error_class', 'message')} for e in c.store.list_records('execution_errors')][:3])
            assert adapters <= {NATIVE_V2} and {e['agent_registration_id'] for e in rows} == {registration.registration_id}
            if mode == 'interrupted':
                assert current.state == 'STOPPED' and rows[-1]['lifecycle'] == 'INTERRUPTED'
            elif mode == 'rejected':
                assert current.state == 'NO_CHANGE' and current.active_policy_version == 'policy-v0'
            else:
                assert current.state == 'COMPLETED', out
                compared, _ = _planned(c, 'smolagents-v2', 'compare')
                await c.start(compared.campaign_id)
                await asyncio.wait_for(c.tasks[compared.campaign_id], timeout=120)
                out['compare_state'] = c.get(compared.campaign_id).state
                out['compare_adapters'] = sorted({c.store.get_record('episode_executions', e['episode_id'])['adapter_entrypoint_id']
                                                  for e in c.store.list_campaign_episodes(compared.campaign_id)})
                # An accepted v2 policy is v2's alone: v1's registration has a different configuration hash.
                v1 = register_agent(c.store, c.settings, 'smolagents')
                options = build_run_options(c.settings, c.store)
                out['accepted_policy_visible_to'] = {row['agent']: row['accepted_policy_version'] for row in options['agents']}
                assert c.store.get_pointer('accepted-policy:' + v1.configuration_hash) is None
        finally:
            await c.runner.world_client.close()
            await c.close()
    record(f'4_learn_loop_{mode}', out)


# ============================================================================ 5. evidence retry for a v2 episode

class FlakyRemote:
    """In-memory Weave double (no network): uploads succeed; readback fails until `ready` is set."""
    def __init__(self): self.calls = {}; self.ready = False; self.reads = 0
    async def start(self): return None
    async def close(self): return None
    async def request(self, operation, payload, **kwargs):
        if operation == 'start_call':
            parent = payload.get('parent_id')
            self.calls[payload['call_id']] = {'id': payload['call_id'], 'project_id': 'entity/project', 'attributes': payload['metadata'],
                'inputs': payload['inputs'], 'parent_id': parent, 'trace_id': self.calls[parent]['trace_id'] if parent in self.calls else payload['call_id'],
                'output': None, 'ended_at': None}
            return {'id': payload['call_id']}
        if operation == 'finish_call':
            self.calls[payload['call_id']]['output'] = payload['output']; self.calls[payload['call_id']]['ended_at'] = '2026-09-29T00:00:00Z'; return {}
        if operation == 'get_calls':
            self.reads += 1
            if not self.ready: raise TimeoutError('fixture outage')
            return [self.calls[i] for i in payload['call_ids'] if i in self.calls]
        return {}


@pytest.mark.anyio
async def test_5_evidence_retry_verifies_a_v2_episode_without_rerunning_it(tmp_path, monkeypatch):
    from app.lab.evidence import EvidenceContext, EvidenceGateway, WaitingEvidence
    from app.lab.runner import EpisodeRunner
    from app.telemetry.outbox import TelemetryOutbox
    from app.telemetry.tracing import TraceRecorder
    from test_native_baseline_study_planned import PricedNativeInputs, plan_settings
    settings = plan_settings(tmp_path / 'lab')
    c = LabCoordinator(settings)
    simulator = simulator_app(database_dir=tmp_path / 'worlds', control_token=CONTROL, settings=settings)
    world = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    remote = FlakyRemote(); trace = TraceRecorder(remote, TelemetryOutbox(c.store))
    provider = PricedNativeInputs('accepted')
    c.runner = EpisodeRunner(c.store, WorldClient('http://127.0.0.1:8001', CONTROL, client=world), provider, trace=trace)
    gateway = EvidenceGateway(c.store, 'entity/project', trace=trace, worker=remote)
    out = {}
    try:
        registration = register_agent(c.store, c.settings, 'smolagents-v2')
        options = build_run_options(c.settings, c.store)
        request = RunPlanRequest(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'],
            task_definition_id=TASK, agent_registration_id=registration.registration_id, mode='baseline', config_profile_id='live-v1',
            task_text=options['task']['task_text_default'], order_id='order-evidence', development_case_id='dev-1')
        prepared = prepare_run_plan(c.store, c.settings, request)
        campaign = c.create(prepared.campaign_request, run_plan=prepared)
        trial = await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline())
        episode = c.store.get_record('episodes', trial.episode_id)
        context = EvidenceContext(episode['campaign_id'], episode['study_id'], episode['evidence_context_id'], episode.get('selector_id'))
        with pytest.raises(WaitingEvidence):
            await gateway.get(trial.episode_id, context)
        calls_before = sum(provider.calls.values())
        remote.ready = True
        async def services(): return remote, gateway, None
        monkeypatch.setattr(c, '_evidence_retry_services', services)
        job = await c.retry_evidence(campaign.campaign_id, [trial.episode_id])
        await c.tasks[job['request_id']]
        result = c.store.get_record('evidence_retries', job['request_id'])
        evidence = c.store.get_record('evidence', trial.episode_id)
        out = {'episode_adapter': c.store.get_record('episode_executions', trial.episode_id)['adapter_entrypoint_id'],
               'episode_source_mode': episode['source_mode'], 'first_read': 'WaitingEvidence (fixture outage)',
               'retry_status': result['status'], 'retry_outcome': result['outcomes'][trial.episode_id],
               'evidence_source': evidence['source'], 'evidence_report_equals_decoded_report': evidence['report'] == episode['report'],
               'model_calls_during_retry': sum(provider.calls.values()) - calls_before}
        assert result['outcomes'][trial.episode_id]['status'] == 'VERIFIED' and evidence['source'] == 'weave_verified'
        assert sum(provider.calls.values()) == calls_before
    finally:
        record('5_evidence_retry', out)
        await world.aclose(); await c.close()


# ============================================================================ 6. runtime behaviour in scripted episodes

def _model_view(request):
    return json.dumps(request['messages'], ensure_ascii=False)


def test_6a_step_alignment_final_turn_and_no_ninth_request(tmp_path, monkeypatch):
    out = {}
    for label, actor in (('v1', SmolagentsActor), ('v2', SmolagentsActorV2)):
        provider, outcome, context, store = episode(tmp_path / label, actor, SCRIPTS['no_report'], name='review-no-report', monkeypatch=monkeypatch)
        flags = [transport(r)['final_report_required'] for r in provider.requests]
        last = provider.requests[-1]
        out[label] = {'requests': len(provider.requests), 'final_flags': flags, 'actor_calls': context.broker.meter.usage.actor_calls,
                      'model_calls': context.broker.meter.usage.model_calls, 'last_tools': [t['name'] for t in transport(last)['tools']],
                      'last_kwargs': last['kwargs'], 'outcome': outcome,
                      'report_events': len(adapter_events(store, context, 'report_submitted'))}
    assert out['v1']['requests'] == out['v2']['requests'] == 8
    assert out['v2']['final_flags'] == [False] * 7 + [True] and out['v2']['last_tools'] == ['final_answer']
    assert out['v2']['last_kwargs'].get('response_contract') == 'native_final_answer'
    assert out['v1']['model_calls'] == out['v2']['model_calls'] == 8
    record('6a_step_alignment', out)


@pytest.mark.parametrize('final_output', [
    'not json at all',
    {'name': 'final_answer', 'arguments': {'answer': {'overall': 'COMPLETED'}}},
    {'name': 'final_answer', 'arguments': {'answer': {}, 'extra': 1}},
    {'name': 'get_operation_status', 'arguments': {'service': 'orders'}},
    {'name': 'final_answer', 'arguments': {'answer': 'obs-1'}},
], ids=['non_json', 'schema_invalid_report', 'extra_argument', 'business_call_on_final_turn', 'answer_not_object'])
def test_6b_malformed_or_forbidden_final_turn_output_is_refused_not_repaired(tmp_path, monkeypatch, final_output):
    def script(call, messages):
        if call < 8: return {'name': 'get_operation_status', 'arguments': {'service': 'orders'}}
        return final_output
    out = {}
    for label, actor in (('v1', SmolagentsActor), ('v2', SmolagentsActorV2)):
        provider, outcome, context, store = episode(tmp_path / label, actor, script, name='review-final', monkeypatch=monkeypatch)
        out[label] = {'requests': len(provider.requests), 'outcome': outcome, 'http_attempts': context.broker.meter.usage.http_attempts,
                      'report_events': len(adapter_events(store, context, 'report_submitted'))}
    record(f'6b_final_turn_{final_output if isinstance(final_output, str) else final_output["name"] + "_" + str(len(json.dumps(final_output)))}', out)
    assert out['v2']['requests'] == 8 and out['v2']['report_events'] == 0
    assert out['v2']['http_attempts'] == out['v1']['http_attempts'] == 7
    assert out['v2']['outcome'].get('error') == out['v1']['outcome'].get('error')


def test_6c_valid_report_on_the_final_turn_is_decoded_and_recorded_as_final(tmp_path, monkeypatch):
    def script(call, messages):
        if call < 8: return {'name': 'get_operation_status', 'arguments': {'service': 'orders'}}
        return report_citing(shown_evidence_ids(messages)[:2], outcome='UNKNOWN') | {}
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, name='review-final-ok', monkeypatch=monkeypatch)
    submitted = adapter_events(store, context, 'report_submitted')
    out = {'outcome': outcome, 'requests': len(provider.requests)}
    if submitted:
        p = submitted[0]['payload']
        out.update(cited=p['cited_evidence_tokens'], decoded_real=all(x.startswith('evidence-') for x in p['decoded_evidence_ids']),
                   final_report_required=p['final_report_required'], response_contract=p['response_contract'],
                   labels_shown=p['labels_shown_to_agent'][:10], tick=submitted[0]['tick'])
    record('6c_final_turn_valid_report', out)
    assert submitted and submitted[0]['payload']['final_report_required'] is True


@pytest.mark.anyio
async def test_6d_label_gap_when_the_broker_retries_a_failed_write(tmp_path):
    """dev-6's fault (two transient confirmation failures): the broker retries once inside one tool call."""
    c = await runtime(tmp_path)
    out = {}
    try:
        registration = register_agent(c.store, c.settings, 'smolagents-v2')
        options = build_run_options(c.settings, c.store)
        request = RunPlanRequest(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'],
            task_definition_id=TASK, agent_registration_id=registration.registration_id, mode='baseline', config_profile_id='live-v1',
            task_text=options['task']['task_text_default'], order_id='order-gap', development_case_id='dev-6')
        prepared = prepare_run_plan(c.store, c.settings, request)
        campaign = c.create(prepared.campaign_request, run_plan=prepared)
        recipe = FaultSpec.model_validate_json(canonical_json(prepared.plan['selection']['fault_spec']))
        trial = await c.runner.run(campaign, recipe, c.policies.baseline())
        submitted, = report_events(c.store, trial.episode_id)
        p = submitted['payload']
        journal = [e['payload']['observation'] for e in c.store.events(trial.episode_id)['events'] if e['type'] == 'observation_delivered']
        out = {'recipe': prepared.plan['selection']['fault_spec'], 'journal_observations': len(journal),
               'journal_tools_and_errors': [(o['result']['tool'], o['result'].get('error_code')) for o in journal],
               'labels_shown_to_agent': p['labels_shown_to_agent'], 'cited': p['cited_evidence_tokens'],
               'all_labels': sorted(p['evidence_labels'].values(), key=lambda s: int(s.split('-')[1])),
               'outcome': trial.outcome, 'failed_checks': trial.failed_checks}
    finally:
        record('6d_label_gap_broker_retry', out)
        await c.close()


class CitesUnseenLabel(NativeReferenceInputs):
    """The repository's scripted native answers, except the final report cites obs-1..obs-4 (a plain sequential list)."""
    async def complete(self, messages, *, role='actor', **kwargs):
        generation = await super().complete(messages, role=role, **kwargs)
        value = json.loads(generation.content)
        if role == 'actor' and value.get('name') == 'final_answer':
            value['arguments']['answer']['evidence_ids'] = ['obs-1', 'obs-2', 'obs-3', 'obs-4']
            return RuntimeGeneration(canonical_json(value), generation.model_id, cost_usd=0.0)
        return generation


@pytest.mark.anyio
async def test_6f_a_label_never_shown_to_the_agent_still_decodes(tmp_path):
    """dev-6: obs-3 (the broker's first, internally retried confirmation attempt) is never shown; cite it anyway."""
    c = await runtime(tmp_path, provider=CitesUnseenLabel('accepted'))
    out = {}
    try:
        registration = register_agent(c.store, c.settings, 'smolagents-v2')
        options = build_run_options(c.settings, c.store)
        request = RunPlanRequest(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'],
            task_definition_id=TASK, agent_registration_id=registration.registration_id, mode='baseline', config_profile_id='live-v1',
            task_text=options['task']['task_text_default'], order_id='order-unseen', development_case_id='dev-6')
        prepared = prepare_run_plan(c.store, c.settings, request)
        campaign = c.create(prepared.campaign_request, run_plan=prepared)
        recipe = FaultSpec.model_validate_json(canonical_json(prepared.plan['selection']['fault_spec']))
        trial = await c.runner.run(campaign, recipe, c.policies.baseline())
        submitted, = report_events(c.store, trial.episode_id)
        p = submitted['payload']
        labels = p['evidence_labels']; reverse = {v: k for k, v in labels.items()}
        episode = c.store.get_record('episodes', trial.episode_id)
        out = {'labels_shown_to_agent': p['labels_shown_to_agent'], 'cited': p['cited_evidence_tokens'],
               'obs_3_decoded_to_real_id': reverse.get('obs-3') in p['decoded_evidence_ids'],
               'episode_report_cites_unseen_observation': reverse.get('obs-3') in episode['report']['evidence_ids'],
               'outcome': trial.outcome, 'failed_checks': trial.failed_checks,
               'checks': {ch['check_id']: ch['passed'] for ch in (episode.get('verdict') or {}).get('checks', [])}}
    finally:
        record('6f_unseen_label_decodes', out)
        await c.close()


@pytest.mark.parametrize('actor_class', [SmolagentsActor, SmolagentsActorV2], ids=['v1', 'v2'])
def test_6e_provider_identity_mismatch_is_a_lab_failure_in_both(tmp_path, monkeypatch, actor_class):
    provider, outcome, context, store = episode(tmp_path, actor_class, SCRIPTS['success'], model='some/other-model', monkeypatch=monkeypatch)
    failures = store.list_records('provider_failures')
    record(f'6e_identity_mismatch_{actor_class.__name__}', {'outcome': outcome, 'requests': len(provider.requests),
           'provider_failures': len(failures), 'cost_dollars': context.broker.meter.usage.cost_dollars})
    assert outcome['error'] == 'RuntimeProviderError' and len(provider.requests) == 1 and len(failures) == 1


# ============================================================================ 7. recording, export, drift check, portability

@pytest.mark.anyio
async def test_7_recording_drift_check_and_portability_refusal(tmp_path):
    c = await runtime(tmp_path)
    out = {}
    try:
        campaign, v2 = _planned(c, 'smolagents-v2', 'learn')
        trial = await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline())
        from app.lab.exports import development_recording
        recording = development_recording(c.store, campaign.campaign_id)
        text = json.dumps(recording)
        out['recording'] = {'contains_report_submitted': 'report_submitted' in text, 'contains_cited_tokens': 'cited_evidence_tokens' in text,
                            'contains_adapter_v2': NATIVE_V2 in text}
        store_path = str(c.store.path)
        v1 = register_agent(c.store, c.settings, 'smolagents')
        from app.integrations.portability import require_independent_target
        try:
            require_independent_target(AgentRegistry(c.store).get(v1.registration_id), v2)
            out['portability_v1_to_v2'] = 'ALLOWED'
        except ValueError as error:
            out['portability_v1_to_v2'] = str(error)
    finally:
        await c.close()
    worlds = str(tmp_path / 'worlds')
    for script in ('check_clock_drift_native.py', 'check_clock_drift.py'):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/experiments' / script), '--store', store_path, '--worlds', '--worlds-dir', worlds],
                                capture_output=True, text=True, cwd=str(ROOT), timeout=120,
                                env={**os.environ, 'PYTHON_DOTENV_DISABLED': '1'})
        out[script] = {'exit': result.returncode, 'stdout': result.stdout.strip().splitlines()[:12], 'stderr': result.stderr.strip()[-300:]}
    record('7_recording_drift_portability', out)
    assert out['check_clock_drift_native.py']['exit'] == 0
    assert out['portability_v1_to_v2'] != 'ALLOWED'


@pytest.mark.anyio
async def test_7b_v2_bundle_import_targets_stale_refusal_and_cross_adapter_rerun(tmp_path, monkeypatch):
    """A regression bundle exported from a v2 episode, imported into a fresh store: what the operator can rerun it on."""
    from app.contracts.models import Counterexample
    from app.lab import bundle_imports as imports
    from app.lab.regressions import RegressionCompiler
    from app.integrations import registry as registry_module
    source = await runtime(tmp_path / 'source'); target = await runtime(tmp_path / 'target')
    out = {}
    try:
        campaign, _ = _planned(source, 'smolagents-v2', 'learn')
        recipe = FaultSpec(seed=0, primitives=[])
        trial = await source.runner.run(campaign, recipe, source.policies.baseline())
        counter = Counterexample(counterexample_id='counter-review-v2', campaign_id=campaign.campaign_id,
            agent_registration_id=source.store.get_record('episodes', trial.episode_id)['agent_registration_id'],
            source_episode_id=trial.episode_id, target_invariant='C3', scenario_hash=content_hash(recipe),
            configuration_hash=campaign.configuration_hash, report_ref=None, verdict_ref='verdict-review-v2')
        RegressionCompiler(source.store).compile(campaign, counter, source.policies.baseline(), recipe, None, [trial])
        regression = source.store.list_records('regressions')[0]
        async with api_client(source) as api:
            download = await api.get(f"/api/regressions/{regression['regression_id']}/download")
        v1 = register_agent(target.store, target.settings, 'smolagents')
        v2 = register_agent(target.store, target.settings, 'smolagents-v2')
        reference = register_agent(target.store, target.settings, 'reference')
        async with api_client(target) as api:
            uploaded = await api.post('/api/bundle-imports', content=download.content,
                headers={'content-type': 'application/zip', 'x-faultlab-store-identity': store_descriptor(target.store)['identity']})
        assert uploaded.status_code == 201, uploaded.text
        detail = uploaded.json()
        recorded = [e for e in detail['historical']['recording']['events'][trial.episode_id] if e['type'] == 'report_submitted']
        listed = {t['agent_registration_id']: t for t in imports.import_detail(target.store, target.settings, detail['import_id'])['targets']}
        out['recording_carries_v2'] = {'adapter_entrypoint_id': recorded[0]['payload'].get('adapter_entrypoint_id'),
                                       'cited': recorded[0]['payload'].get('cited_evidence_tokens')}
        out['targets_fresh'] = {t['agent']: [t['compatible'], t['reason']] for t in listed.values()}
        # Rerun the v2-origin bundle on the v1 target (a regression is a scenario, not tied to the source adapter).
        body = imports.ImportedExecutionRequest(expected_store_identity=store_descriptor(target.store)['identity'],
            expected_manifest_hash=detail['manifest_hash'], expected_target_configuration_hash=v1.configuration_hash,
            agent_registration_id=v1.registration_id, request_id='request-review-v1', execution_profile_id='sandbox-v1', execute_live=True)
        started = await imports.execute_import(target, detail['import_id'], body)
        await target.tasks[started['execution']['execution_id']]
        result = imports.request_view(target.store, detail['import_id'], body.request_id)
        out['rerun_on_v1_target'] = {'status': result['execution']['status'], 'target_agent': result['target']['agent']}
        # The v2 adapter module changes after registration: the v2 target becomes stale and is refused with a plain reason.
        real_digest = registry_module.digest
        monkeypatch.setattr(registry_module, 'digest', lambda path: ('e' * 64) if Path(path).name == 'external_agent_v2.py' else real_digest(path))
        listed = {t['agent_registration_id']: t for t in imports.import_detail(target.store, target.settings, detail['import_id'])['targets']}
        out['targets_after_v2_module_change'] = {t['agent']: [t['compatible'], t['reason']] for t in listed.values()}
        body = imports.ImportedExecutionRequest(expected_store_identity=store_descriptor(target.store)['identity'],
            expected_manifest_hash=detail['manifest_hash'], expected_target_configuration_hash=v2.configuration_hash,
            agent_registration_id=v2.registration_id, request_id='request-review-v2-stale', execution_profile_id='sandbox-v1', execute_live=True)
        try:
            await imports.execute_import(target, detail['import_id'], body); out['stale_v2_execute'] = 'ADMITTED'
        except Exception as error:
            out['stale_v2_execute'] = f'{type(error).__name__}: {error}'
        assert listed[v2.registration_id]['compatible'] is False and listed[v1.registration_id]['compatible'] is True
        assert out['stale_v2_execute'] != 'ADMITTED'
    finally:
        record('7b_bundle_import_v2', out)
        await source.close(); await target.close()


# ============================================================================ 8. failure modes

@pytest.mark.anyio
async def test_8a_v2_plan_opened_by_a_runtime_without_v2_simulated(tmp_path, monkeypatch):
    """Simulate the pre-v2 runtime's reading rules (agent kinds 'reference' and 'smolagents' only)."""
    from typing import Literal
    from pydantic import create_model
    from app.lab import run_plans
    from app.integrations import registry as registry_module
    c = await runtime(tmp_path)
    out = {}
    try:
        registration = register_agent(c.store, c.settings, 'smolagents-v2')
        options = build_run_options(c.settings, c.store)
        request = RunPlanRequest(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'],
            task_definition_id=TASK, agent_registration_id=registration.registration_id, mode='baseline', config_profile_id='live-v1',
            task_text=options['task']['task_text_default'], order_id='order-old-runtime', development_case_id='dev-1')
        prepared = prepare_run_plan(c.store, c.settings, request)
        campaign = c.create(prepared.campaign_request, run_plan=prepared)
        Old = create_model('SavedRunPlan', __base__=run_plans.SavedRunPlan, agent=(Literal['reference', 'smolagents'], ...))
        monkeypatch.setattr(run_plans, 'SavedRunPlan', Old)
        monkeypatch.setattr(registry_module, 'NATIVE_ENTRYPOINTS', (NATIVE_V1,))
        monkeypatch.setattr(registry_module, 'AGENT_ENTRYPOINTS', {'reference': 'orders-prototype-v1', 'smolagents': NATIVE_V1})
        async with api_client(c) as api:
            plan = await api.get(f'/api/campaigns/{campaign.campaign_id}/plan')
            start = await api.post(f'/api/campaigns/{campaign.campaign_id}/start', json={})
            campaigns = await api.get('/api/campaigns')
            regs = await api.get('/api/agent-registrations')
        try:
            AgentRegistry(c.store).verify(registration.registration_id, c.store.get_record('configurations', registration.configuration_hash))
            verify = 'accepted'
        except ValueError as error:
            verify = str(error)
        out = {'simulated': 'SavedRunPlan.agent narrowed to the pre-v2 literal; registry maps without v2',
               'GET plan': [plan.status_code, plan.json()], 'POST start': [start.status_code, start.json()],
               'GET campaigns': campaigns.status_code, 'GET agent-registrations': regs.status_code,
               'registry.verify(v2 registration)': verify, 'provider_calls': sum(c.runner.provider.calls.values())}
        assert start.status_code >= 400 and sum(c.runner.provider.calls.values()) == 0
    finally:
        record('8a_v2_plan_on_runtime_without_v2', out)
        await c.close()


@pytest.mark.anyio
async def test_8b_v1_registration_made_before_this_runtime_change(tmp_path, monkeypatch):
    """An old v1 registration: its frozen adapter_hash (and runtime hashes) no longer match the installed runtime."""
    c = await runtime(tmp_path)
    out = {}
    try:
        old = register_agent(c.store, c.settings, 'smolagents')
        options = build_run_options(c.settings, c.store)
        request = RunPlanRequest(expected_store_identity=options['data_store']['identity'], expected_setup_hash=options['setup_hash'],
            task_definition_id=TASK, agent_registration_id=old.registration_id, mode='baseline', config_profile_id='live-v1',
            task_text=options['task']['task_text_default'], order_id='order-old-v1', development_case_id='dev-1')
        prepared = prepare_run_plan(c.store, c.settings, request)
        idle = c.create(prepared.campaign_request, run_plan=prepared)
        # Now the runtime changes under the saved registration and the idle plan (as this v2 change did to v1).
        from app.integrations import registry as registry_module
        from app.lab import configuration as configuration_module
        real_digest = registry_module.digest
        monkeypatch.setattr(registry_module, 'digest', lambda path: ('f' * 64) if Path(path).name == 'registry.py' else real_digest(path))
        async with api_client(c) as api:
            options = (await api.get('/api/run-options')).json()
            row = next(r for r in options['agents'] if r['agent'] == 'smolagents')
            plan_new = await plan_via_api(api, options, registration_id=old.registration_id, mode='baseline', case='dev-1')
            start_old = await api.post(f'/api/campaigns/{idle.campaign_id}/start', json={})
            read_old = await api.get(f'/api/campaigns/{idle.campaign_id}/plan')
        out = {'dashboard_v1_row': {k: row[k] for k in ('status', 'registered', 'registration_id', 'proposed_registration_id', 'message')},
               'old_registration_id': old.registration_id,
               'new_plan_with_old_registration': [plan_new.status_code, plan_new.json()],
               'start_idle_plan_saved_under_old_runtime': [start_old.status_code, start_old.json()],
               'saved_plan_still_readable': [read_old.status_code, read_old.json().get('status')],
               'provider_calls': sum(c.runner.provider.calls.values())}
        assert row['registered'] is False and plan_new.status_code == 409 and start_old.status_code == 409
        assert read_old.status_code == 200
    finally:
        record('8b_old_v1_registration_after_runtime_change', out)
        await c.close()


SAVED_STORE = '/Users/shree/FaultLab_Runs/2026-09-29/native-learn-v3/lab.sqlite3'
SCRATCH = Path('/private/tmp/claude-501/-Users-shree-Desktop-Coreweave-AGI-Hackthon/31c46f2c-a976-45ff-91d4-1214cbd5c473/scratchpad')


@pytest.mark.anyio
@pytest.mark.skipif(not Path(SAVED_STORE).exists(), reason='saved native store not present')
async def test_8c_real_saved_v1_store_opened_by_this_runtime(tmp_path):
    """A copy of the real native-learn-v3 store (read with mode=ro&immutable=1; its WAL is empty), opened by this runtime."""
    import sqlite3
    work = SCRATCH / 'saved-store-copy'
    if work.exists():
        import shutil; shutil.rmtree(work)
    work.mkdir(parents=True)
    source = sqlite3.connect(f'file:{SAVED_STORE}?mode=ro&immutable=1', uri=True)
    target = sqlite3.connect(str(work / 'lab.sqlite3'))
    source.backup(target); target.close(); source.close()
    probe = sqlite3.connect(str(work / 'lab.sqlite3'))   # the private copy, not the saved store
    saved_configuration = json.loads(probe.execute("SELECT payload FROM records WHERE kind='configurations'").fetchone()[0])
    old = json.loads(probe.execute("SELECT payload FROM records WHERE kind='agent_registrations'").fetchone()[0])
    probe.close()
    models = saved_configuration.get('models') or {}
    settings = Settings(faultlab_artifact_dir=str(work), wandb_model=saved_configuration['model'],
                        wandb_explorer_model=models.get('explorer', ''), wandb_mechanic_model=models.get('mechanic', ''))
    c = LabCoordinator(settings)
    out = {'saved_registration': {k: old[k] for k in ('registration_id', 'adapter_entrypoint_id', 'model')},
           'saved_adapter_hash_prefix': old['adapter_hash'][:12], 'current_v1_adapter_hash_prefix': adapter_hash(NATIVE_V1)[:12],
           'saved_prompt_hash_equals_current_v1': old['prompt_hash'] == native_prompt_hash(NATIVE_V1)}
    try:
        registry = AgentRegistry(c.store)
        try:
            registry.verify(old['registration_id'], saved_configuration); out['old_registration_verify'] = 'accepted'
        except ValueError as error:
            out['old_registration_verify'] = str(error)
        async with api_client(c) as api:
            options = (await api.get('/api/run-options')).json()
            rows = {r['agent']: r for r in options['agents']}
            out['dashboard_rows'] = {k: {f: v[f] for f in ('status', 'registered', 'registration_id')} for k, v in rows.items()}
            stale = await plan_via_api(api, options, registration_id=old['registration_id'], mode='learn', protocol='faultlab-discovery/v3-history')
            out['plan_with_old_registration'] = [stale.status_code, stale.json().get('error', {}).get('message')]
            saved_plans = {}
            for campaign in (await api.get('/api/campaigns')).json()['campaigns']:
                plan = await api.get(f"/api/campaigns/{campaign['campaign_id']}/plan")
                recording = await api.get(f"/api/campaigns/{campaign['campaign_id']}/recording")
                saved_plans[campaign['campaign_id']] = {'mode': campaign['mode'], 'plan': [plan.status_code, plan.json().get('status')],
                                                        'recording': recording.status_code}
            out['saved_campaigns_readable'] = saved_plans
            identity = options['data_store']['identity']
            v1 = (await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents'})).json()
            v2 = (await api.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents-v2'})).json()
            options = (await api.get('/api/run-options')).json()
            histories = {}
            for label, reg in (('v1_reregistered', v1), ('v2', v2)):
                made = await plan_via_api(api, options, registration_id=reg['registration_id'], mode='learn', protocol='faultlab-discovery/v3-history')
                assert made.status_code == 201, made.text
                h = (await api.get(f"/api/campaigns/{made.json()['campaign_id']}/plan")).json()['plan']['discovery']['history']
                histories[label] = {'status': h['status'], 'verified_episodes': h['summary']['verified_episodes'],
                                    'agent': h['summary']['agent'], 'composition': h['summary']['composition'],
                                    'builds': h['summary']['builds'], 'excluded': h['summary']['excluded']}
            out['histories'] = histories
        assert histories['v2']['status'] == 'NO_PRIOR_HISTORY'
        assert histories['v1_reregistered']['verified_episodes'] > 0
    finally:
        record('8c_real_saved_v1_store', out)
        await c.close()


# ============================================================================ 9. frozen identities and v1 pins, recomputed by the reviewer

def test_9_frozen_identities_and_v1_pins():
    configuration = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
    import hashlib
    v1_module = hashlib.sha256((ROOT / 'backend/app/integrations/external_agent.py').read_bytes()).hexdigest()
    out = {'service_hash': configuration['service_hash'][:8], 'contract_hash': configuration['contract_hash'][:8],
           'interpreter_hash': configuration['interpreter_hash'][:8], 'scorer_hash': configuration['scorer_hash'][:8],
           'v1_native_prompt_hash': native_prompt_hash(NATIVE_V1), 'v2_native_prompt_hash': native_prompt_hash(NATIVE_V2),
           'v1_adapter_hash': adapter_hash(NATIVE_V1), 'v2_adapter_hash': adapter_hash(NATIVE_V2),
           'external_agent_py_sha256': v1_module}
    record('9_identities', out)
    assert (out['service_hash'], out['contract_hash'], out['interpreter_hash']) == ('3ce5bcd2', '6f9d7783', '6da0714a')
    assert out['v1_native_prompt_hash'] == '2251542869cf3e0fb841e536f56c8d2780f77e852d91ae30e12d4edf3e4c4989'
    assert v1_module == '6c0909bfff3753b470570baef5c96b39904a922ea7a8f9d548fb30f5be9380f7'
