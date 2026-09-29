"""Negative paths for dashboard bundle import, review and explicit fresh rerun.

Uploaded bytes are data: they are bounded before parsing, never executed, and a
historical ACCEPTED decision never becomes a local acceptance. Every refusal leaves
the store byte-identical and makes no provider call.
"""
import asyncio
from dataclasses import replace
import io
import json
from pathlib import Path
import runpy
import stat
import subprocess
import sys
import zipfile

import httpx
import pytest

from app.contracts.models import CampaignRequest, canonical_json, content_hash
from app.lab import bundle_imports as imports
from app.lab.coordinator import LabCoordinator
from app.lab.dashboard import store_descriptor
from app.lab.operator_actions import register_agent
from app.lab.policies import IMPORTED_POLICY_REFUSAL
from app.lab.storage import StoreConflict
from app.main import create_app
from test_bundle_imports import archive_bytes, bundle_fixture, request, save, saved_rows, setup
from test_planned_agent_execution import runtime

# A real dashboard download made at checkpoint 8e497da (simulator contract 6f9d7783…), which is
# the installed simulator identity again (the September 28 PM decision reverted the lazy
# simulator entry point to keep earlier exports and registrations compatible).
REAL_ZIP = Path(__file__).resolve().parents[3] / 'frontend/tests/fixtures/exported-regression.zip'
# The same kind of real download, made by an uncommitted simulator build (runtimes bb87c764…
# to c9b1b7e6…, contract 1099eda7…) that was then reverted. Kept to show how an export from a
# different simulator build is treated.
OTHER_SIMULATOR_ZIP = REAL_ZIP.with_name('exported-regression-other-simulator.zip')


@pytest.fixture
def anyio_backend(): return 'asyncio'


def entry_zip(files, *, special=None, compression=zipfile.ZIP_DEFLATED):
    """Write a ZIP whose named entries may carry a chosen mode or compression."""
    special = special or {}
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', compression) as archive:
        for name, text in files.items():
            options = special.get(name)
            if options is None:
                archive.writestr(name, text)
                continue
            info = zipfile.ZipInfo(name)
            info.compress_type = options.get('compress_type', compression)
            if 'mode' in options:
                info.create_system = 3
                info.external_attr = options['mode'] << 16
            archive.writestr(info, text)
    return target.getvalue()


def set_encrypted_flag(data, name):
    """Mark one entry as encrypted in both headers without changing its bytes."""
    data = bytearray(data)
    encoded = name.encode()
    central = data.find(b'PK\x01\x02')
    while central >= 0:
        size = int.from_bytes(data[central + 28:central + 30], 'little')
        if data[central + 46:central + 46 + size] == encoded:
            data[central + 8] |= 1
            local = int.from_bytes(data[central + 42:central + 46], 'little')
            data[local + 6] |= 1
            return bytes(data)
        central = data.find(b'PK\x01\x02', central + 4)
    raise AssertionError('entry not found')


def rehashed(bundle_files, **changes):
    manifest = json.loads(bundle_files['manifest.json'])
    manifest.update(changes)
    manifest['manifest_hash'] = content_hash({k: v for k, v in manifest.items() if k != 'manifest_hash'})
    return {**bundle_files, 'manifest.json': canonical_json(manifest)}


async def refused(c, data, category):
    before = saved_rows(c)
    with pytest.raises(ValueError) as caught:
        await imports.save_import(c, store_descriptor(c.store)['identity'], data)
    message = str(caught.value)
    assert message.startswith(imports.REJECTED + ' ')
    assert message == f'{imports.REJECTED} {imports._UNKNOWN if category is None else category}'
    assert 'PRIVATE_CANARY' not in message and len(message) <= 200
    assert saved_rows(c) == before and not c.runner.provider.calls
    return message


@pytest.mark.anyio
@pytest.mark.parametrize('attack', ['symlink_policy', 'fifo_policy', 'encrypted_policy', 'bzip2_policy',
    'absolute_name', 'backslash_traversal', 'dot_segment', 'directory_entry', 'total_expanded', 'manifest_bound',
    'per_file_bound'])
