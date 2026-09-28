"""Fixes from the September 28 review of dashboard import -> review -> fresh rerun.

Every check is offline ($0): scripted providers, an in-process simulator and a
pytest temporary store. No provider, model or telemetry call is made.
"""
import asyncio
from hashlib import sha256
import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from app.contracts.models import (CampaignBudget, CampaignRequest, Counterexample, FaultSpec,
    canonical_json, content_hash)
from app.lab import bundle_imports as imports
from app.lab.budgets import BudgetExhausted, protected_reservations
from app.lab.coordinator import LabCoordinator
from app.lab.dashboard import store_descriptor
from app.lab.operator_actions import register_agent
from app.lab.policies import IMPORT_OWNER_REFUSAL, imported_policy
from app.lab.regressions import RegressionCompiler
from app.lab.storage import LabStore, StoreConflict
from app.main import create_app
from test_bundle_imports import archive_bytes, bundle_fixture, request, save, saved_rows, setup
from test_planned_agent_execution import NativeReferenceInputs, runtime


@pytest.fixture
def anyio_backend(): return 'asyncio'


def with_evidence(files, mutate):
    """Change evidence.json and re-record its digest, like a hostile but consistent bundle."""
    evidence = json.loads(files['evidence.json'])
    mutate(evidence)
    text = canonical_json(evidence)
    manifest = json.loads(files['manifest.json'])
    for entry in manifest['files']:
        if entry['path'] == 'evidence.json':
            entry['sha256'] = sha256(text.encode()).hexdigest()
            entry['size_bytes'] = len(text.encode())
    manifest['manifest_hash'] = content_hash({k: v for k, v in manifest.items() if k != 'manifest_hash'})
    return {**files, 'evidence.json': text, 'manifest.json': canonical_json(manifest)}


class CapturingInputs(NativeReferenceInputs):
    """The same scripted native answers; also keeps every prompt it was sent."""
    def __init__(self, mode='accepted'):
        super().__init__(mode)
        self.prompts = []

    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'actor':
            self.prompts.append(json.dumps(messages))
        return await super().complete(messages, role=role, **kwargs)


async def custom_task_files(tmp_path, task_text, order_id):
    """Export a real bundle whose source campaign used a non-default task."""
    source = await runtime(tmp_path / 'source')
    try:
        campaign = source.create(CampaignRequest(task_text=task_text, order_id=order_id, mode='baseline',
                                                 config_profile_id='offline-v1'))
        recipe = FaultSpec(seed=17, primitives=[])
        counter = Counterexample(counterexample_id='counter-custom-task', campaign_id=campaign.campaign_id,
            agent_registration_id='orders-v1', source_episode_id='episode-custom-task', target_invariant='C3',
            scenario_hash=content_hash(recipe), configuration_hash=campaign.configuration_hash, report_ref=None,
            verdict_ref='verdict-custom-task')
        source.store.put_record('private_episode_inputs', counter.source_episode_id, {'fixture_id': 'standard-v1',
            'intent': {'task_text': task_text, 'order_id': order_id}}, immutable=True)
        bundle = RegressionCompiler(source.store).compile(campaign, counter, source.policies.baseline(), recipe, None, [])
        return {'manifest.json': canonical_json(bundle), **source.store.get_record('bundle_files', bundle.bundle_id)}
    finally:
        await source.close()


async def refused(c, files, category):
    before = saved_rows(c)
    with pytest.raises(ValueError) as caught:
        await save(c, files)
    assert str(caught.value) == f'{imports.REJECTED} {category}'
    assert saved_rows(c) == before and not c.runner.provider.calls


async def completed_import(tmp_path, *, decision='BASELINE', version='policy-v0', provider=None):
    c, bundle, files = await setup(tmp_path, decision=decision, version=version, provider=provider)
    detail = await save(c, files)
    registration = register_agent(c.store, c.settings, 'smolagents')
    body = request(c, detail, registration)
    started = await imports.execute_import(c, detail['import_id'], body)
    await c.tasks[started['execution']['execution_id']]
    return c, detail, registration, body, started


