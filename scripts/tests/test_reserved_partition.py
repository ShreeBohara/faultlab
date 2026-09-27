"""Offline prospective partition checks. Synthetic histories, no provider calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('reserved_partition', ROOT / 'scripts/experiments/reserved_partition.py')
partition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(partition)


def inventory(recipes=()):
    value = {'schema_version': partition.INVENTORY_SCHEMA, 'algorithm': partition.ALGORITHM,
             'material_signatures': sorted({partition.material_signature(r) for r in recipes}),
             'composition_signatures': sorted({partition.composition_signature(r) for r in recipes}),
             'sources': [], 'counts': {}, 'public_manifest_hashes': {}}
    value['inventory_hash'] = partition.digest(value)
    return value


def declaration():
    return dict(seed=partition.SEED, guards=partition.GUARDS, before_selection=True,
                before_provider_generation=True, no_resampling=True)


def build(history=None):
    history = inventory() if history is None else history
    return partition.build_reserved_partition(history, partition.SEED, seed_declaration=declaration())


def test_signatures_ignore_seed_ids_and_primitive_order_but_not_mechanism():
    original = partition.candidate_universe()[0]['fault_spec']
    changed = deepcopy(original)
    changed['seed'] += 1
    changed['case_id'] = 'cosmetic'
    changed['primitives'].reverse()
    changed['primitives'][0]['fault_id'] = 'also-cosmetic'
    assert partition.material_signature(original) == partition.material_signature(changed)
    assert partition.composition_signature(original) == partition.composition_signature(changed)
    changed['primitives'][0]['parameters']['response_delay_ms'] = 2500
    assert partition.material_signature(original) != partition.material_signature(changed)
    assert partition.composition_signature(original) == partition.composition_signature(changed)


def test_count_delay_and_occurrence_changes_never_create_new_composition():
    for case in partition.candidate_universe():
        spec = deepcopy(case['fault_spec'])
        for p in spec['primitives']:
            p['occurrence'] += 1
            for field in ('failure_count', 'completion_delay_ticks', 'response_delay_ms', 'versions_back'):
                if field in p['parameters']:
                    p['parameters'][field] += 1
        assert partition.composition_signature(spec) == partition.composition_signature(case['fault_spec'])


def test_terminal_rejection_is_a_distinct_semantic_mechanism():
    specs = [c['fault_spec'] for c in partition.candidate_universe()
             if any(p['kind'] == 'F2' for p in c['fault_spec']['primitives'])]
    source = next(s for s in specs if any(p['kind'] == 'F2' and p['parameters']['terminal_status'] == 'FAILED' for p in s['primitives']))
    success = deepcopy(source)
    p = next(p for p in success['primitives'] if p['kind'] == 'F2')
    p['parameters'].update(terminal_status='SUCCEEDED', failure_code=None)
    assert partition.composition_signature(source) != partition.composition_signature(success)


def test_static_universe_has_21_unique_compatible_compositions():
    candidates = partition.candidate_universe()
    assert len(candidates) == 21
    assert len({partition.composition_signature(c['fault_spec']) for c in candidates}) == 21
    for case in candidates:
        primitives = case['fault_spec']['primitives']
        assert len(primitives) == 2
        partition.FaultSpec.model_validate(case['fault_spec'])
        assert all(p['target_tool'] != 'get_operation_status' for p in primitives)
        if any(p['kind'] == 'F3' for p in primitives):
            assert case['fixture_id'] == 'history-v1' and case['expected_version'] == 4
        for p in primitives:
            if p['kind'] != 'F4' and any(q['kind'] == 'F4' and q['target_tool'] == p['target_tool'] for q in primitives):
                assert p['occurrence'] == 2


def test_partition_fixed_categories_repeats_and_deterministic_selection():
    manifest = build()
    assert manifest == build()
    assert [c['case_id'] for c in manifest['cases'][:3]] == partition.GUARDS
    assert [c['case_kind'] for c in manifest['cases']] == [
        'healthy_guard', 'known_family_guard', 'known_family_guard',
        'reserved_composition', 'reserved_composition', 'reserved_composition']
    assert [c['repeats_per_arm'] for c in manifest['cases']] == [3, 15, 15, 15, 15, 15]
    assert manifest['episode_count'] == 156 and manifest['paired_repetitions'] == 78
    from app.lab.heldout_check import replica_layout, expand_cases
    assert len(expand_cases(manifest['cases'], replica_layout(manifest['cases']))) * 6 == 156


def test_exposed_composition_excludes_all_parameter_variants():
    history = inventory([partition.candidate_universe()[0]['fault_spec']])
    summary = partition.availability_summary(history)
    assert summary['available_compositions'] == 20 and summary['excluded_compositions'] == 1
    assert all(partition.composition_signature(c['fault_spec']) not in history['composition_signatures'] for c in build(history)['cases'][3:])


def test_insufficient_new_compositions_refuses_without_substitution():
    history = inventory([c['fault_spec'] for c in partition.candidate_universe()[:-2]])
    assert partition.availability_summary(history)['available_compositions'] == 2
    with pytest.raises(ValueError, match='Fewer than three'):
        build(history)


@pytest.mark.parametrize('change', [dict(seed='another'), dict(before_selection=False),
                                  dict(no_resampling=False), dict(guards=['healthy'])])
def test_missing_or_changed_prior_seed_declaration_refused(change):
    with pytest.raises(ValueError, match='Seed declaration'):
        partition.build_reserved_partition(inventory(), partition.SEED, seed_declaration=declaration() | change)


@pytest.mark.parametrize('mutation', ['duplicate', 'seed_only', 'preemption', 'fixture', 'repeats', 'replacement', 'ordering'])
def test_manifest_mutations_do_not_evade_novelty_or_fixed_selection(mutation):
    history, manifest = inventory(), build()
    if mutation == 'duplicate':
        manifest['cases'][4]['fault_spec'] = deepcopy(manifest['cases'][3]['fault_spec'])
    elif mutation == 'seed_only':
        manifest['cases'][3]['fault_spec']['seed'] += 1
    elif mutation == 'preemption':
        for p in manifest['cases'][3]['fault_spec']['primitives']:
            p['occurrence'] = 3
    elif mutation == 'fixture':
        manifest['cases'][3]['expected_version'] = 900
    elif mutation == 'repeats':
        manifest['cases'][3]['repeats_per_arm'] = 3
    elif mutation == 'replacement':
        existing = {partition.composition_signature(c['fault_spec']) for c in manifest['cases'][3:]}
        other = next(c for c in partition.candidate_universe() if partition.composition_signature(c['fault_spec']) not in existing)
        manifest['cases'][3].update(deepcopy(other))
    else:
        manifest['cases'][3], manifest['cases'][4] = manifest['cases'][4], manifest['cases'][3]
    with pytest.raises(ValueError):
        partition.validate_partition(manifest, history)


def test_exposure_inventory_hash_tampering_refused():
    history = inventory()
    history['counts']['extra'] = 1
    with pytest.raises(ValueError, match='hash mismatch'):
        partition.availability_summary(history)


def commit():
    history, manifest = inventory(), build()
    return manifest, partition.partition_commitment(manifest, history, committed_at='2026-09-27T12:00:00+00:00')


def bind(manifest, commitment, **changes):
    return partition.bind_candidate(commitment, manifest, **(
        dict(policy_hash='a' * 64, policy_version='policy-new', study_id='completion-study-new',
             generation_started_at='2026-09-27T12:00:01+00:00', prior_policy_hashes=[]) | changes))


def test_commitment_is_public_and_candidate_binding_is_exact():
    manifest, commitment = commit()
    assert 'fault_spec' not in partition.canonical(commitment)
    assert 'primitives' not in partition.canonical(commitment)
    binding = bind(manifest, commitment)
    assert binding['partition_hash'] == partition.digest(manifest)
    assert binding['policy_hash'] == 'a' * 64
    assert binding['ordinary_policy_accepted'] is False


@pytest.mark.parametrize('when', ['2026-09-27T11:59:59Z', '2026-09-27T12:00:00Z', '2026-09-27T12:00:01'])
def test_commitment_must_strictly_precede_generation_with_explicit_timezone(when):
    manifest, commitment = commit()
    with pytest.raises(ValueError):
        bind(manifest, commitment, generation_started_at=when)


@pytest.mark.parametrize('change', [dict(prior_policy_hashes=['a' * 64]), dict(policy_hash='bad'),
                                  dict(policy_version=''), dict(study_id='other-study')])
def test_binding_rejects_rediscovery_or_missing_exact_identity(change):
    manifest, commitment = commit()
    with pytest.raises(ValueError):
        bind(manifest, commitment, **change)


def test_manifest_or_commitment_tampering_after_freeze_refused():
    manifest, commitment = commit()
    altered = deepcopy(manifest)
    altered['cases'][3]['fault_spec']['seed'] += 1
    with pytest.raises(ValueError, match='changed after commitment'):
        bind(altered, commitment)
    commitment['committed_at'] = '2026-09-27T11:00:00Z'
    with pytest.raises(ValueError, match='Invalid partition commitment'):
        bind(manifest, commitment)


def make_database(root, table='records', spec=None):
    path = root / 'artifacts' / 'test.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        if table == 'records':
            db.execute('CREATE TABLE records(payload TEXT)')
            db.execute('INSERT INTO records VALUES(?)', (json.dumps({'private_case_id': 'never-return-me', 'fault_spec': spec}),))
        elif table == 'state':
            db.execute('CREATE TABLE state(value TEXT)')
            db.execute('INSERT INTO state VALUES(?)', (json.dumps({'fault_spec': spec}),))
        else:
            db.execute('CREATE TABLE unknown(value TEXT)')
    return path


def test_inventory_reads_protected_recipes_but_returns_hash_only_metadata(tmp_path):
    recipe = partition.candidate_universe()[0]['fault_spec']
    path = make_database(tmp_path, spec=recipe)
    before = path.read_bytes()
    result = partition.scan_exposure_inventory(tmp_path)
    assert path.read_bytes() == before
    assert partition.composition_signature(recipe) in result['composition_signatures']
    assert 'never-return-me' not in partition.canonical(result)
    assert 'primitives' not in partition.canonical(result)
    assert result['counts']['record_databases'] == 1
    assert result['counts']['matching_record_rows'] == 1


def test_world_inventory_and_mixed_json_logs_are_counted(tmp_path):
    recipes = [c['fault_spec'] for c in partition.candidate_universe()[:2]]
    make_database(tmp_path, table='state', spec=recipes[0])
    (tmp_path / 'artifacts' / 'old.out.json').write_text(json.dumps({'fault_spec': recipes[1]}) + '\nlog line\n' + json.dumps({'count': 2}))
    (tmp_path / 'artifacts' / 'status.json').write_text('old command ended without an answer\n')
    result = partition.scan_exposure_inventory(tmp_path)
    assert result['counts']['world_databases'] == 1
    assert result['counts']['mixed_json_logs'] == 1
    assert result['counts']['text_logs_without_recipe'] == 1
    assert all(partition.composition_signature(r) in result['composition_signatures'] for r in recipes)


def test_saved_unexecuted_explorer_json_string_counts_as_exposure(tmp_path):
    recipe = partition.candidate_universe()[0]['fault_spec']
    path = make_database(tmp_path, spec=None)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO records VALUES(?)', (json.dumps({'raw_output': '```json\n' + json.dumps({'fault_spec': recipe}) + '\n```'}),))
    result = partition.scan_exposure_inventory(tmp_path)
    assert partition.composition_signature(recipe) in result['composition_signatures']
    assert result['counts']['embedded_json_strings'] == 1
    assert result['counts']['unresolved_recipe_strings'] == 0


def test_truncated_potential_recipe_blocks_selection_but_schema_description_does_not(tmp_path):
    path = make_database(tmp_path, spec=None)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO records VALUES(?)', (json.dumps({'raw': '{"primitives": [{"kind": "F1",'}),))
        db.execute('INSERT INTO records VALUES(?)', (json.dumps({'schema': '{"properties":{"primitives":{"type":"array"}}}'}),))
    result = partition.scan_exposure_inventory(tmp_path)
    assert result['counts']['unresolved_recipe_strings'] == 1
    with pytest.raises(ValueError, match='truncated'):
        partition.availability_summary(result)


@pytest.mark.parametrize('case', ['unknown_db', 'missing_world_recipe', 'broken_recipe_json', 'no_db'])
def test_incomplete_exposure_coverage_fails_closed(tmp_path, case):
    if case == 'unknown_db':
        make_database(tmp_path, table='unknown')
    elif case == 'missing_world_recipe':
        make_database(tmp_path, table='state', spec=None)
    elif case == 'broken_recipe_json':
        make_database(tmp_path, spec=partition.candidate_universe()[0]['fault_spec'])
        (tmp_path / 'artifacts' / 'broken.json').write_text('{"primitives": [BROKEN')
    with pytest.raises(ValueError):
        partition.scan_exposure_inventory(tmp_path)


@pytest.mark.parametrize('case_index', range(21))
def test_every_static_composition_has_a_legal_trigger_witness(tmp_path, monkeypatch, case_index):
    """A mechanical witness only; does not pretest Actor outcomes or select cases.

    Use the real dispatcher and fresh state, with only F1's wall sleep elided.
    A valid fixed sequence exists within business budgets for both primitives.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.contracts.models import TaskIntent
    from app.simulator import business
    from app.simulator.storage import WorldStore
    case = partition.candidate_universe()[case_index]
    intent = TaskIntent(task_id='task-witness', order_id='order-witness', expected_version=case['expected_version'],
        upgrade_operation_id='upgrade-witness', notification_operation_id='notify-witness',
        upgrade_idempotency_key='upgrade-key', notification_idempotency_key='notify-key',
        upgrade_intent_hash='1' * 64, notification_intent_hash='2' * 64, task_text='Upgrade and confirm')
    store = WorldStore(tmp_path)
    handle = store.create('episode-witness', intent, partition.FaultSpec.model_validate(case['fault_spec']), case['fixture_id'])
    app = FastAPI()
    app.include_router(business.router(store))
    async def no_sleep(_):
        return None
    monkeypatch.setattr(business.asyncio, 'sleep', no_sleep)
    upgrade = dict(order_id=intent.order_id, desired_shipping='express', expected_version=intent.expected_version,
                   operation_id=intent.upgrade_operation_id, idempotency_key=intent.upgrade_idempotency_key,
                   intent_hash=intent.upgrade_intent_hash)
    notification = dict(order_id=intent.order_id, upgrade_operation_id=intent.upgrade_operation_id,
                        operation_id=intent.notification_operation_id, idempotency_key=intent.notification_idempotency_key,
                        intent_hash=intent.notification_intent_hash, template_version='confirmation/v1')
    attempted = 0
    with TestClient(app) as client:
        def call(method, route, payload=None):
            nonlocal attempted
            # Same logical operation and bytes, one bounded transient retry.
            for _ in range(2):
                attempted += 1
                headers = {'X-FaultLab-World': handle['world_id'], 'X-FaultLab-Capability': handle['capability'],
                           'X-FaultLab-Call': f'call-{attempted}', 'X-FaultLab-Attempt': f'attempt-{attempted}'}
                response = client.request(method, route, headers=headers, **({'json': payload} if payload else {}))
                if response.status_code != 503:
                    assert response.status_code in (200, 201, 202)
                    return response.json()
            pytest.fail('Static witness exhausted its bounded retry')
        call('GET', '/business/orders/order-witness')
        result = call('POST', '/business/orders/order-witness/upgrade', upgrade)
        for _ in range(3):
            if result.get('status') != 'PENDING':
                break
            result = call('GET', '/business/operations/orders/upgrade-witness')
        if result.get('status') == 'SUCCEEDED':
            call('POST', '/business/notifications', notification)
    state = store.read(handle['world_id'])
    assert all(f['triggered'] for f in state['fault_executions'])
    assert state['attempts'] <= 18 and state['tick'] <= 20
    assert len(state['notifications']) == (0 if case['expected_outcome'] == 'CORRECTLY_REJECTED' else 1)
    assert state['order']['version'] == case['expected_version'] + (0 if case['expected_outcome'] == 'CORRECTLY_REJECTED' else 1)
