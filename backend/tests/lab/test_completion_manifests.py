"""Phase 28 (docs/part2/PHASE28_DESIGN.md sections 8.1-8.2): the 'upgrade-v1' completion manifest,
the closed manifest registry, the request field and the transposed source clause.

Offline only: no provider, no network, no store outside tmp_path. The end-to-end studies run the
real runner against the in-process simulator with fixture providers, exactly like
test_completion_study.py; they are plumbing evidence, never model-performance evidence.
"""
import ast
import collections
import hashlib
import importlib.util
import inspect
import itertools
import json
import pathlib
import random
from copy import deepcopy

import httpx
import pytest

from app.contracts.models import CandidatePolicy, FaultSpec, TrialResult, Usage, canonical_json, content_hash
from app.lab import completion_study
from app.lab.completion_study import (
    CASE_MANIFESTS, DEFAULT_CASE_MANIFEST, MODEL_CALL_RESERVATION, assess_pairs, build_case_manifest,
    case_manifest, planned_slots, queue_completion_study, source_clause, upgrade_case_manifest,
)
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration
from test_completion_study import CompletionFixtureProvider, harness

ROOT = pathlib.Path(__file__).resolve().parents[3]
V4 = 'faultlab-actor-context/v4-indexed-evidence'
OLD_MANIFEST_HASH = '7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483'
# PHASE28_DESIGN.md section 4.1: the stdlib mirror's hash of the declared upgrade-v1 manifest. The
# runner's DECLARED_MANIFEST_HASH is filled from the backend builder at the freeze (F6) and must
# equal this value, or the difference is explained and re-reviewed before the freeze is accepted.
UPGRADE_V1_MIRROR_HASH = 'cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3'
# gate_freeze.py's method: sha256(ast.get_source_segment(src, node) + '\n'), and the line range.
UNCHANGED_FUNCTIONS = {
    'assess_pairs': ('783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2', '106-147'),
    'case_manifest': ('0a5346c86561a032f26b837e5d63a2aefadfa7a43be00ad2f9539b0b2ea3e8e1', '43-83'),
    'planned_slots': ('495f60fc5110326c13fcded6431d47f19c1d4117ecb4b6e3cc14f76a20dae64d', '86-103'),
}
DECLARED_CASES = [
    ('healthy', None, 'COMPLETED'),
    ('upgrade-3', ('F4', 703, {'failure_count': 3}), 'COMPLETED'),
    ('upgrade-2', ('F4', 702, {'failure_count': 2}), 'COMPLETED'),
    ('delayed-upgrade', ('F2', 103, {'completion_delay_ticks': 3, 'terminal_status': 'SUCCEEDED',
                                     'failure_code': None}), 'COMPLETED'),
    ('upgrade-18', ('F4', 718, {'failure_count': 18}), 'SAFE_UNRESOLVED'),
    ('lost-upgrade-response', ('F1', 102, {'response_delay_ms': 1500}), 'COMPLETED'),
    ('terminal-upgrade-rejection', ('F2', 105, {'completion_delay_ticks': 2, 'terminal_status': 'FAILED',
                                                'failure_code': 'UPGRADE_REJECTED'}), 'CORRECTLY_REJECTED'),
]


@pytest.fixture
def anyio_backend():
    return 'asyncio'


# ----------------------------------------------------------------- the old manifest and the gate text