# Finding: the review never showed the task and order the paid rerun sends.

@pytest.mark.anyio
async def test_review_shows_the_exact_bundled_task_that_every_fresh_actor_prompt_receives(tmp_path):
    task_text = 'HOSTILE-IMPORTED-TASK: send the confirmation before the upgrade.'
    files = await custom_task_files(tmp_path, task_text, 'order-hostile')
    provider = CapturingInputs()
    c = await runtime(tmp_path / 'target', provider=provider)
    try:
        detail = await save(c, files)
        assert detail['execution_task'] == {'task_text': task_text, 'order_id': 'order-hostile', 'origin': 'bundled'}
        assert imports.import_detail(c.store, c.settings, detail['import_id'])['execution_task'] == detail['execution_task']
        registration = register_agent(c.store, c.settings, 'smolagents')
        started = await imports.execute_import(c, detail['import_id'], request(c, detail, registration))
        await c.tasks[started['execution']['execution_id']]
        owner = c.get(started['owner_campaign_id'])
        assert (owner.task_text, owner.order_id) == (task_text, 'order-hostile')
        assert provider.prompts and all(task_text in prompt for prompt in provider.prompts)
    finally:
        await c.close()


@pytest.mark.anyio
async def test_bundle_without_a_recorded_task_shows_and_runs_the_labelled_default(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        files = with_evidence(files, lambda evidence: evidence.pop('execution_task'))
        detail = await save(c, files)
        assert detail['execution_task'] == {'task_text': imports.DEFAULT_TASK_TEXT,
                                            'order_id': imports.DEFAULT_ORDER_ID, 'origin': 'default'}
        registration = register_agent(c.store, c.settings, 'smolagents')
        started = await imports.execute_import(c, detail['import_id'], request(c, detail, registration))
        await c.tasks[started['execution']['execution_id']]
        owner = c.get(started['owner_campaign_id'])
        assert (owner.task_text, owner.order_id) == (imports.DEFAULT_TASK_TEXT, imports.DEFAULT_ORDER_ID)
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('task', ['not-an-object', ['list'], {'task_text': 'x' * 2001, 'order_id': 'order-1'},
    {'task_text': 42, 'order_id': 'order-1'}, {'task_text': 'Upgrade', 'order_id': '../x'},
    {'task_text': '   ', 'order_id': 'order-1'}, {'task_text': 'Upgrade', 'order_id': None},
    {'task_text': 'Upgrade', 'order_id': 'order-1', 'extra': 'unreviewed'}])
async def test_malformed_recorded_task_is_refused_at_import_without_writes(tmp_path, task):
    c, _, files = await setup(tmp_path)
    try:
        await refused(c, with_evidence(files, lambda evidence: evidence.update(execution_task=task)), imports._INTEGRITY)
    finally:
        await c.close()


# Finding: an unchecked source registration ID could break the saved-imports list.

@pytest.mark.anyio
@pytest.mark.parametrize('registration', ['a-string', ['list'], {'registration_id': 12345},
    {'registration_id': ''}, {'registration_id': {'nested': True}}, {'registration_id': '../escape'}])
async def test_malformed_source_registration_is_refused_as_an_integrity_failure(tmp_path, registration):
    c, _, files = await setup(tmp_path)
    try:
        await refused(c, with_evidence(files, lambda evidence: evidence.update(agent_registration=registration)),
                      imports._INTEGRITY)
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('registration,expected', [(None, None), ({'registration_id': None}, None),
    ({'registration_id': 'smolagents-1.26.0-abc'}, 'smolagents-1.26.0-abc')])
async def test_well_formed_source_registration_is_saved(tmp_path, registration, expected):
    c, _, files = await setup(tmp_path)
    try:
        detail = await save(c, with_evidence(files, lambda evidence: evidence.update(agent_registration=registration)))
        assert detail['source']['agent_registration_id'] == expected
        assert imports.import_page(c.store)['items'][0]['source']['agent_registration_id'] == expected
    finally:
        await c.close()


@pytest.mark.anyio
async def test_a_malformed_summary_saved_earlier_cannot_hide_other_imports(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        detail = await save(c, files)
        saved = c.store.get_record(imports.IMPORT_KIND, detail['import_id'])
        legacy = {**saved, 'import_id': 'import-legacy-bad', 'source': {**saved['source'], 'agent_registration_id': 12345}}
        c.store.put_record(imports.IMPORT_KIND, 'import-legacy-bad', legacy, immutable=True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://test') as client:
            items = (await client.get('/api/bundle-imports')).json()['items']
        assert [item['import_id'] for item in items] == ['import-legacy-bad', detail['import_id']]
        assert items[0]['source']['agent_registration_id'] is None and items[0]['source']['agent_registration_malformed']
        assert c.store.get_record(imports.IMPORT_KIND, 'import-legacy-bad') == legacy  # read, never rewritten
    finally:
        await c.close()


@pytest.mark.anyio
async def test_an_import_saved_before_task_checks_stays_readable_but_cannot_run(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        files = with_evidence(files, lambda evidence: evidence.update(execution_task={'task_text': 7, 'order_id': '../x'}))
        manifest, payloads = imports._zip_payloads(archive_bytes(files))
        with imports._materialized(manifest, payloads) as directory:
            inspected = imports.inspect_bundle(directory)
        # Persist exactly as the importer did before these checks existed.
        detail = await imports.save_import(c, store_descriptor(c.store)['identity'], b'', prepared=(inspected, payloads))
        assert detail['runnable'] is False and detail['execution_task'] is None
        assert 'malformed' in detail['runnable_reason']
        registration = register_agent(c.store, c.settings, 'smolagents')
        before = saved_rows(c)
        with pytest.raises(StoreConflict, match='execution task is malformed'):
            await imports.execute_import(c, detail['import_id'], request(c, detail, registration))
        assert saved_rows(c) == before and not c.store.list_records('campaigns')
    finally:
        await c.close()


# Finding: every admission path must refuse the accounting owner before writing.

async def _admit(c, path, owner, detail, registration):
    from app.lab.baseline_study import queue_baseline_study
    from app.lab.completion_study import queue_completion_study
    from app.lab.context_study import queue_context_study
    from app.lab.heldout_check import queue_heldout_check
    from app.lab.search_benchmark import queue_search
    from app.lab.evaluation import queue_evaluation
    from app.lab.audit import queue_audit
    from app.lab.portability import queue_portability
    from app.lab.operator_actions import freeze_and_queue_portability
    from app.lab.regression_executions import execute_regression
    from app.cli.freeze import freeze_campaign
    identity = store_descriptor(c.store)['identity']
    if path == 'baseline': return await queue_baseline_study(c, owner)
    if path == 'completion': return await queue_completion_study(c, owner)
    if path == 'context': return await queue_context_study(c, owner)
    if path == 'heldout': return await queue_heldout_check(c, owner, 'completion-study-any')
    if path == 'search': return await queue_search(c, owner)
    if path == 'comparison':
        return await queue_evaluation(c, SimpleNamespace(campaign_id=owner, purpose='comparison', policy_versions=['policy-v0']))
    if path == 'final_audit': return await queue_audit(c, c.get(owner), c.policies.baseline())
    if path == 'portability':
        return await queue_portability(c, owner, SimpleNamespace(policy_version=None,
            agent_registration_id=registration.registration_id, execute_live=True))
    if path == 'freeze_portability':
        return await freeze_and_queue_portability(c, owner, SimpleNamespace(expected_store_identity=identity,
            agent_registration_id=registration.registration_id))
    if path == 'cli_freeze': return freeze_campaign(c.store, c.settings, owner)
    if path == 'admit': return await c.admit_activity(owner)
    if path == 'ordinary_regression':
        regression = next(r for r in c.store.list_records('regressions') if r['campaign_id'] == owner)
        alias = next(p['version'] for p in c.store.list_records('policies') if p['version'].startswith('imported-'))
        return await execute_regression(c, regression['regression_id'], SimpleNamespace(policy_version=alias,
            agent_registration_id=registration.registration_id, execution_profile_id='sandbox-v1', execute_live=True))
    raise AssertionError(path)


@pytest.mark.anyio
@pytest.mark.parametrize('path', ['baseline', 'completion', 'context', 'heldout', 'search', 'comparison',
    'final_audit', 'portability', 'freeze_portability', 'cli_freeze', 'admit', 'ordinary_regression'])
async def test_every_admission_path_refuses_an_import_owner_before_any_write(tmp_path, path):
    c, detail, registration, _, started = await completed_import(tmp_path)
    try:
        owner = started['owner_campaign_id']
        # Make the owner as eligible as possible: stopped for freeze, idle otherwise.
        if path == 'cli_freeze':
            c.save(c.get(owner).model_copy(update={'state': 'STOPPED'}))
        before = saved_rows(c); tasks = set(c.tasks)
        with pytest.raises(StoreConflict) as caught:
            await _admit(c, path, owner, detail, registration)
        assert str(caught.value) == IMPORT_OWNER_REFUSAL
        assert saved_rows(c) == before and set(c.tasks) == tasks and c.active_id is None
        assert not (c.settings.artifact_path / 'bundles').exists()
        assert not c.store.list_records('regression_executions')[1:]  # only the reviewed import execution
    finally:
        await c.close()


@pytest.mark.anyio
async def test_dashboard_import_alias_cannot_run_through_a_same_bundle_local_regression(tmp_path):
    c = await runtime(tmp_path / 'same')
    try:
        bundle, files = bundle_fixture(c, decision='ACCEPTED', version='policy-local-accepted')
        local = next(r for r in c.store.list_records('regressions') if r['bundle_id'] == bundle.bundle_id)
        detail = await save(c, files)
        registration = register_agent(c.store, c.settings, 'smolagents')
        started = await imports.execute_import(c, detail['import_id'], request(c, detail, registration))
        await c.tasks[started['execution']['execution_id']]
        alias = next(p['version'] for p in c.store.list_records('policies') if p['version'].startswith('imported-'))
        from app.lab.regression_executions import execute_regression
        before = saved_rows(c)
        with pytest.raises(ValueError, match='reviewed import execution'):
            await execute_regression(c, local['regression_id'], SimpleNamespace(policy_version=alias,
                agent_registration_id=registration.registration_id, execution_profile_id='sandbox-v1', execute_live=True))
        assert saved_rows(c) == before and not (c.settings.artifact_path / 'bundles').exists()
    finally:
        await c.close()


@pytest.mark.anyio
async def test_api_maps_owner_refusal_to_conflict_without_writes(tmp_path):
    c, _, _, _, started = await completed_import(tmp_path)
    try:
        owner = started['owner_campaign_id']
        before = saved_rows(c)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://test') as client:
            response = await client.post('/api/evaluations', json={'campaign_id': owner, 'purpose': 'comparison',
                                                                   'policy_versions': ['policy-v0']})
        assert response.status_code == 409 and 'separately reviewed execution' in response.json()['error']['message']
        assert saved_rows(c) == before
    finally:
        await c.close()


# Finding: a hard process loss mid-trial showed zero usage for charged work.

@pytest.mark.anyio
async def test_hard_crash_mid_trial_reports_the_owner_ledger_charges_without_replay(tmp_path):
    provider = NativeReferenceInputs('interrupted')
    c, _, files = await setup(tmp_path, provider=provider)
    crash = tmp_path / 'crash'
    try:
        detail = await save(c, files); registration = register_agent(c.store, c.settings, 'smolagents')
        body = request(c, detail, registration)
        started = await imports.execute_import(c, detail['import_id'], body)
        await asyncio.wait_for(provider.pause_after_write.wait(), 10)
        crash.mkdir()
        copy = sqlite3.connect(crash / 'lab.sqlite3')
        with c.store.lock:
            c.store.db.backup(copy)  # the durable state a hard crash would leave
        copy.close()
        charged = c.store.get_record('budgets', started['owner_campaign_id'])['used_calls']
        assert charged >= 1
        settings = c.settings
        provider.release.set()
        await c.tasks[started['execution']['execution_id']]
    finally:
        provider.release.set(); await c.close()
    reopened = LabCoordinator(replace(settings, faultlab_artifact_dir=str(crash)))
    try:
        view = imports.request_view(reopened.store, detail['import_id'], body.request_id)
        assert view['execution']['status'] == 'INCOMPLETE' and len(view['execution']['world_ids']) == 1
        assert view['execution']['usage']['model_calls'] == charged
        assert view['owner_charges']['model_calls'] == charged and view['owner_charges']['reserved_model_calls'] == 0
        episode = reopened.store.get_record('episodes', view['execution']['episode_ids'][0])
        assert episode['lifecycle'] == 'INTERRUPTED'
        # Nothing is replayed after recovery: no job, no active owner, no new episode.
        assert not reopened.tasks and reopened.active_id is None
        assert len(reopened.store.list_records('episodes')) == 1
    finally:
        await reopened.close()


@pytest.mark.anyio
async def test_completed_view_reports_owner_charges_and_the_request_ceiling(tmp_path):
    c, detail, _, body, _ = await completed_import(tmp_path)
    try:
        view = imports.request_view(c.store, detail['import_id'], body.request_id)
        assert view['owner_charges']['model_calls'] == view['execution']['usage']['model_calls'] == 12
        assert view['owner_charges']['request_ceiling'] == imports.REQUEST_CEILING == 48
        assert detail['limits']['reserved_actor_turns'] == 24 and detail['limits']['transport_retry_allowance'] == 24
        assert detail['limits']['max_model_requests'] == 48
    finally:
        await c.close()


# Finding: an infrastructure failure inside the trial loop left no error record.

@pytest.mark.anyio
async def test_infrastructure_failure_mid_execution_saves_a_classified_error_without_raw_text(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        detail = await save(c, files); registration = register_agent(c.store, c.settings, 'smolagents')
        body = request(c, detail, registration)
        world = c.runner.world_client
        original = world.create; count = {'n': 0}
        async def flaky(*args, **kwargs):
            count['n'] += 1
            if count['n'] >= 2:
                raise httpx.ConnectError('RAW-SIMULATOR-TEXT went away')
            return await original(*args, **kwargs)
        world.create = flaky
        started = await imports.execute_import(c, detail['import_id'], body)
        await c.tasks[started['execution']['execution_id']]
        view = imports.request_view(c.store, detail['import_id'], body.request_id)
        assert view['execution']['status'] == 'INCOMPLETE'
        assert view['error']['code'] == 'LOCAL_CONNECTION_ERROR' and view['error']['error_class'] == 'ConnectError'
        assert view['error']['execution_id'] == started['execution']['execution_id']
        assert 'RAW-SIMULATOR-TEXT' not in json.dumps(view)
        assert view['assertions']['reproduced'] is False
        assert c.store.get_record('budgets', started['owner_campaign_id'])['reservations'] == {} and c.active_id is None
    finally:
        await c.close()


# Finding: the 24-call reservation did not bound charged transport retries.

def test_owner_ledger_bounds_retries_while_keeping_every_reserved_turn(tmp_path):
    store = LabStore(tmp_path / 'lab.sqlite3')
    try:
        ledger = imports.ImportOwnerLedger(store, 'campaign-owner', CampaignBudget())
        for name in protected_reservations(ledger.caps): ledger.release(name)
        ledger.reserve('regression:x', imports.RESERVED_ACTOR_TURNS)
        for _ in range(imports.TRANSPORT_RETRY_ALLOWANCE):
            ledger.consume_call()  # an unreserved, charged transport retry
        with pytest.raises(BudgetExhausted, match='ceiling'):
            ledger.consume_call()
        for _ in range(imports.RESERVED_ACTOR_TURNS):
            ledger.consume_call(reservation='regression:x')
        assert ledger.used_calls == imports.REQUEST_CEILING == 48
        with pytest.raises(BudgetExhausted):
            ledger.consume_call(reservation='regression:x')
        assert store.get_record('budgets', 'campaign-owner')['used_calls'] == 48
    finally:
        store.close()


@pytest.mark.anyio
async def test_reference_target_charges_transport_retries_within_the_request_ceiling(tmp_path):
    from original_loop_fixture import ScriptedProvider
    from app.providers.runtime import RuntimeProviderError

    class FlakyTransport(ScriptedProvider):
        """Every actor request fails once in transport before any answer ($0, scripted)."""
        def __init__(self):
            super().__init__('accepted'); self.failed = set()
        async def complete(self, messages, *, role='actor', **kwargs):
            key = (role, json.dumps(messages, sort_keys=True)[-4000:])
            if role == 'actor' and key not in self.failed:
                self.failed.add(key)
                raise RuntimeProviderError('scripted transport loss', code='CONNECTION_ERROR')
            return await super().complete(messages, role=role, **kwargs)

    c, _, files = await setup(tmp_path, provider=FlakyTransport())
    try:
        detail = await save(c, files); registration = register_agent(c.store, c.settings, 'reference')
        detail = imports.import_detail(c.store, c.settings, detail['import_id'])
        body = request(c, detail, registration)
        started = await imports.execute_import(c, detail['import_id'], body)
        assert isinstance(c.ledgers[started['owner_campaign_id']], imports.ImportOwnerLedger)
        await c.tasks[started['execution']['execution_id']]
        view = imports.request_view(c.store, detail['import_id'], body.request_id)
        budget = c.store.get_record('budgets', started['owner_campaign_id'])
        turns = sum(c.store.get_record('episodes', e)['usage']['actor_calls'] for e in view['execution']['episode_ids'])
        assert budget['used_calls'] > turns  # retries were charged ...
        assert budget['used_calls'] <= imports.REQUEST_CEILING and budget['reservations'] == {}  # ... and bounded
        assert view['owner_charges']['model_calls'] == budget['used_calls']
    finally:
        await c.close()


# Finding: foreign policies imported by the older CLI path before markers existed.

@pytest.mark.anyio
async def test_unmarked_legacy_cli_import_is_still_refused_by_local_acceptance_gates(tmp_path):
    from app.lab.operator_actions import import_bundle
    from app.lab.evaluation import queue_evaluation
    from app.integrations.regression_runner import inspect_bundle
    c, _, foreign = await setup(tmp_path, decision='ACCEPTED', version='policy-legacy-foreign')
    try:
        manifest, payloads = imports._zip_payloads(archive_bytes(foreign))
        with imports._materialized(manifest, payloads) as directory:
            inspected = inspect_bundle(directory)
        owner = c.create(CampaignRequest(mode='baseline', config_profile_id='live-v1', task_text='CLI owner', order_id='order-cli'))
        import_bundle(c.store, inspected, payloads, owner.campaign_id)
        # Simulate a store written before policy_imports markers existed.
        with c.store.lock:
            c.store.db.execute("DELETE FROM records WHERE kind='policy_imports'")
        assert imported_policy(c.store, 'policy-legacy-foreign')
        provenance = imports.policy_import_provenance(c.store, 'policy-legacy-foreign')
        assert provenance['imported'] and provenance['local_acceptance'] is False
        assert provenance['historical_decision'] == 'ACCEPTED' and provenance['import_id'] == inspected.bundle.bundle_id
        before = saved_rows(c)
        with pytest.raises(ValueError, match='historical source decision'):
            await queue_evaluation(c, SimpleNamespace(campaign_id=owner.campaign_id, purpose='comparison',
                                                      policy_versions=['policy-legacy-foreign']))
        assert saved_rows(c) == before
        # The baseline, and a policy whose proposal was made in this store, are never relabeled,
        # even when a legacy import carried the same version name and hash.
        assert not imported_policy(c.store, 'policy-v0')
        ref = c.store.get_record('policies', 'policy-legacy-foreign')['raw_proposal_ref']
        c.store.put_record('proposals', ref, {'raw': '{}', 'author': 'mechanic', 'parent_version': 'policy-v0'}, immutable=True)
        assert not imported_policy(c.store, 'policy-legacy-foreign')
    finally:
        await c.close()


# Finding: the backend accepted any Host header (DNS rebinding) and foreign Origins.

@pytest.mark.anyio
async def test_foreign_host_or_origin_is_refused_before_any_route(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        app = create_app(coordinator=c, allowed_hosts=())
        identity = store_descriptor(c.store)['identity']
        zip_headers = {'content-type': 'application/zip', 'x-faultlab-store-identity': identity}
        before = saved_rows(c)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://attacker.example') as client:
            status = await client.get('/api/config/status')
            assert status.status_code == 403 and identity not in status.text
            assert status.json()['error']['code'] == 'HOST_NOT_ALLOWED'
            assert (await client.get('/api/health')).status_code == 403
            assert (await client.post('/api/bundle-imports', content=archive_bytes(files), headers=zip_headers)).status_code == 403
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000') as client:
            foreign = await client.post('/api/bundle-imports', content=archive_bytes(files),
                                        headers={**zip_headers, 'origin': 'http://attacker.example'})
            assert foreign.status_code == 403
            assert (await client.post('/api/bundle-imports', content=archive_bytes(files),
                                      headers={**zip_headers, 'origin': 'null'})).status_code == 403
            assert saved_rows(c) == before
            assert (await client.get('/api/config/status')).json()['data_store']['identity'] == identity
            local = await client.post('/api/bundle-imports', content=archive_bytes(files),
                                      headers={**zip_headers, 'origin': 'http://127.0.0.1:5173'})
            assert local.status_code == 201, local.text
        for host in ('http://localhost:8000', 'http://[::1]:8000'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=host) as client:
                assert (await client.get('/api/health')).status_code == 200
    finally:
        await c.close()


# Findings: first-time review usability (targets, refusal wording).

@pytest.mark.anyio
async def test_review_omits_internal_smoke_targets_and_names_why_a_target_is_stale(tmp_path):
    from app.integrations.registry import AgentRegistry
    from app.lab.configuration import frozen_configuration
    c, _, files = await setup(tmp_path)
    try:
        detail = await save(c, files)
        caps = CampaignBudget(model_calls=c.settings.faultlab_model_call_cap, tokens=c.settings.faultlab_token_cap,
                              dollars=float(c.settings.faultlab_dollar_cap))
        smoke = AgentRegistry(c.store).register_reference(frozen_configuration(c.settings, caps, 'offline-v1'), internal_smoke=True)
        native = register_agent(c.store, c.settings, 'smolagents')
        targets = imports.import_detail(c.store, c.settings, detail['import_id'])['targets']
        assert smoke.registration_id not in {t['agent_registration_id'] for t in targets}
        assert [t['compatible'] for t in targets if t['agent_registration_id'] == native.registration_id] == [True]
        stale = imports.import_detail(c.store, replace(c.settings, wandb_model='another-model'), detail['import_id'])['targets']
        reason = next(t['reason'] for t in stale if t['agent_registration_id'] == native.registration_id)
        assert 'registered model differs from the configured runtime model' in reason
    finally:
        await c.close()


@pytest.mark.anyio
async def test_refusals_lead_with_a_plain_nothing_saved_sentence(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        for data, category in ((files['evidence.json'].encode(), imports._NOT_ZIP), (b'PK\x05\x06' + b'\0' * 18, imports._STRUCTURE)):
            before = saved_rows(c)
            with pytest.raises(ValueError) as caught:
                await imports.save_import(c, store_descriptor(c.store)['identity'], data)
            message = str(caught.value)
            assert message.startswith('Import refused; nothing was saved. ') and message.endswith(category)
            assert 'inventory or integrity' not in message and saved_rows(c) == before
    finally:
        await c.close()