async def test_zip_structure_attacks_on_exact_inventory_names_are_refused(tmp_path, monkeypatch, attack):
    c, _, files = await setup(tmp_path)
    try:
        files = dict(files)
        data = None
        if attack == 'symlink_policy':
            data = entry_zip(files, special={'policy.json': {'mode': stat.S_IFLNK | 0o777}})
        if attack == 'fifo_policy':
            data = entry_zip(files, special={'policy.json': {'mode': stat.S_IFIFO | 0o644}})
        if attack == 'encrypted_policy':
            data = set_encrypted_flag(archive_bytes(files), 'policy.json')
        if attack == 'bzip2_policy':
            data = entry_zip(files, special={'policy.json': {'compress_type': zipfile.ZIP_BZIP2}})
        if attack == 'absolute_name':
            files['/policy.json'] = files.pop('policy.json')
        if attack == 'backslash_traversal':
            files['..\\policy.json'] = files.pop('policy.json')
        if attack == 'dot_segment':
            files['harness/../policy.json'] = files.pop('policy.json')
        if attack == 'directory_entry':
            files.pop('evidence.json')
            data = entry_zip({**files, 'harness/': ''})
        if attack == 'total_expanded':
            monkeypatch.setattr(imports, 'MAX_BUNDLE_BYTES', 1024)
        if attack == 'manifest_bound':
            monkeypatch.setattr(imports, 'MAX_MANIFEST_BYTES', 512)
        if attack == 'per_file_bound':
            monkeypatch.setattr(imports, 'MAX_BUNDLE_FILE', 64)
        await refused(c, data if data is not None else archive_bytes(files), imports._STRUCTURE)
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('change', ['evidence', 'trials', 'manifest_unhashed', 'configuration', 'lineage'])
async def test_tampered_contents_are_refused_as_integrity_failures(tmp_path, change):
    c, _, files = await setup(tmp_path)
    try:
        files = dict(files)
        if change == 'evidence':
            evidence = json.loads(files['evidence.json'])
            evidence['completeness_notes'] = ['PRIVATE_CANARY edited after export']
            files['evidence.json'] = canonical_json(evidence)
        if change == 'trials':
            files['trials.json'] = files['trials.json'] + '\n'
        if change == 'manifest_unhashed':
            manifest = json.loads(files['manifest.json'])
            manifest['setup_instructions'] = 'PRIVATE_CANARY edited without rehash'
            files['manifest.json'] = canonical_json(manifest)
        if change == 'configuration':
            files['configuration.json'] = files['configuration.json'].replace('"', ' "', 1)
        if change == 'lineage':
            lineage = json.loads(files['lineage.json'])
            lineage['counterexample']['target_invariant'] = 'C4'
            files['lineage.json'] = canonical_json(lineage)
        await refused(c, archive_bytes(files), imports._INTEGRITY)
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('change', ['runner_version', 'schema', 'profile'])
async def test_unsupported_bundle_versions_are_refused_with_a_preservation_hint(tmp_path, change):
    c, _, files = await setup(tmp_path)
    try:
        if change == 'runner_version':
            # Shaped like a bundle from another runner generation: no evidence file.
            files = dict(files); files.pop('evidence.json')
            listed = [entry for entry in json.loads(files['manifest.json'])['files'] if entry['path'] != 'evidence.json']
            files = rehashed(files, harness_version='faultlab-runner-v0', files=listed)
        if change == 'schema':
            files = rehashed(files, schema_hash='0' * 64)
        if change == 'profile':
            files = rehashed(files, execution_profile_id='unreviewed-v9')
        message = await refused(c, archive_bytes(files), imports._VERSION)
        assert 'FaultLab version that created it' in message
    finally:
        await c.close()