def test_the_default_manifest_and_the_gate_keep_their_hashes_and_their_line_ranges():
    assert content_hash(case_manifest()) == OLD_MANIFEST_HASH
    assert content_hash(build_case_manifest(DEFAULT_CASE_MANIFEST)) == OLD_MANIFEST_HASH
    assert DEFAULT_CASE_MANIFEST == 'notification-v1' and CASE_MANIFESTS['notification-v1'] is case_manifest
    source = pathlib.Path(completion_study.__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    found = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name, (text_sha, lines) in UNCHANGED_FUNCTIONS.items():
        node = found[name]
        segment = ast.get_source_segment(source, node)
        assert hashlib.sha256((segment + '\n').encode('utf-8')).hexdigest() == text_sha, name
        assert f'{node.lineno}-{node.end_lineno}' == lines, name


def test_every_new_definition_is_appended_after_execute():
    source = pathlib.Path(completion_study.__file__).read_text(encoding='utf-8')
    order = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            order.append(node.name)
        elif isinstance(node, ast.Assign):
            order.extend(t.id for t in node.targets if isinstance(t, ast.Name))
    execute = order.index('_execute')
    for name in ('upgrade_case_manifest', 'CASE_MANIFESTS', 'DEFAULT_CASE_MANIFEST', 'build_case_manifest',
                 'SOURCE_CLAUSE_OUTCOMES', 'SOURCE_CLAUSE_REOPENS', 'source_clause'):
        assert order.index(name) > execute, name


# ----------------------------------------------------------------- upgrade-v1

def _spec(kind, seed, parameters, *, tool='update_order', service='orders'):
    return FaultSpec.model_validate({'seed': seed, 'primitives': [{
        'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': 1,
        'parameters': parameters}]}).model_dump(mode='json')


def test_upgrade_v1_is_the_declared_seven_case_manifest():
    manifest = build_case_manifest('upgrade-v1')
    assert manifest == upgrade_case_manifest()
    assert [c['case_id'] for c in manifest['cases']] == [c[0] for c in DECLARED_CASES]
    for case, (case_id, fault, expected) in zip(manifest['cases'], DECLARED_CASES):
        assert case['expected_outcome'] == expected, case_id
        if fault is None:
            assert case['fault_spec']['primitives'] == [] and case['fault_spec']['seed'] == 101
        else:
            assert case['fault_spec'] == _spec(*fault), case_id
        FaultSpec.model_validate(case['fault_spec'])
        assert case['fixture_id'] == 'standard-v1'
    assert (manifest['source_case_id'], manifest['control_case_id'], manifest['repeats']) == ('upgrade-3', 'healthy', 3)
    assert manifest['validation_feedback_forbidden'] is True and manifest['ordinary_policy_accepted'] is False
    old = case_manifest()
    assert manifest['schema_version'] == old['schema_version']
    assert manifest['source_manifest_hash'] == old['source_manifest_hash']
    assert not any(c['case_id'] == 'notification-2' for c in manifest['cases'])
    assert not any(p['target_service'] == 'notifications' for c in manifest['cases']
                   for p in c['fault_spec']['primitives'])
    assert [c['case_id'] for c in manifest['cases'] if c['expected_outcome'] == 'SAFE_UNRESOLVED'] == ['upgrade-18']
    old_cases = {c['case_id']: c for c in old['cases']}
    new_cases = {c['case_id']: c for c in manifest['cases']}
    for kept in ('healthy', 'terminal-upgrade-rejection'):
        assert canonical_json(new_cases[kept]) == canonical_json(old_cases[kept])
    # The source sits at index 1, as notification-2 does in the old manifest.
    assert manifest['cases'][1]['case_id'] == manifest['source_case_id']
    assert len({content_hash(c['fault_spec']) for c in manifest['cases']}) == 7


def _mirror():
    """An independent stdlib mirror of the declared manifest (no app import), from audit/development.json."""
    def cj(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    dev = json.loads((ROOT / 'audit/development.json').read_text(encoding='utf-8'))
    by = {c['case_id']: c for c in dev['cases']}

    def spec(seed, primitives):
        return {'schema_version': 'faultlab/v1', 'scope': 'orders.upgrade_then_confirm/v1', 'seed': seed,
                'primitives': primitives}

    def f4(count):
        return [{'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
                 'parameters': {'failure_count': count}}]
    healthy = deepcopy(by['dev-1']); healthy.update(case_id='healthy', expected_outcome='COMPLETED')
    rejection = deepcopy(by['dev-5'])
    rejection.update(case_id='terminal-upgrade-rejection', expected_outcome='CORRECTLY_REJECTED')
    cases = [healthy]
    for count, expected in ((3, 'COMPLETED'), (2, 'COMPLETED')):
        case = deepcopy(by['dev-6'])
        case.update(case_id=f'upgrade-{count}', name=f'upgrade_transient_{count}', expected_outcome=expected,
                    fault_spec=spec(700 + count, f4(count)))
        cases.append(case)
    delayed = deepcopy(by['dev-3']); delayed.update(case_id='delayed-upgrade', expected_outcome='COMPLETED')
    unrecoverable = deepcopy(by['dev-6'])
    unrecoverable.update(case_id='upgrade-18', name='upgrade_transient_18', expected_outcome='SAFE_UNRESOLVED',
                         fault_spec=spec(718, f4(18)))
    lost = deepcopy(by['dev-2']); lost.update(case_id='lost-upgrade-response', expected_outcome='COMPLETED')
    cases += [delayed, unrecoverable, lost, rejection]
    manifest = {'schema_version': 'faultlab-completion-study/v1', 'source_manifest_hash': dev['manifest_hash'],
                'cases': cases, 'source_case_id': 'upgrade-3', 'control_case_id': 'healthy', 'repeats': 3,
                'validation_feedback_forbidden': True, 'ordinary_policy_accepted': False}
    return hashlib.sha256(cj(manifest).encode('utf-8')).hexdigest()


def test_the_builder_hash_equals_the_stdlib_mirror_and_the_designs_value():
    built = content_hash(build_case_manifest('upgrade-v1'))
    assert built == _mirror() == UPGRADE_V1_MIRROR_HASH


@pytest.mark.parametrize('case_id,change', [
    ('dev-2', {'response_delay_ms': 900}),
    ('dev-3', {'completion_delay_ticks': 4}),
    ('dev-3', {'terminal_status': 'FAILED', 'failure_code': 'UPGRADE_REJECTED'}),
])
def test_a_changed_reviewed_upgrade_case_is_refused(monkeypatch, case_id, change):
    from app.referee import manifests
    real = manifests.load_manifest

    def tampered(split):
        loaded = deepcopy(real(split))
        for case in loaded['cases']:
            if case['case_id'] == case_id:
                case['fault_spec']['primitives'][0]['parameters'].update(change)
        return loaded
    monkeypatch.setattr(manifests, 'load_manifest', tampered)
    assert content_hash(case_manifest()) == OLD_MANIFEST_HASH          # the old manifest does not read them
    with pytest.raises(StoreConflict, match='Reviewed public upgrade cases changed'):
        upgrade_case_manifest()


@pytest.mark.parametrize('manifest_id', ['', 'upgrade-v2', 'UPGRADE-V1', 'notification-2', 'x' * 40])
def test_an_unknown_manifest_id_is_refused(manifest_id):
    with pytest.raises(StoreConflict, match='Unknown completion case manifest'):
        build_case_manifest(manifest_id)


def test_a_manifest_whose_control_is_not_the_literal_healthy_is_refused(monkeypatch):
    def renamed():
        manifest = upgrade_case_manifest()
        manifest['cases'][0]['case_id'] = 'plain'
        manifest['control_case_id'] = 'plain'
        return manifest
    monkeypatch.setitem(CASE_MANIFESTS, 'upgrade-v1', renamed)
    with pytest.raises(StoreConflict, match='literal healthy control'):
        build_case_manifest('upgrade-v1')


def test_planned_slots_for_upgrade_v1_fit_the_frozen_reservation():
    manifest = build_case_manifest('upgrade-v1')
    slots = planned_slots(manifest)
    controls = [s for s in slots if s['stage'] == 'controls']
    assert [s['case_id'] for s in controls] == ['upgrade-3', 'healthy'] * 3
    assert all(s['arm'] == 'B0' for s in controls)
    for stage in ('candidate-1', 'candidate-2'):
        chosen = [s for s in slots if s['stage'] == stage]
        assert len(chosen) == 6 and {s['case_id'] for s in chosen} == {'upgrade-3'}
    validation = [s for s in slots if s['stage'] == 'validation']
    assert len(validation) == 42 and {s['case_id'] for s in validation} == {c['case_id'] for c in manifest['cases']}
    assert len(slots) == 60 and MODEL_CALL_RESERVATION == 60 * 8 + 4 == 484
    scenario = {c['case_id']: content_hash(c['fault_spec']) for c in manifest['cases']}
    assert all(s['scenario_hash'] == scenario[s['case_id']] for s in slots)


# ----------------------------------------------------------------- source_clause: the property

@pytest.fixture(scope='module')
def reference(tmp_path_factory):
    """assess_pairs with its one literal 'notification-2' replaced by 'upgrade-3', loaded as its own
    module beside the same imports. Built from the live source text, so it cannot drift from the gate."""
    text = inspect.getsource(assess_pairs)
    assert text.count("'notification-2'") == 1
    path = tmp_path_factory.mktemp('reference') / 'reference_assess_pairs.py'
    path.write_text('from app.lab.completion_study import content_hash, summarize, valid_trial\n\n\n'
                    + text.replace("'notification-2'", "'upgrade-3'"), encoding='utf-8')
    spec = importlib.util.spec_from_file_location('reference_assess_pairs', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assess_pairs


class Trials:
    """Prebuilt, reused TrialResults so every combination is cheap (assess_pairs never mutates them)."""

    def __init__(self, cases):
        self.cases = cases
        self.cache = {}

    def get(self, case, index, arm, outcome):
        key = (case['case_id'], index, arm, outcome)
        if key not in self.cache:
            suffix = f"{case['case_id']}-{index}-{arm}"
            scheduled = bool(case['fault_spec']['primitives'])
            self.cache[key] = TrialResult(
                episode_id='episode-' + suffix, world_id='world-' + suffix,
                scenario_hash=content_hash(case['fault_spec']), policy_hash=('a' if arm == 'B0' else 'b') * 64,
                arm=arm, trial_index=index, lifecycle='COMPLETED', outcome=outcome, failed_checks=[],
                fault_scheduled=scheduled, fault_triggered=scheduled, usage=Usage())
        return self.cache[key]

    def rows(self, completed):
        """completed[case_id] = (B0 completions, L completions); every other trial gets the case's
        non-completed outcome (SAFE_UNRESOLVED, or CORRECTLY_REJECTED on the refusal case)."""
        rows = []
        for case in self.cases:
            other = 'CORRECTLY_REJECTED' if case['expected_outcome'] == 'CORRECTLY_REJECTED' else 'SAFE_UNRESOLVED'
            for index in range(3):
                for arm, count in zip(('B0', 'L'), completed[case['case_id']]):
                    rows.append({'case_id': case['case_id'],
                                 'trial': self.get(case, index, arm, 'COMPLETED' if index < count else other)})
        return rows


def _check_equal(rows, cases, manifest, reference):
    original = assess_pairs(rows, cases, 'a' * 64, 'b' * 64, validation=True)
    patched = source_clause(original, manifest)
    expected = reference(rows, cases, 'a' * 64, 'b' * 64, validation=True)
    fired = patched.get('source_clause_case')
    assert {k: v for k, v in patched.items() if k != 'source_clause_case'} == expected
    # The key appears exactly when the transposed clause, not the unchanged gate, decided.
    assert (fired is not None) == (expected != original)
    if fired is not None:
        assert fired == manifest['source_case_id'] and expected['decision'] == 'NO_CHANGE'
        assert original['decision'] in ('OBSERVED_IMPROVEMENT', 'NO_CHANGE')
    return patched['decision'], fired is not None, original['decision']


def _reduced(order):
    manifest = build_case_manifest('upgrade-v1')
    by = {c['case_id']: c for c in manifest['cases']}
    cases = [by[name] for name in order]
    return cases, {**manifest, 'cases': cases}


@pytest.mark.parametrize('order', [
    ('healthy', 'upgrade-3', 'upgrade-2', 'upgrade-18'),                      # the manifest's own order
    ('upgrade-2', 'healthy', 'upgrade-3', 'terminal-upgrade-rejection'),      # a regression-able case first
])
def test_source_clause_equals_assess_pairs_with_the_literal_replaced(order, reference):
    cases, manifest = _reduced(order)
    trials = Trials(cases)
    ranges = {'healthy': (2, 3), 'upgrade-3': range(4), 'upgrade-2': range(4), 'upgrade-18': (0, 1),
              'terminal-upgrade-rejection': (0, 1)}
    names = [c['case_id'] for c in cases]
    seen = set()
    for combo in itertools.product(*[list(itertools.product(ranges[n], ranges[n])) for n in names]):
        seen.add(_check_equal(trials.rows(dict(zip(names, combo))), cases, manifest, reference))
    decisions = {s[0] for s in seen}
    assert decisions == {'NO_CHANGE', 'OBSERVED_IMPROVEMENT'}
    # The clause fired both over a stored gain and over a stored NO_CHANGE whose reason it takes over.
    assert {(fired, before) for _, fired, before in seen if fired} == {(True, 'OBSERVED_IMPROVEMENT'),
                                                                      (True, 'NO_CHANGE')}


FULL_MANIFEST_DRAWS = 1000


def test_source_clause_equals_the_reference_on_the_full_manifest_in_its_real_order(reference):
    """Review round 1: the reduced orderings above never run the real 7-case order, delayed-upgrade,
    lost-upgrade-response, or mixed outcomes. Seeded random draws over build_case_manifest('upgrade-v1') in its own
    order: each trial's outcome is drawn on its own (L: COMPLETED, SAFE_UNRESOLVED or CORRECTLY_REJECTED; B0 also
    VIOLATION), biased toward the case's expected outcome, with an occasional candidate check failure (C6)."""
    manifest = build_case_manifest('upgrade-v1')
    cases = manifest['cases']
    rng = random.Random(28)
    cache = {}

    def trial(case, index, arm, outcome, failed):
        key = (case['case_id'], index, arm, outcome, failed)
        if key not in cache:
            suffix = f"{case['case_id']}-{index}-{arm}"
            scheduled = bool(case['fault_spec']['primitives'])
            cache[key] = TrialResult(
                episode_id='episode-' + suffix, world_id='world-' + suffix,
                scenario_hash=content_hash(case['fault_spec']), policy_hash=('a' if arm == 'B0' else 'b') * 64,
                arm=arm, trial_index=index, lifecycle='COMPLETED', outcome=outcome, failed_checks=list(failed),
                fault_scheduled=scheduled, fault_triggered=scheduled, usage=Usage())
        return cache[key]

    seen = collections.Counter()
    reasons = collections.Counter()
    for _ in range(FULL_MANIFEST_DRAWS):
        bias = rng.choice((0.5, 0.8, 0.9, 0.95))
        rows = []
        for case in cases:
            for index in range(3):
                for arm in ('B0', 'L'):
                    pool = ('COMPLETED', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED') + (('VIOLATION',) if arm == 'B0' else ())
                    outcome = case['expected_outcome'] if rng.random() < bias else rng.choice(pool)
                    failed = ('C6',) if arm == 'L' and rng.random() < 0.002 else ()
                    rows.append({'case_id': case['case_id'], 'trial': trial(case, index, arm, outcome, failed)})
        decision, fired, before = _check_equal(rows, cases, manifest, reference)
        seen[(decision, fired, before)] += 1
        reasons[reference(rows, cases, 'a' * 64, 'b' * 64, validation=True)['reason']] += 1
    # The draws reach every branch that matters: both decisions, the clause over a stored gain and over a stored
    # NO_CHANGE whose reason it takes over, a candidate check failure, and a regression. It never raises a decision.
    assert {decision for decision, _, _ in seen} == {'NO_CHANGE', 'OBSERVED_IMPROVEMENT'}
    assert seen[('NO_CHANGE', True, 'OBSERVED_IMPROVEMENT')] and seen[('NO_CHANGE', True, 'NO_CHANGE')], seen
    assert not seen[('OBSERVED_IMPROVEMENT', False, 'NO_CHANGE')] and not any(
        fired and decision != 'NO_CHANGE' for decision, fired, _ in seen)
    assert reasons['Candidate safety or truthfulness check failed'] and reasons[
        'Expected outcome regressed within a validation case'], reasons


def test_source_clause_equals_the_reference_on_violations_incomplete_pairs_and_source_gates(reference):
    cases, manifest = _reduced(('healthy', 'upgrade-3', 'upgrade-2', 'upgrade-18'))
    trials = Trials(cases)
    decisions = set()
    for source_l in range(4):
        completed = {'healthy': (3, 3), 'upgrade-3': (0, source_l), 'upgrade-2': (0, 3), 'upgrade-18': (0, 0)}
        rows = trials.rows(completed)
        # a candidate check failure: decided before the per-case loop, in both
        violated = list(rows)
        index = next(i for i, r in enumerate(violated) if r['case_id'] == 'upgrade-2' and r['trial'].arm == 'L')
        violated[index] = {**violated[index],
                           'trial': violated[index]['trial'].model_copy(update={'failed_checks': ['C6']})}
        decisions.add(_check_equal(violated, cases, manifest, reference)[0])
        # incomplete pairs
        decisions.add(_check_equal(rows[:-1], cases, manifest, reference)[0])
        # a source-gate result (validation=False) is never reopened
        source_rows = [r for r in rows if r['case_id'] == 'upgrade-3']
        gate = assess_pairs(source_rows, [cases[1]], 'a' * 64, 'b' * 64)
        assert source_clause(gate, manifest) is gate
    assert decisions == {'NO_CHANGE', 'INCOMPLETE'}


def test_source_clause_rejects_a_source_below_three_of_three_that_the_unchanged_gate_accepts():
    cases, manifest = _reduced(('healthy', 'upgrade-3', 'upgrade-2', 'upgrade-18'))
    rows = Trials(cases).rows({'healthy': (3, 3), 'upgrade-3': (0, 2), 'upgrade-2': (0, 3), 'upgrade-18': (0, 0)})
    original = assess_pairs(rows, cases, 'a' * 64, 'b' * 64, validation=True)
    assert original['decision'] == 'OBSERVED_IMPROVEMENT'
    patched = source_clause(original, manifest)
    assert patched['decision'] == 'NO_CHANGE' and patched['source_clause_case'] == 'upgrade-3'
    assert patched['reason'] == 'Healthy or source completion was not preserved in all trials'
    assert patched['by_case'] == original['by_case'] and 'source_clause_case' not in original


def test_source_clause_is_the_identity_for_the_default_manifest():
    manifest = case_manifest()
    cases = manifest['cases']
    trials = Trials(cases)
    names = [c['case_id'] for c in cases]
    for source_l, sibling_l in itertools.product(range(4), range(4)):
        completed = {name: (0, 0) for name in names}
        completed.update({'healthy': (3, 3), 'notification-2': (0, source_l), 'notification-3': (1, sibling_l),
                          'notification-1': (3, 3), 'lost-notification-response': (3, 3)})
        result = assess_pairs(trials.rows(completed), cases, 'a' * 64, 'b' * 64, validation=True)
        assert source_clause(result, manifest) is result


# ----------------------------------------------------------------- queueing and the record

def _state(c, campaign):
    ledger = c.ledgers.get(campaign.campaign_id)
    return (dict(ledger.reservations) if ledger else {}, c.get(campaign.campaign_id).state, c.active_id,
            c.store.list_records('completion_studies'), c.store.list_records('completion_plans'))


@pytest.mark.anyio
@pytest.mark.parametrize('manifest_id,replay', [('upgrade-v9', False), ('', False), ('upgrade-v1', True)])
async def test_refusals_happen_before_any_state_is_taken(tmp_path, manifest_id, replay):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        kwargs = {'case_manifest_id': manifest_id}
        match = 'Unknown completion case manifest'
        if replay:
            # A saved non-empty policy, so the refusal is the manifest rule, not the replay lookup.
            saved = c.policies.proposal(CandidatePolicy.model_validate(
                {'parent_version': c.policies.baseline().version, 'rules': [UPGRADE_RESEND]}),
                parent=c.policies.baseline().version, raw='fixture', episode_ids=[])
            kwargs['replay_policy_version'] = saved.version
            match = 'Replay runs only the default manifest'
        before = _state(c, campaign)
        assert before[1] == 'IDLE' and not before[3] and not before[4]
        with pytest.raises(StoreConflict, match=match):
            await queue_completion_study(c, campaign.campaign_id, **kwargs)
        assert _state(c, campaign) == before
        assert not c.tasks and provider.calls == 0
    finally:
        await client.aclose(); await c.close()


# Today's record keys, as queue_completion_study wrote them before Phase 28.
TODAYS_RECORD_KEYS = {
    'schema_version', 'study_id', 'campaign_id', 'status', 'stage', 'decision', 'reason',
    'ordinary_policy_accepted', 'configuration_hash', 'incumbent_hash', 'model', 'manifest', 'manifest_hash',
    'evidence_protocol', 'actor_context_protocol', 'replay_of', 'replay_policy_hash', 'reserved_model_calls',
    'slots', 'trial_rows', 'candidates', 'evidence', 'telemetry', 'validation_assessment',
    'charged_model_calls', 'usage', 'created_at'}


@pytest.mark.anyio
async def test_a_default_request_writes_todays_record_and_passes_every_check(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path, CompletionFixtureProvider(recover_baseline=True))
    try:
        queued = await queue_completion_study(c, campaign.campaign_id)
        assert set(queued) == TODAYS_RECORD_KEYS and 'case_manifest_id' not in queued
        assert queued['manifest_hash'] == OLD_MANIFEST_HASH
        assert set(c.store.get_record('completion_plans', queued['study_id'])) == TODAYS_RECORD_KEYS
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        # The baseline recovers here, so the declared gap does not reproduce: NO_CHANGE after the six
        # controls, with check() run before every slot and never raising.
        assert result['status'] == 'COMPLETED' and result['decision'] == 'NO_CHANGE', result
        assert 'error_type' not in result and len(result['trial_rows']) == 6
        assert [r['case_id'] for r in result['trial_rows']] == ['notification-2', 'healthy'] * 3
    finally:
        await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_an_explicit_default_id_is_recorded_and_runs_the_default_manifest(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path, CompletionFixtureProvider(recover_baseline=True))
    try:
        queued = await queue_completion_study(c, campaign.campaign_id, case_manifest_id='notification-v1')
        assert queued['case_manifest_id'] == 'notification-v1' and queued['manifest_hash'] == OLD_MANIFEST_HASH
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        assert result['status'] == 'COMPLETED' and 'error_type' not in result
    finally:
        await client.aclose(); await c.close()


# ----------------------------------------------------------------- upgrade-v1 through _execute

UPGRADE_RESEND = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain', 'steps': [
    {'op': 'wait_ticks', 'ticks': 1, 'only_if': 'upgrade_outcome_uncertain'},
    {'op': 'retry_original_request', 'service': 'orders', 'only_if': 'upgrade_outcome_uncertain'}]}


class UpgradeFixtureProvider(CompletionFixtureProvider):
    """The fixture Actor never re-sends a failed upgrade; the fixture Mechanic proposes one re-send."""

    async def complete(self, messages, **kwargs):
        if kwargs.get('role') == 'mechanic':
            self.calls += 1
            context = json.loads(messages[1]['content'])
            self.mechanic_inputs.append(deepcopy(context))
            output = {'candidate': {'scope': 'orders.upgrade_then_confirm/v1',
                                    'parent_version': context['parent_version'], 'rules': [UPGRADE_RESEND]},
                      'explanation': 'Handwritten offline fixture, not a learned result.'}
            return RuntimeGeneration(canonical_json(output), 'openai/gpt-oss-120b',
                                     input_tokens=100, output_tokens=30, cost_usd=.0001)
        return await super().complete(messages, **kwargs)


def _lose_one_source_completion(c):
    """Validation, upgrade-3, L, trial 2 is re-labelled SAFE_UNRESOLVED after it runs: the unchanged
    gate still sees a strict gain, and only the transposed source clause can refuse it."""
    run = c.runner.run

    async def wrapped(*args, **kwargs):
        trial = await run(*args, **kwargs)
        plan = c.store.list_records('completion_plans')[0]
        slot = next(s for s in plan['slots'] if s['episode_id'] == trial.episode_id)
        if (slot['stage'], slot['case_id'], slot['arm'], slot['trial_index']) == ('validation', 'upgrade-3', 'L', 2):
            return trial.model_copy(update={'outcome': 'SAFE_UNRESOLVED'})
        return trial
    c.runner.run = wrapped


@pytest.mark.anyio
@pytest.mark.parametrize('lose_one', [False, True])
async def test_an_upgrade_v1_study_runs_every_stage_on_its_own_source(tmp_path, lose_one):
    c, campaign, provider, remote, client = await harness(tmp_path, UpgradeFixtureProvider())
    try:
        if lose_one:
            _lose_one_source_completion(c)
        queued = await queue_completion_study(c, campaign.campaign_id, actor_context_protocol=V4,
                                              case_manifest_id='upgrade-v1')
        manifest = build_case_manifest('upgrade-v1')
        assert queued['case_manifest_id'] == 'upgrade-v1' and queued['manifest'] == manifest
        assert queued['manifest_hash'] == content_hash(manifest) == UPGRADE_V1_MIRROR_HASH
        assert set(queued) == TODAYS_RECORD_KEYS | {'case_manifest_id'}
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        assert 'error_type' not in result and result['status'] == 'COMPLETED', result
        rows = result['trial_rows']
        assert [r['case_id'] for r in rows if r['stage'] == 'controls'] == ['upgrade-3', 'healthy'] * 3
        assert {r['case_id'] for r in rows if r['stage'] == 'candidate-1'} == {'upgrade-3'}
        assert len([r for r in rows if r['stage'] == 'validation']) == 42
        cases = {case['case_id']: case for case in manifest['cases']}
        supplied = provider.mechanic_inputs[0]
        assert supplied['source_fault_spec'] == cases['upgrade-3']['fault_spec']
        assert supplied['control_fault_spec'] == cases['healthy']['fault_spec']
        assert result['candidates'][0]['source_assessment']['decision'] == 'SOURCE_QUALIFIED'
        va = result['validation_assessment']
        assert va['by_case']['upgrade-2']['L']['completed'] - va['by_case']['upgrade-2']['B0']['completed'] >= 2
        candidate = c.policies.get(result['selected_candidate_version'])
        if lose_one:
            assert va['by_case']['upgrade-3']['L']['completed'] == 2
            assert result['decision'] == va['decision'] == 'NO_CHANGE'
            assert va['source_clause_case'] == 'upgrade-3'
            assert va['reason'] == result['reason'] == 'Healthy or source completion was not preserved in all trials'
            assert result['candidates'][0]['decision'] == 'NO_CHANGE' and candidate.decision == 'REJECTED'
        else:
            assert va['by_case']['upgrade-3']['L']['completed'] == 3
            assert result['decision'] == va['decision'] == 'OBSERVED_IMPROVEMENT'
            assert 'source_clause_case' not in va and candidate.decision == 'PROPOSED'
        # Never promoted, never activated, whatever the decision.
        assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
        assert not c.store.list_records('promotion_decisions')
        assert all(p.decision != 'ACCEPTED' for p in c.policies.list())
    finally:
        await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_a_study_whose_recorded_manifest_no_longer_rebuilds_stops_before_any_slot(tmp_path, monkeypatch):
    c, campaign, provider, remote, client = await harness(tmp_path, UpgradeFixtureProvider())
    try:
        changed = build_case_manifest('upgrade-v1')
        changed['repeats'] = 4
        # The id is resolved through the registry at every check(): a changed builder is caught.
        monkeypatch.setitem(CASE_MANIFESTS, 'upgrade-v1', lambda: deepcopy(changed))
        original = content_hash(changed)
        queued = await queue_completion_study(c, campaign.campaign_id, actor_context_protocol=V4,
                                              case_manifest_id='upgrade-v1')
        assert queued['manifest_hash'] == original
        changed['repeats'] = 5
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        assert result['status'] == 'INCOMPLETE' and result['error_type'] == 'StoreConflict'
        assert not result['trial_rows'] and provider.calls == 0
    finally:
        await client.aclose(); await c.close()


# ----------------------------------------------------------------- the HTTP route

@pytest.mark.anyio
async def test_the_route_passes_the_manifest_id_and_still_forbids_unknown_fields(tmp_path):
    from fastapi import FastAPI
    from app.lab.api import create_router
    c, campaign, provider, remote, client = await harness(tmp_path, UpgradeFixtureProvider())
    try:
        app = FastAPI(); app.include_router(create_router(lambda: c))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://lab') as http:
            path = f'/api/campaigns/{campaign.campaign_id}/completion-study'
            extra = await http.post(path, json={'execute_live': True, 'case_manifest': 'upgrade-v1'})
            assert extra.status_code == 422
            too_long = await http.post(path, json={'execute_live': True, 'case_manifest_id': 'u' * 41})
            assert too_long.status_code == 422
            unknown = await http.post(path, json={'execute_live': True, 'case_manifest_id': 'upgrade-v9'})
            # The StoreConflict itself, not any error: a crash in the builder would map to 503 (review round 1).
            assert unknown.status_code == 409, unknown.text
            assert unknown.json()['error']['message'] == 'Unknown completion case manifest'
            assert not c.store.list_records('completion_studies') and c.active_id is None
            response = await http.post(path, json={'execute_live': True, 'actor_context_protocol': V4,
                                                   'case_manifest_id': 'upgrade-v1'})
            assert response.status_code == 202, response.text
            body = response.json()
            assert body['case_manifest_id'] == 'upgrade-v1' and body['manifest']['source_case_id'] == 'upgrade-3'
            await c.tasks[body['study_id']]
            status = (await http.get(f"/api/completion-studies/{body['study_id']}")).json()
            assert status['case_manifest_id'] == 'upgrade-v1' and status['status'] == 'COMPLETED'
    finally:
        await client.aclose(); await c.close()