@pytest.mark.anyio
async def test_recording_json_and_non_zip_bytes_are_named_as_evidence_not_bundles(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        await refused(c, files['evidence.json'].encode(), imports._NOT_ZIP)
        await refused(c, b'PK\x03\x04 truncated', imports._NOT_ZIP)
        app = create_app(coordinator=c)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            headers = {'x-faultlab-store-identity': store_descriptor(c.store)['identity']}
            response = await client.post('/api/bundle-imports', content=files['evidence.json'],
                                         headers={**headers, 'content-type': 'application/json'})
            assert response.status_code == 422 and 'recording JSON' in response.json()['error']['message']
            response = await client.post('/api/bundle-imports', content=files['evidence.json'],
                                         headers={**headers, 'content-type': 'application/zip'})
            assert response.status_code == 422
            assert response.json()['error']['message'] == f'{imports.REJECTED} {imports._NOT_ZIP}'
        assert not c.store.list_records(imports.IMPORT_KIND)
    finally:
        await c.close()


@pytest.mark.anyio
async def test_declared_oversized_body_is_refused_before_any_byte_is_read():
    read = []
    class Request:
        headers = {'content-type': 'application/zip', 'content-length': str(imports.MAX_UPLOAD_BYTES + 1)}
        async def stream(self):
            read.append(True)
            yield b'never'
    with pytest.raises(ValueError, match='transport bound'):
        await imports.read_zip_request(Request())
    assert read == []


@pytest.mark.anyio
async def test_same_bundle_identity_with_different_manifest_is_refused_without_writes(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        first = await save(c, files)
        before = saved_rows(c)
        with pytest.raises(StoreConflict, match='conflicts'):
            await save(c, rehashed(files, setup_instructions='A different manifest reusing the bundle identity'))
        assert saved_rows(c) == before
        assert imports.import_detail(c.store, c.settings, first['import_id']) == first
    finally:
        await c.close()


@pytest.mark.anyio
async def test_intentional_new_request_gets_new_worlds_while_retry_returns_the_first_run(tmp_path):
    c, bundle, files = await setup(tmp_path, decision='ACCEPTED', version='policy-historical')
    try:
        detail = await save(c, files)
        registration = register_agent(c.store, c.settings, 'smolagents')
        first_body = request(c, detail, registration, 'request-import-first')
        started = await imports.execute_import(c, detail['import_id'], first_body)
        await c.tasks[started['execution']['execution_id']]
        first = imports.request_view(c.store, detail['import_id'], first_body.request_id)
        second_body = request(c, detail, registration, 'request-import-second')
        started = await imports.execute_import(c, detail['import_id'], second_body)
        await c.tasks[started['execution']['execution_id']]
        second = imports.request_view(c.store, detail['import_id'], second_body.request_id)
        assert first['execution']['status'] == second['execution']['status'] == 'COMPLETED'
        assert first['execution']['execution_id'] != second['execution']['execution_id']
        assert first['owner_campaign_id'] != second['owner_campaign_id']
        worlds = first['execution']['world_ids'] + second['execution']['world_ids']
        episodes = first['execution']['episode_ids'] + second['execution']['episode_ids']
        assert len(worlds) == len(set(worlds)) == 6 and len(episodes) == len(set(episodes)) == 6
        versions = {c.store.get_record('episodes', e)['policy_version'] for e in episodes}
        assert len(versions) == 1 and next(iter(versions)).startswith('imported-')
        assert len(c.store.list_records('policy_imports')) == 1
        before = saved_rows(c)
        assert await imports.execute_import(c, detail['import_id'], first_body) == first
        assert saved_rows(c) == before
        page = imports.execution_page(c.store, detail['import_id'])
        assert [item['request_id'] for item in page['items']] == [second_body.request_id, first_body.request_id]
        assert all(c.get(item['owner_campaign_id']).active_policy_version == 'policy-v0' for item in page['items'])
    finally:
        await c.close()


@pytest.mark.anyio
async def test_imported_historical_acceptance_is_refused_by_every_local_acceptance_gate(tmp_path):
    c, _, files = await setup(tmp_path, decision='ACCEPTED', version='policy-historical')
    try:
        detail = await save(c, files)
        registration = register_agent(c.store, c.settings, 'smolagents')
        body = request(c, detail, registration)
        started = await imports.execute_import(c, detail['import_id'], body)
        await c.tasks[started['execution']['execution_id']]
        alias = c.store.list_records('policy_imports')[0]
        policy = c.policies.get(next(p['version'] for p in c.store.list_records('policies') if p['version'].startswith('imported-')))
        assert policy.decision == 'ACCEPTED' and alias['local_acceptance'] is False
        ordinary = c.create(CampaignRequest(mode='baseline', config_profile_id='live-v1',
                                            task_text='Ordinary local run', order_id='order-local'))
        local_bundle, _ = bundle_fixture(c)  # an ordinary local regression with the same policy content
        local_regression = next(r for r in c.store.list_records('regressions') if r['bundle_id'] == local_bundle.bundle_id)
        assert local_bundle.policy_hash == policy.policy_hash
        before = saved_rows(c)
        from types import SimpleNamespace
        from app.lab.evaluation import queue_evaluation
        from app.lab.portability import queue_portability
        from app.lab.audit import queue_audit
        from app.lab.regression_executions import execute_regression
        from app.cli.freeze import freeze_campaign
        for purpose in ('comparison', 'final_audit'):
            with pytest.raises(ValueError, match='historical source decision'):
                await queue_evaluation(c, SimpleNamespace(campaign_id=ordinary.campaign_id, purpose=purpose,
                                                          policy_versions=['policy-v0', policy.version]))
        with pytest.raises(ValueError, match='historical source decision'):
            await queue_portability(c, ordinary.campaign_id, SimpleNamespace(policy_version=policy.version,
                agent_registration_id=registration.registration_id, execute_live=True))
        with pytest.raises(StoreConflict, match='historical source decision'):
            await queue_audit(c, ordinary, policy)
        with pytest.raises(ValueError, match='reviewed import execution'):
            await execute_regression(c, local_regression['regression_id'], SimpleNamespace(policy_version=policy.version,
                agent_registration_id=registration.registration_id, execution_profile_id='sandbox-v1', execute_live=True))
        assert saved_rows(c) == before
        app = create_app(coordinator=c)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/evaluations', json={'campaign_id': ordinary.campaign_id,
                'purpose': 'comparison', 'policy_versions': ['policy-v0', policy.version]})
            assert response.status_code == 422 and 'historical source decision' in response.json()['error']['message']
            provenance = (await client.get(f'/api/policies/{policy.version}/import-provenance')).json()
            assert provenance['historical_decision'] == 'ACCEPTED' and provenance['local_acceptance'] is False
        assert saved_rows(c) == before
        assert c.store.get_pointer('accepted-policy:' + registration.configuration_hash) is None
        assert IMPORTED_POLICY_REFUSAL.startswith('An imported policy')
        # Defense in depth: even a corrupted owner pointing at the alias cannot be frozen as a learned
        # arm; the owner guard refuses first, and the imported-policy guard refuses any other campaign.
        owner = c.get(started['owner_campaign_id'])
        c.save(owner.model_copy(update={'state': 'STOPPED', 'active_policy_version': policy.version}))
        with pytest.raises(StoreConflict, match='separately reviewed execution'):
            freeze_campaign(c.store, c.settings, owner.campaign_id)
        assert c.store.get_record('audit_freezes', owner.campaign_id) is None
        c.save(c.get(ordinary.campaign_id).model_copy(update={'state': 'STOPPED', 'active_policy_version': policy.version}))
        with pytest.raises(ValueError, match='historical source decision'):
            freeze_campaign(c.store, c.settings, ordinary.campaign_id)
        assert c.store.get_record('audit_freezes', ordinary.campaign_id) is None
    finally:
        await c.close()


@pytest.mark.anyio
async def test_archive_mode_reads_imports_but_refuses_execute_and_cancel_without_writes(tmp_path):
    c, _, files = await setup(tmp_path)
    try:
        detail = await save(c, files)
        registration = register_agent(c.store, c.settings, 'smolagents')
        body = request(c, detail, registration).model_dump(mode='json')
        settings = c.settings
    finally:
        await c.close()
    archive_settings = replace(settings, faultlab_read_only=True)
    reopened = LabCoordinator(settings)
    before = saved_rows(reopened)
    await reopened.close()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings=archive_settings)),
                                 base_url='http://test') as client:
        ident = detail['import_id']
        assert (await client.get(f'/api/bundle-imports/{ident}')).json()['import_id'] == ident
        assert (await client.get(f'/api/bundle-imports/{ident}/executions')).json()['items'] == []
        executed = await client.post(f'/api/bundle-imports/{ident}/execute', json=body)
        cancelled = await client.post(f'/api/bundle-imports/{ident}/requests/{body["request_id"]}/cancel', json=body)
        assert executed.status_code == cancelled.status_code == 409
        assert executed.json()['error']['code'] == cancelled.json()['error']['code'] == 'READ_ONLY_ARCHIVE'
    reopened = LabCoordinator(settings)
    try:
        assert saved_rows(reopened) == before
    finally:
        await reopened.close()


@pytest.mark.anyio
async def test_import_review_and_fresh_rerun_never_execute_bundle_code(tmp_path, monkeypatch):
    c, _, files = await setup(tmp_path)
    try:
        def forbidden(*args, **kwargs):
            raise AssertionError('Uploaded bundle content must never be executed')
        real_popen = subprocess.Popen
        def guarded_popen(args, *rest, **kwargs):
            command = ' '.join(map(str, args)) if isinstance(args, (list, tuple)) else str(args)
            if any(marker in command for marker in ('test_regression', 'import-executions', 'faultlab-reviewed-import-', 'pytest')):
                forbidden()
            return real_popen(args, *rest, **kwargs)
        monkeypatch.setattr(subprocess, 'Popen', guarded_popen)
        monkeypatch.setattr(runpy, 'run_path', forbidden)
        monkeypatch.setattr(runpy, 'run_module', forbidden)
        imported_modules = set(sys.modules)
        detail = await save(c, files)
        imports.import_detail(c.store, c.settings, detail['import_id'])
        registration = register_agent(c.store, c.settings, 'smolagents')
        started = await imports.execute_import(c, detail['import_id'], request(c, detail, registration))
        await c.tasks[started['execution']['execution_id']]
        result = imports.request_view(c.store, detail['import_id'], started['request_id'])
        assert result['execution']['status'] == 'COMPLETED'
        loaded = set(sys.modules) - imported_modules
        assert not any(name == 'test_regression' or name.endswith('.test_regression') for name in loaded)
        harness = next((c.settings.artifact_path / 'import-executions').rglob('harness/test_regression.py'))
        assert not any(getattr(module, '__file__', None) and Path(module.__file__).resolve() == harness.resolve()
                       for module in list(sys.modules.values()))
    finally:
        await c.close()


@pytest.mark.anyio
async def test_real_saved_download_imports_once_and_a_tampered_copy_is_refused(tmp_path):
    if not REAL_ZIP.is_file():
        pytest.skip('Saved dashboard download fixture is not in this checkout')
    data = REAL_ZIP.read_bytes()
    c = await runtime(tmp_path / 'target')
    try:
        detail = await imports.save_import(c, store_descriptor(c.store)['identity'], data)
        assert detail['artifact_kind'] == 'incident_fixture' and detail['runnable']
        assert detail['source']['source_modes'] == ['offline_fixture']
        assert detail['source']['evidence_verification'] == 'NO_LOCAL_VERIFICATION'
        assert detail['historical']['label'] == 'Imported historical observations; not verified locally'
        assert len(detail['historical']['trials']) == len(detail['historical']['recording']['episodes']) == 16
        rows = saved_rows(c)
        assert await imports.save_import(c, store_descriptor(c.store)['identity'], data) == detail
        assert saved_rows(c) == rows
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = {name: archive.read(name).decode() for name in archive.namelist()}
        evidence = json.loads(files['evidence.json'])
        evidence['completeness_notes'] = [*evidence.get('completeness_notes', []), 'Edited after download']
        files['evidence.json'] = canonical_json(evidence)
        await refused(c, archive_bytes(files), imports._INTEGRITY)
        assert c.store.list_records('campaigns') == [] and [p['version'] for p in c.store.list_records('policies')] == ['policy-v0']
        # Explicit rerun of the real download with the offline scripted native target (no provider).
        registration = register_agent(c.store, c.settings, 'smolagents')
        body = request(c, imports.import_detail(c.store, c.settings, detail['import_id']), registration)
        started = await imports.execute_import(c, detail['import_id'], body)
        await c.tasks[started['execution']['execution_id']]
        result = imports.request_view(c.store, detail['import_id'], body.request_id)
        assert result['execution']['status'] == 'COMPLETED' and not result['source_evidence_verified_locally']
        assert result['assertions']['valid_trials'] == 3 and result['assertions']['source_modes'] == ['offline_fixture']
        assert not result['assertions']['provider_backed'] and result['execution']['usage']['cost_dollars'] == 0
        historical = {trial['world_id'] for trial in detail['historical']['trials']}
        assert len(set(result['execution']['world_ids']) - historical) == 3
        for episode_id in result['execution']['episode_ids']:
            verdict = c.store.get_record('episodes', episode_id)['verdict']
            assert verdict['fault_executions'] and all(f['triggered'] for f in verdict['fault_executions'])
        assert c.get(result['owner_campaign_id']).active_policy_version == 'policy-v0'
    finally:
        await c.close()


@pytest.mark.anyio
async def test_cli_import_marks_only_foreign_policy_versions_so_local_gates_refuse_them(tmp_path):
    """The older CLI import-and-execute path keeps source version names; it must not
    turn a foreign historical ACCEPTED label into a local acceptance either."""
    from types import SimpleNamespace
    from app.lab.evaluation import queue_evaluation
    from app.lab.operator_actions import import_bundle
    from app.integrations.regression_runner import inspect_bundle
    c, _, foreign = await setup(tmp_path, decision='ACCEPTED', version='policy-foreign-accepted')
    try:
        manifest, payloads = imports._zip_payloads(archive_bytes(foreign))
        with imports._materialized(manifest, payloads) as directory:
            inspected = inspect_bundle(directory)
        owner = c.create(CampaignRequest(mode='baseline', config_profile_id='live-v1', task_text='CLI owner', order_id='order-cli'))
        import_bundle(c.store, inspected, payloads, owner.campaign_id)
        marker = c.store.get_record('policy_imports', 'policy-foreign-accepted')
        assert marker['historical_decision'] == 'ACCEPTED' and marker['local_acceptance'] is False
        assert marker['import_id'] == inspected.bundle.bundle_id
        with pytest.raises(ValueError, match='historical source decision'):
            await queue_evaluation(c, SimpleNamespace(campaign_id=owner.campaign_id, purpose='comparison',
                                                      policy_versions=['policy-foreign-accepted']))
        # A bundle whose policy already exists locally (the shared baseline) is not relabeled.
        local_bundle, local_files = bundle_fixture(c)
        manifest, payloads = imports._zip_payloads(archive_bytes(local_files))
        with imports._materialized(manifest, payloads) as directory:
            inspected = inspect_bundle(directory)
        import_bundle(c.store, inspected, payloads, owner.campaign_id)
        assert c.store.get_record('policy_imports', 'policy-v0') is None
    finally:
        await c.close()


@pytest.mark.anyio
async def test_a_download_from_a_different_simulator_identity_stays_reviewable_but_never_reruns(tmp_path):
    """Its task, tool and oracle semantics cannot be shown to match the current simulator, so
    the review lists every target as incompatible with that reason and a fresh run is refused
    before any record is written or any model is called."""
    if not OTHER_SIMULATOR_ZIP.is_file():
        pytest.skip('Other-simulator download fixture is not in this checkout')
    data = OTHER_SIMULATOR_ZIP.read_bytes()
    c = await runtime(tmp_path / 'target')
    try:
        detail = await imports.save_import(c, store_descriptor(c.store)['identity'], data)
        assert detail['artifact_kind'] == 'incident_fixture' and len(detail['historical']['trials']) == 16
        manifest = json.loads(zipfile.ZipFile(io.BytesIO(data)).read('manifest.json'))
        current = imports._installed_semantics()
        assert manifest['contract_hash'] != current['contract_hash']
        # Only the simulator/contract identity differs; tools, scorer and interpreter are the same.
        assert all(manifest[field] == current[field] for field in ('capability_hash', 'scorer_hash', 'interpreter_hash'))
        registration = register_agent(c.store, c.settings, 'smolagents')
        reviewed = imports.import_detail(c.store, c.settings, detail['import_id'])
        target = next(t for t in reviewed['targets'] if t['agent_registration_id'] == registration.registration_id)
        assert target['compatible'] is False and 'semantics are incompatible' in target['reason']
        # Review finding: the refusal names the cause (an earlier or different simulator build) and both identities,
        # and the review says so for the bundle itself, before any target is selected.
        assert reviewed['runnable'] is False and 'earlier or different simulator build' in reviewed['runnable_reason']
        assert 'earlier or different simulator build' in target['reason']
        assert f"bundle {manifest['contract_hash'][:8]}…, installed {current['contract_hash'][:8]}…" in target['reason']
        before = saved_rows(c)
        with pytest.raises(StoreConflict, match='semantics are incompatible'):
            await imports.execute_import(c, detail['import_id'], request(c, reviewed, registration))
        assert saved_rows(c) == before and not c.runner.provider.calls
        assert c.store.list_records('campaigns') == []
    finally:
        await c.close()


def test_semantics_refusal_names_each_differing_identity_and_the_simulator_cause():
    from types import SimpleNamespace
    current = {'contract_hash': '1' * 64, 'capability_hash': '2' * 64, 'scorer_hash': '3' * 64, 'interpreter_hash': '4' * 64}
    same = SimpleNamespace(**current)
    assert imports.semantics_mismatch(current, same) is None
    older = SimpleNamespace(**{**current, 'contract_hash': 'a' * 64})
    message = imports.semantics_mismatch(current, older)
    assert 'task contract and simulator: bundle aaaaaaaa…, installed 11111111…' in message
    assert 'earlier or different simulator build' in message and 'saved evidence stays reviewable' in message
    scorer = imports.semantics_mismatch(current, SimpleNamespace(**{**current, 'scorer_hash': 'b' * 64}))
    assert 'fixed scorer: bundle bbbbbbbb…' in scorer and 'simulator build' not in scorer
