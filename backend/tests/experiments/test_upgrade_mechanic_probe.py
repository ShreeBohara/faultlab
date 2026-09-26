"""Offline checks of the Phase 28a upgrade-side Mechanic probe. No provider call, no .env read, no store write."""
import ast
import asyncio
import dataclasses
import importlib.util
import json
import os
import pathlib
import signal
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('upgrade_mechanic_probe', ROOT / 'scripts/experiments/upgrade_mechanic_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['upgrade_mechanic_probe'] = probe
SPEC.loader.exec_module(probe)
s2 = probe.s2

from app.agents.mechanic import Mechanic  # noqa: E402
from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.providers.runtime import RuntimeProvider, RuntimeProviderError  # noqa: E402

STORE = ROOT / 'artifacts/lab.sqlite3'


@pytest.fixture(autouse=True)
def no_real_process_list(monkeypatch):
    """No test reads the machine's real process list; the process guard is tested with injected rows."""
    monkeypatch.setattr(probe, 'process_list', lambda: [])


def _policy(rules, parent='policy-v0', explanation='A bounded recovery policy.'):
    return json.dumps({'candidate': {'scope': 'orders.upgrade_then_confirm/v1', 'parent_version': parent,
                                     'rules': rules}, 'explanation': explanation})


RESEND = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
          'steps': [{'op': 'wait_ticks', 'ticks': 1}, {'op': 'read_current_operation'},
                    {'op': 'retry_original_request', 'service': 'orders', 'only_if': 'upgrade_outcome_uncertain'}]}
PENDING_RESEND = {'hook': 'after_upgrade_response', 'when': 'upgrade_receipt_missing',
                  'steps': [{'op': 'read_current_operation'},
                            {'op': 'retry_original_request', 'service': 'orders', 'only_if': 'current_operation_pending'}]}
READ_ONLY = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
             'steps': [{'op': 'read_current_operation'}]}
NOTIFY = {'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
          'steps': [{'op': 'retry_original_request', 'service': 'notifications'}]}
DEFER = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain', 'steps': [{'op': 'defer_unresolved'}]}
FIRING = _policy([RESEND])
DEAD = _policy([PENDING_RESEND])
NO_STEP = _policy([READ_ONLY])
NO_CHANGE = json.dumps({'no_change_reason': 'nothing supported'})


def _tree_is_the_declared_configuration():
    try:
        settings = probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)
        return probe.configuration_pins(settings)['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    except Exception:
        return False


needs_store = pytest.mark.skipif(not STORE.exists() or not _tree_is_the_declared_configuration(),
                                 reason='needs the local lab stores and the tree Phase 28a is pinned to')


@pytest.fixture(scope='module')
def real():
    if not STORE.exists() or not _tree_is_the_declared_configuration():
        pytest.skip('needs the local lab stores and the tree Phase 28a is pinned to')
    plan, prompts, inputs = probe.build_plan()
    return SimpleNamespace(plan=plan, prompts=prompts, inputs=inputs)


@pytest.fixture(scope='module')
def dry_settings():
    return probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)


def _context(prompt):
    context = json.loads(prompt['messages'][1]['content'])
    context.pop('output_schema')
    return context


# ---------------------------------------------------------------- pins, constants and imports

def test_the_imported_harnesses_are_pinned_and_a_changed_one_refuses(tmp_path, monkeypatch):
    assert probe.pinned_imports_problem() is None
    assert probe.sha256_file(probe.PHASE25_HARNESS) == probe.PHASE25_HARNESS_SHA256 == '28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0'
    assert probe.sha256_file(probe.PHASE17_RUNNER) == probe.PHASE17_RUNNER_SHA256
    changed = tmp_path / 'slot2_probe.py'
    changed.write_bytes(probe.PHASE25_HARNESS.read_bytes() + b'\n# changed\n')
    with pytest.raises(ImportError, match='none of it was run'):
        probe._load_pinned(changed, probe.PHASE25_HARNESS_SHA256, 'faultlab_test_changed')
    monkeypatch.setattr(probe, 'PHASE25_HARNESS', changed)
    assert 'not the pinned file' in probe.pinned_imports_problem()


def test_the_declared_design_constants():
    assert probe.K_CONTEXTS == 30 and probe.PLANNED_CALLS == 60 and probe.TEMPERATURE == 0
    assert probe.HARD_SPEND_CAP == 5.0 and probe.PER_REQUEST_DOLLAR_BOUND == 0.04984
    assert probe.PLANNED_CALLS * probe.PER_REQUEST_DOLLAR_BOUND == pytest.approx(2.9904)
    assert probe.DECLARED_CONFIGURATION_HASH.startswith('2cf63e93')
    assert probe.DECLARED_FREEZE_SHA256.startswith('8994e962')
    assert probe.PROTOCOL == ROOT / 'docs/part2/PHASE28A_EXPERIMENT.md'
    assert probe.REVIEW_RECORD == 'artifacts/phase28a-2026-09-25/review.json'
    assert probe.PHASE_PREFIX == 'phase28a-' and probe.CLAIM_DIR == 'phase28a-live-claims'
    # PHASE28_DESIGN.md §4.1 row 2: the design's stdlib mirror of upgrade-3's fault spec, byte for byte.
    mirror = {'schema_version': 'faultlab/v1', 'scope': 'orders.upgrade_then_confirm/v1', 'seed': 703,
              'primitives': [{'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders',
                              'occurrence': 1, 'parameters': {'failure_count': 3}}]}
    assert canonical_json(probe.source_fault_spec()) == canonical_json(mirror)
    assert content_hash(probe.source_fault_spec()) == probe.SOURCE_FAULT_SPEC_CONTENT_HASH
    assert probe.control_fault_spec() == {'schema_version': 'faultlab/v1', 'scope': 'orders.upgrade_then_confirm/v1',
                                          'seed': 101, 'primitives': []}
    assert probe.controls_order() == ['upgrade-3', 'healthy'] * 3
    # No excluded or sealed file is ever hashed by the freeze check.
    for name in probe.EXTRA_FREEZE_FILES + s2.FREEZE_FILES:
        assert 'checks.py' not in name and 'promotion' not in name and 'final-audit' not in name
    assert not any(kind.startswith('private') for kind in probe.READ_KINDS)


def test_only_the_declared_names_are_read_from_the_pinned_harnesses():
    tree = ast.parse((ROOT / 'scripts/experiments/upgrade_mechanic_probe.py').read_text())
    used = {'s2': set(), 'rfl': set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in used:
            used[node.value.id].add(node.attr)
    assert used['rfl'] == {'contains_step'}
    assert used['s2'] == {
        'EXPECTED_MECHANIC_MODEL', 'EXPECTED_PROJECT', 'DECLARED_SETTINGS', 'DECLARED_SETTINGS_SHA256',
        'MECHANIC_MAX_OUTPUT_TOKENS', 'MECHANIC_TIMEOUT_SECONDS', 'RESEND_CODES', 'PlanningError', 'sha256_file',
        'sha256_text', 'write_json', 'load_results', 'status_block', 'entry_delivered', 'delivered_generations',
        'backend_status', 'settings_from_file', 'configuration_pins', 'check_pins', 'process_list', 'SpendGuard',
        'PER_REQUEST_DOLLAR_BOUND', 'DECLARED_CONFIGURATION_HASH', 'wilson', 'before_cutoff', 'mechanic_messages',
        'request_digest', 'request_body', 'check_freeze', 'FREEZE_FINGERPRINTS', '_service', 'run_hook',
        'live_experiment_processes', 'RequestSender', 'Recorder', 'classify_response', 'parse_policy'}


def test_the_format_repair_instruction_is_mechanic_generates_verbatim():
    source = (ROOT / 'backend/app/agents/mechanic.py').read_text()
    assert f"'instruction':'{probe.FORMAT_REPAIR_INSTRUCTION}'" in source


class _Ledger:
    def consume_call(self, **_):
        pass

    def reconcile(self, _):
        pass


class _Store:
    def put_record(self, *_, **__):
        pass


class _MechanicProvider:
    """A provider for the real Mechanic._generate: it records the messages of every call."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def role_model(self, role):
        return probe.EXPECTED_MECHANIC_MODEL

    async def complete(self, messages, **_):
        self.calls.append(json.loads(json.dumps(messages)))
        return SimpleNamespace(content=self.script.pop(0), model_id=probe.EXPECTED_MECHANIC_MODEL, input_tokens=1,
                               output_tokens=1, cost_usd=None)


def test_the_first_request_and_the_format_repair_are_what_the_real_mechanic_sends(real):
    prompt = real.prompts[real.plan['requests'][0]['messages_hash']]
    context = _context(prompt)
    provider = _MechanicProvider(['not json', NO_CHANGE])
    _, result, raws = asyncio.run(Mechanic(provider, _Store(), _Ledger()).propose_completion(context))
    assert raws == ['not json', NO_CHANGE] and result is not None
    assert provider.calls[0] == prompt['messages'] == s2.mechanic_messages(context)
    assert provider.calls[1] == probe.repair_messages(prompt['messages'], 'not json', probe.validation_errors('not json'))
    # A first output that validates gets no repair, in the Mechanic and in the probe.
    provider = _MechanicProvider([FIRING])
    asyncio.run(Mechanic(provider, _Store(), _Ledger()).propose_completion(context))
    assert len(provider.calls) == 1 and probe.validation_errors(FIRING) == []


# ---------------------------------------------------------------- the real stores (read-only)

def test_the_pools_are_the_declared_episodes(real):
    plan = real.plan
    assert plan['pool_sizes'] == {'upgrade-3': 19, 'healthy': 89}
    assert plan['pool_sizes_by_store'] == {'upgrade-3': {'phase20': 8, 'phase26': 11},
                                           'healthy': {'phase20': 3, 'phase26': 2, 'main': 84}}
    upgrade = plan['pools']['upgrade-3']
    assert all(e['outcome'] != 'COMPLETED' and e['failed_checks'] == [] for e in upgrade)
    assert all(e['outcome'] == 'COMPLETED' for e in plan['pools']['healthy'])
    assert not {e['episode_id'] for e in upgrade} & {e['episode_id'] for e in plan['pools']['healthy']}
    completed = [k for store in ('phase20', 'phase26') for k, v in plan['excluded'][store].items()
                 if k.startswith('upgrade-3:completed') and v == 1]
    assert len(completed) == 2
    for episode_id in [e['episode_id'] for role in plan['pools'] for e in plan['pools'][role]]:
        trial, bundle = real.inputs['rows'][episode_id]
        assert trial.arm == 'B0' and trial.policy_hash == probe.B0_POLICY_HASH and bundle.source == 'local_only'
        assert probe.valid_trial(trial)
    # Review round 1: every pool entry names its configuration. Phase 20's episodes ran on 0a33aa51... (before the
    # Phase 22 freeze); its stored record differs from 2cf63e93...'s only in algorithm_hash and runtime_hash.
    phase20 = '0a33aa51cf125cadcfc1dfeaf640950f9e18e0dd89576ec24202a414893aee98'
    for role in plan['pools']:
        for entry in plan['pools'][role]:
            assert entry['configuration_hash'] == (phase20 if entry['store'] == 'phase20'
                                                   else probe.DECLARED_CONFIGURATION_HASH)
    assert plan['pool_configurations'] == {
        phase20: {'episodes': {'upgrade-3': 8, 'healthy': 3}, 'episodes_by_store': {'phase20': 11},
                  'fields_differing_from_declared': ['algorithm_hash', 'runtime_hash']},
        probe.DECLARED_CONFIGURATION_HASH: {'episodes': {'upgrade-3': 11, 'healthy': 86},
                                            'episodes_by_store': {'main': 84, 'phase26': 13},
                                            'fields_differing_from_declared': []}}
    assert any('0a33aa51' in line for line in plan['declared_input_differences'])


def test_no_private_record_is_ever_read_and_every_store_is_read_only(monkeypatch):
    if not STORE.exists() or not _tree_is_the_declared_configuration():
        pytest.skip('needs the local lab stores')
    seen = []
    real_execute = probe.StoreReader._execute

    def recording(self, sql, params=()):
        seen.append((self.label, sql, tuple(params)))
        return real_execute(self, sql, params)
    monkeypatch.setattr(probe.StoreReader, '_execute', recording)
    probe.collect_inputs()
    assert {label for label, _, _ in seen} == {'main', 'phase20', 'phase26'}
    for _, sql, params in seen:
        assert 'private' not in sql.lower() and 'private' not in json.dumps(params)
        if ' from records ' in f' {sql.lower()} ':
            assert 'kind=?' in sql.replace(' ', '') and params[0] in probe.READ_KINDS
        else:
            assert ' from events ' in f' {sql.lower()} '
    reader = probe.open_main()
    try:
        with pytest.raises(probe.PlanningError):
            reader.record('private_episode_inputs', 'x')
        with pytest.raises(sqlite3.OperationalError):
            reader.connection.execute('create table probe_write_test(a)')
    finally:
        reader.close()
    reader = probe.open_static('phase20')
    try:
        with pytest.raises(sqlite3.OperationalError):
            reader.connection.execute('create table probe_write_test(a)')
    finally:
        reader.close()


def test_the_positive_controls_hold(real):
    positive = real.plan['positive_controls']
    bundle, context = positive['bundle_rebuild'], positive['context_rebuild']
    assert bundle['episodes_checked'] == bundle['equal'] == 174 and bundle['differing'] == []
    assert context['studies'] == 30 and context['studies_checked'] == context['byte_equal_apart_from_source'] == 26
    labels = {v['policy_hash'][:8]: v for v in positive['auditor_validation']}
    assert labels['b8d18218']['static_label'] == 'CAN_FIRE' and labels['b8d18218']['dynamic_fired'] == 18
    assert labels['dd62c857']['static_present'] is False and labels['dd62c857']['dynamic_not_fired'] == 27
    assert labels['711bddb6']['static_present'] is False and labels['711bddb6']['dynamic_not_fired'] == 18
    assert all(v['agrees'] and v['content_hash_matches'] for v in positive['auditor_validation'])
    # Review round 1: only the manual-reference policy is informative; the other two have no orders re-send and
    # cannot disagree. Three labels have no dynamic validation.
    assert {k: v['informative'] for k, v in labels.items()} == {'b8d18218': True, 'dd62c857': False, '711bddb6': False}
    assert positive['auditor_validation_scope'] == {
        'policies': 3, 'informative_policies': 1, 'policies_without_an_orders_re_send_cannot_disagree': 2,
        'labels_validated': ['CAN_FIRE@after_upgrade_response'],
        'labels_not_validated': ['CAN_FIRE@before_final_report', 'CANNOT_FIRE', 'UNCLEAR']}
    assert positive['hook_reach'] == {**positive['hook_reach'], 'source_episodes': 19, 'actor_sent_confirmation': 0,
                                      'report_submitted': 19}
    assert positive['control_spec']['equals_every_phase23_manifest'] is True


@pytest.mark.parametrize('change', [
    lambda p: p['bundle_rebuild'].update(equal=p['bundle_rebuild']['equal'] - 1),
    lambda p: p['context_rebuild'].update(byte_equal_apart_from_source=25),
    lambda p: p['auditor_validation'][0].update(agrees=False),
    # Review round 1: the vacuous rows alone are not a validation; the one informative row must be there and fire.
    lambda p: p.update(auditor_validation=[v for v in p['auditor_validation'] if not v['static_present']]),
    lambda p: [v.update(dynamic_fired=0) for v in p['auditor_validation'] if v['static_present']],
    lambda p: [v.update(static_fires_at='before_final_report') for v in p['auditor_validation'] if v['static_present']],
    lambda p: p['hook_reach'].update(actor_sent_confirmation=1),
    lambda p: p['source_spec'].update(content_hash='0' * 64),
    lambda p: p['control_spec'].update(equals_every_phase23_manifest=False),
])
def test_a_failed_positive_control_refuses_the_plan(real, change):
    inputs = {**real.inputs, 'positive': json.loads(json.dumps(real.inputs['positive']))}
    change(inputs['positive'])
    with pytest.raises(probe.PlanningError, match='positive control'):
        probe.assemble_plan(inputs)


def test_every_request_is_the_loops_slot1_request(real):
    plan, prompts = real.plan, real.prompts
    assert len(plan['requests']) == 30 and len(prompts) == 30
    keys = {'campaign_id', 'study_id', 'objective', 'parent_version', 'source_fault_spec', 'control_fault_spec',
            'runtime_contract', 'development_evidence', 'observed_outcomes', 'candidate_history'}
    for request in plan['requests']:
        prompt = prompts[request['messages_hash']]
        context = _context(prompt)
        assert set(context) == keys and context['candidate_history'] == []
        assert context['parent_version'] == 'policy-v0' and context['objective'] == 'faultlab-completion-study/v1'
        assert context['source_fault_spec'] == probe.source_fault_spec()
        assert context['control_fault_spec'] == probe.control_fault_spec()
        assert (context['campaign_id'], context['study_id']) == probe.probe_ids(request['context'])
        assert context['runtime_contract'] == json.loads(canonical_json(probe.runtime_contract()))
        rows = context['development_evidence']['episodes']
        assert [r['episode_id'] for r in rows] == [c['episode_id'] for c in request['controls']]
        assert [c['case'] for c in request['controls']] == probe.controls_order()
        assert all(r['source'] == 'local_only' for r in rows)
        assert context['development_evidence']['format'] == probe.COMPACT_EVIDENCE_V2
        assert prompt['messages'] == s2.mechanic_messages(context)
        assert content_hash(prompt['messages']) == request['messages_hash']
        assert s2.request_digest(s2.request_body(prompt['messages'], 0)) == request['request_hash']
        assert s2.request_body(prompt['messages'], 0)['temperature'] == 0
        assert request['input_token_bound'] <= probe.MODEL_INPUT_TOKEN_LIMIT
        # The context is rebuilt from the same rows byte for byte.
        again = probe.proposal_context(campaign_id=context['campaign_id'], study_id=context['study_id'],
                                       source_spec=probe.source_fault_spec(), control_spec=probe.control_fault_spec(),
                                       rows=[real.inputs['rows'][c['episode_id']] for c in request['controls']])
        assert canonical_json(again) == canonical_json(context)
        assert 'phase28a' not in canonical_json(context) and 'probe' not in context['study_id']


def test_the_draws_follow_the_declared_rule(real):
    plan = real.plan
    upgrade = [frozenset(c['episode_id'] for c in r['controls'] if c['case'] == 'upgrade-3') for r in plan['requests']]
    healthy = [frozenset(c['episode_id'] for c in r['controls'] if c['case'] == 'healthy') for r in plan['requests']]
    assert all(len(t) == 3 for t in upgrade + healthy)
    assert len(set(upgrade)) == 30 and len(set(healthy)) == 30
    assert plan['draws']['caps'] == {'upgrade-3': 5, 'healthy': 2}
    assert max(plan['draws']['uses']['upgrade-3'].values()) <= 5 and max(plan['draws']['uses']['healthy'].values()) <= 2
    assert sum(plan['draws']['uses']['upgrade-3'].values()) == sum(plan['draws']['uses']['healthy'].values()) == 90
    ids = [e['episode_id'] for e in plan['pools']['upgrade-3']]
    ordered, cap, _ = probe.draw_triples(ids, 'upgrade-3')
    assert [frozenset(t) for t in ordered] == upgrade and cap == 5


def test_the_plan_is_deterministic_and_the_protocol_is_not_in_it(real, tmp_path, monkeypatch):
    first, _ = probe.assemble_plan(real.inputs)
    assert probe.plan_hash(first) == probe.plan_hash(real.plan)
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('one')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    again, _ = probe.assemble_plan(real.inputs)
    protocol.write_text('two')
    assert probe.plan_hash(again) == probe.plan_hash(probe.assemble_plan(real.inputs)[0]) == probe.plan_hash(first)
    assert probe.plan_hash(probe.assemble_plan(real.inputs, spend_cap=4.0)[0]) != probe.plan_hash(first)
    monkeypatch.setattr(probe, 'SAMPLE_SEED', 'another-seed')
    assert probe.plan_hash(probe.assemble_plan(real.inputs)[0]) != probe.plan_hash(first)


def test_the_dry_plan_never_reads_env_and_refuses_an_altered_settings_file(tmp_path, monkeypatch):
    if not STORE.exists() or not _tree_is_the_declared_configuration():
        pytest.skip('needs the local lab stores')
    seen = []
    real_loader = probe.settings_from_file

    def watching(path, *, env_path):
        seen.append(env_path)
        return real_loader(path, env_path=env_path)
    monkeypatch.setattr(probe, 'settings_from_file', watching)
    probe.collect_inputs()
    assert seen == [os.devnull]
    altered = tmp_path / 'settings.json'
    altered.write_text((ROOT / probe.DECLARED_SETTINGS).read_text() + ' ')
    with pytest.raises(probe.PlanningError, match='settings file'):
        probe.collect_inputs(settings_path=altered)


def test_main_prints_a_dry_plan_and_sends_nothing(real, capsys):
    assert probe.main([]) == 0
    out = capsys.readouterr().out
    assert probe.plan_hash(real.plan) in out and 'Dry plan only' in out


# ---------------------------------------------------------------- the static check (pure)

@pytest.mark.parametrize('rules,label,fires_at,reason', [
    ([RESEND], 'CAN_FIRE', 'after_upgrade_response', None),
    ([{'hook': 'after_upgrade_response', 'when': 'always',
       'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'CAN_FIRE', 'after_upgrade_response', None),
    ([PENDING_RESEND], 'CANNOT_FIRE', None, 'pitfall 77'),
    ([{'hook': 'after_upgrade_response', 'when': 'current_operation_pending',
       'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'CANNOT_FIRE', None, 'pitfall 77'),
    ([{'hook': 'before_final_report', 'when': 'upgrade_receipt_missing',
       'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'CAN_FIRE', 'before_final_report', None),
    ([DEFER, {'hook': 'before_final_report', 'when': 'always',
              'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'CANNOT_FIRE', None, 'closed business'),
    ([{'hook': 'after_upgrade_response', 'when': 'always',
       'steps': [{'op': 'defer_unresolved'}, {'op': 'retry_original_request', 'service': 'orders'}]}],
     'CANNOT_FIRE', None, 'closed business'),
    ([{'hook': 'before_confirmation', 'when': 'upgrade_outcome_uncertain',
       'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'UNCLEAR', None, 'before_confirmation'),
    ([{'hook': 'after_notification_response', 'when': 'always',
       'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'UNCLEAR', None, 'after_notification_response'),
    ([{'hook': 'after_upgrade_response', 'when': 'always',
       'steps': [{'op': 'retry_original_request', 'service': 'orders', 'only_if': 'upgrade_succeeded'}]}],
     'CANNOT_FIRE', None, 'receipt'),
    ([{'hook': 'after_upgrade_response', 'when': 'always', 'steps': [{'op': 'read_order'}] * 8}] * 4
     + [{'hook': 'after_upgrade_response', 'when': 'always',
         'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}], 'CANNOT_FIRE', None, 'exhausted'),
])
def test_the_static_check_labels(rules, label, fires_at, reason):
    audit = probe.upgrade_audit({'rules': rules})
    assert audit['present'] and audit['label'] == label and audit['fires_at'] == fires_at
    if reason:
        assert reason in audit['reason']


def test_the_static_check_sees_no_step_in_notification_only_or_read_only_policies():
    for rules in ([NOTIFY], [READ_ONLY], []):
        audit = probe.upgrade_audit({'rules': rules})
        assert audit['present'] is False and audit['label'] is None


def test_the_declared_source_state_is_uncertain_never_pending():
    state = probe.transient_state()
    assert s2.condition('upgrade_outcome_uncertain', state, False) is True
    assert s2.condition('upgrade_receipt_missing', state, False) is True
    assert s2.condition('current_operation_pending', state, False) is False
    assert probe.TRANSIENT_READS['orders'] == 'UNKNOWN'


# ---------------------------------------------------------------- read-outs (pure)

def _small_plan(n=3):
    requests, prompts = [], {}
    for index in range(1, n + 1):
        messages = [{'role': 'system', 'content': 'You are a test.'}, {'role': 'user', 'content': f'context {index}'}]
        messages_hash = content_hash(messages)
        prompts[messages_hash] = {'messages_hash': messages_hash, 'messages': messages, 'context': index}
        requests.append({'request_id': f'r{index:04d}', 'context': index, 'campaign_id': f'campaign-{index}',
                         'study_id': f'completion-study-{index}',
                         'controls': [{'case': case, 'store': 'test', 'episode_id': f'e{index}-{position}'}
                                      for position, case in enumerate(probe.controls_order())],
                         'messages_hash': messages_hash,
                         'request_hash': s2.request_digest(s2.request_body(messages, 0)),
                         'input_token_bound': 10, 'user_bytes': 10})
    return {'counts': {'contexts': n}, 'requests': requests}, prompts


def _line(request, kind, status='ok', raw=None, request_hash=None, attempts=None):
    return {'request_id': request['request_id'], 'kind': kind, 'context': request['context'],
            'request_hash': request_hash or request['request_hash'], 'status': status, 'raw': raw,
            'attempts': attempts or [{'attempt': 1, 'error': None, 'served': None}]}


def _repair_line(request, prompts, first_raw, **fields):
    messages = probe.repair_messages(prompts[request['messages_hash']]['messages'], first_raw,
                                     probe.validation_errors(first_raw))
    return _line(request, 'repair', request_hash=s2.request_digest(s2.request_body(messages, 0)), **fields)


def test_each_draw_is_classified_as_the_loop_would_use_its_output():
    plan, prompts = _small_plan(10)
    r = plan['requests']
    lines = [
        _line(r[0], 'first', raw=FIRING),
        _line(r[1], 'first', raw='not json'), _repair_line(r[1], prompts, 'not json', raw=NO_CHANGE),
        _line(r[2], 'first', raw='not json'), _repair_line(r[2], prompts, 'not json', raw='still not json'),
        _line(r[3], 'first', raw='not json'),
        _line(r[4], 'first', raw='not json'), _repair_line(r[4], prompts, 'not json', status='error'),
        _line(r[5], 'first', status='empty_response'),
        _line(r[6], 'first', status='error'),
        _line(r[7], 'first', raw=_policy([RESEND], parent='policy-v9')),
        _line(r[8], 'first', raw=DEAD),
        _line(r[9], 'first', raw='not json'), _repair_line(r[9], prompts, 'not json', raw=FIRING),
    ]
    readouts = probe.compute_readouts(plan['requests'], prompts, lines)
    by = {d['request_id']: d for d in readouts['per_draw']}
    assert by['r0001']['class'] == 'CANDIDATE' and by['r0001']['label'] == 'CAN_FIRE' and not by['r0001']['repaired']
    assert by['r0002']['class'] == 'NO_CHANGE' and by['r0002']['repaired'] and by['r0002']['repair_status'] == 'ok'
    assert by['r0003']['class'] == 'INVALID' and by['r0003']['repaired']
    assert by['r0004']['class'] == 'UNDELIVERED' and by['r0004']['undelivered'] == 'repair'
    assert by['r0005']['class'] == 'UNDELIVERED' and by['r0005']['undelivered'] == 'repair'
    assert by['r0006']['class'] == 'INVALID' and not by['r0006']['repaired']
    assert by['r0007']['class'] == 'UNDELIVERED' and by['r0007']['undelivered'] == 'first'
    assert by['r0008']['class'] == 'INVALID' and by['r0008']['subclass'] == 'STALE_PARENT' and not by['r0008']['repaired']
    assert by['r0009']['class'] == 'CANDIDATE' and by['r0009']['label'] == 'CANNOT_FIRE'
    assert by['r0010']['class'] == 'CANDIDATE' and by['r0010']['label'] == 'CAN_FIRE' and by['r0010']['repaired']
    # The decision counts present re-sends (3, including r0009's CANNOT_FIRE one); the firing rate is descriptive.
    assert readouts['decision'] == 'GO' and readouts['R_draw']['present'] == 3 and readouts['R_valid']['present'] == 3
    assert readouts['R_fire_draw_descriptive']['firing'] == 2 and readouts['R_fire_valid_descriptive']['candidates'] == 3
    assert readouts['labels'] == {'CAN_FIRE': 2, 'CANNOT_FIRE': 1}
    assert readouts['integrity'] == []
    # Review round 1: the empty first output is a delivered INVALID draw that the loop would not have seen.
    assert by['r0006']['not_a_loop_proposal'] == 'first_empty'
    assert [d['request_id'] for d in readouts['per_draw'] if d['not_a_loop_proposal']] == ['r0006']
    assert readouts['not_a_loop_proposal'] == {'count': 1, 'by_cause': {'first_empty': 1}, 'loop_visible_draws': 9,
                                               'wilson95_upper_over_loop_visible_if_none_present': pytest.approx(
                                                   probe.wilson(0, 9)[1])}
    assert '1 of the 10 draws were empty or unreadable outputs' in readouts['statement']
    unreadable = [{'attempt': 1, 'code': 'INVALID_RESPONSE_SHAPE', 'served': {'model': 'm'}}]
    shaped = probe.compute_readouts(plan['requests'][:1], prompts,
                                    [_line(r[0], 'first', status='error', attempts=unreadable)])
    assert shaped['per_draw'][0]['class'] == 'INVALID' and shaped['decision'] == 'NO_GO' and shaped['delivered'] == 1
    assert shaped['per_draw'][0]['not_a_loop_proposal'] == 'first_unreadable'
    assert '1 of the 1 draws were empty or unreadable' in shaped['statement']
    assert 'over the other 0 the upper bound is undefined' in shaped['statement']
    bad = lines[:1] + [_line(r[1], 'first', raw='not json'), _line(r[1], 'repair', raw=NO_CHANGE, request_hash='0' * 64)]
    assert probe.compute_readouts(plan['requests'][:2], prompts, bad)['integrity'][0]['request_id'] == 'r0002'


def test_go_no_go_and_incomplete():
    plan, prompts = _small_plan(30)
    r = plan['requests']
    # NO_GO: every draw delivered and none contains an orders re-send at any hook (a read-only policy or a refusal).
    none = [_line(x, 'first', raw=NO_STEP if i % 2 else NO_CHANGE) for i, x in enumerate(r)]
    readouts = probe.compute_readouts(r, prompts, none)
    assert readouts['decision'] == 'NO_GO' and readouts['R_draw']['wilson95'][1] == pytest.approx(0.1135, abs=1e-4)
    assert readouts['R_draw']['present'] == 0 and readouts['R_valid']['candidates'] == 15
    assert readouts['statement'].startswith('NO_GO: none of the 30 draws contains an orders re-send at any hook under '
                                            'any gate (Wilson 95% upper bound 0.114)')
    assert '0 of the 30 draws were empty or unreadable outputs' in readouts['statement']
    assert 'over the other 30 the upper bound is 0.114' in readouts['statement']
    assert readouts['statement'].endswith(probe.SCOPE_SENTENCE)
    assert readouts['labels'] == {} and readouts['no_change']['count'] == 15
    missing = none[:-1]
    assert probe.compute_readouts(r, prompts, missing)['decision'] == 'INCOMPLETE'
    assert probe.compute_readouts(r, prompts, missing + [_line(r[-1], 'first', status='error')])['decision'] == 'INCOMPLETE'
    incomplete = probe.compute_readouts(r, prompts, missing)
    assert incomplete['statement'].startswith('INCOMPLETE: 29 of 30 draws delivered (0 of them empty or unreadable')
    assert ("completing the missing draws needs the owner's approval and a separately reviewed harness change (this "
            'harness has no completion mode).') in incomplete['statement']
    assert incomplete['any_generation_arrived'] is True
    # Review round 2, finding 2: when no generation arrived, the statement says a relaunch needs the owner's approval.
    errored = [_line(x, 'first', status='error', attempts=[{'attempt': 1, 'code': 'HTTP_ERROR', 'served': None}] * 2)
               for x in r[:5]]
    for lines in ([], errored):
        nothing = probe.compute_readouts(r, prompts, lines)
        assert nothing['decision'] == 'INCOMPLETE' and nothing['any_generation_arrived'] is False
        assert nothing['statement'].startswith(
            'INCOMPLETE: 0 of 30 draws delivered and no generation arrived, so nothing was observed. Another launch '
            "within the $5 phase cap sends all 30 draws and needs the owner's relaunch approval (design §6.0; "
            'protocol §11). ')
        assert nothing['statement'].endswith(probe.SCOPE_SENTENCE)
    # A generation that arrived without making a draw delivered (an invalid first output whose repair never went), an
    # empty reply, or a line cut off by a hard kill: never the relaunch wording, because the one-run rule refuses a
    # relaunch. For a cut-off line that holds since review round 3, finding 1: --finalize-abandoned counts it as
    # delivered (test_a_line_cut_off_by_a_hard_stop_counts_as_delivered_and_no_relaunch_is_offered).
    arrived = [[_line(r[0], 'first', raw='not json')], [_line(r[0], 'first', status='empty_response')],
               [_line(r[0], 'first', status='error', attempts=[{'attempt': 1, 'code': 'INVALID_RESPONSE_SHAPE',
                                                                'served': {'model': 'm'}}])]]
    for lines in arrived:
        readouts = probe.compute_readouts(r, prompts, lines)
        assert readouts['decision'] == 'INCOMPLETE' and readouts['any_generation_arrived'] is True
        assert 'relaunch approval' not in readouts['statement'] and 'no completion mode' in readouts['statement']
    cut = probe.compute_readouts(r, prompts, [], partial_lines_skipped=1)
    assert cut['any_generation_arrived'] is True and 'no completion mode' in cut['statement']
    # The manifest's own count (the one-run rule's test) also rules the relaunch wording out: counted, or unreadable.
    for counted in (1, None):
        by_manifest = probe.compute_readouts(r, prompts, errored, manifest_delivered=counted)
        assert by_manifest['any_generation_arrived'] is True and 'no completion mode' in by_manifest['statement']
    firing = missing[:-1] + [_line(r[-2], 'first', raw=FIRING)]
    readouts = probe.compute_readouts(r, prompts, firing)
    assert readouts['decision'] == 'GO' and readouts['statement'].startswith('GO: 1 of 30 first proposals')
    assert ('1 can fire (1 at after_upgrade_response, where a re-send can complete the task, and 0 only at '
            'before_final_report' in readouts['statement'])
    assert '0 cannot fire and 0 are unclear' in readouts['statement']
    late = _policy([{'hook': 'before_final_report', 'when': 'upgrade_outcome_uncertain',
                     'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}])
    late_readouts = probe.compute_readouts(r[:1], prompts, [_line(r[0], 'first', raw=late)])
    assert late_readouts['decision'] == 'GO' and late_readouts['fires_at'] == {'before_final_report': 1}
    assert '1 can fire (0 at after_upgrade_response' in late_readouts['statement']
    assert '1 only at before_final_report' in late_readouts['statement']
    assert readouts['fires_at'] == {'after_upgrade_response': 1}
    both = _policy([RESEND, NOTIFY])
    readouts = probe.compute_readouts(r[:1], prompts, [_line(r[0], 'first', raw=both)])
    assert readouts['both_sides'] == 1 and readouts['phase9_notification_step'] == 1


PENDING_ONLY = {'hook': 'after_upgrade_response', 'when': 'upgrade_receipt_missing',
                'steps': [{'op': 'read_current_operation'},
                          {'op': 'retry_original_request', 'service': 'orders', 'only_if': 'current_operation_pending'}]}
CONFIRMATION_ONLY = {'hook': 'before_confirmation', 'when': 'upgrade_outcome_uncertain',
                     'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}
FINAL_REPORT_ONLY = {'hook': 'before_final_report', 'when': 'upgrade_receipt_missing',
                     'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}


@pytest.mark.parametrize('rule,label,fires_at', [
    (PENDING_ONLY, 'CANNOT_FIRE', None),
    (CONFIRMATION_ONLY, 'UNCLEAR', None),
    (FINAL_REPORT_ONLY, 'CAN_FIRE', 'before_final_report'),
])
def test_any_present_orders_re_send_is_go_whatever_its_label(rule, label, fires_at):
    """Review round 1, finding 1 (the reviewer's decide_demo): PHASE28_DESIGN.md §6.0, approved in §19 decision 4,
    decides on the present predicate. One policy and 29 refusals is GO for a PENDING-gated re-send, a
    before_confirmation re-send and a before_final_report-only re-send alike; the label is only described."""
    plan, prompts = _small_plan(30)
    r = plan['requests']
    lines = [_line(r[0], 'first', raw=_policy([rule]))] + [_line(x, 'first', raw=NO_CHANGE) for x in r[1:]]
    readouts = probe.compute_readouts(r, prompts, lines)
    assert readouts['decision'] == 'GO' and readouts['R_draw']['present'] == 1
    assert readouts['labels'] == {label: 1}
    assert readouts['R_fire_draw_descriptive']['firing'] == (1 if label == 'CAN_FIRE' else 0)
    assert readouts['fires_at'] == ({fires_at: 1} if fires_at else {})
    assert 'GO' in probe.DECISION_RULE and 'any hook' in probe.DECISION_RULE and 'never decide' in probe.DECISION_RULE


def test_an_empty_or_unreadable_or_refused_repair_is_counted_as_not_a_loop_proposal():
    plan, prompts = _small_plan(4)
    r = plan['requests']
    unreadable = [{'attempt': 1, 'code': 'INVALID_RESPONSE_SHAPE', 'served': {'model': 'm'}}]
    limited = [{'attempt': 1, 'code': 'INPUT_LIMIT', 'served': None}]
    lines = [_line(r[0], 'first', raw='not json'), _repair_line(r[0], prompts, 'not json', status='empty_response'),
             _line(r[1], 'first', raw='not json'),
             _repair_line(r[1], prompts, 'not json', status='error', attempts=unreadable),
             _line(r[2], 'first', raw='not json'),
             _repair_line(r[2], prompts, 'not json', status='error', attempts=limited),
             _line(r[3], 'first', raw='not json'), _repair_line(r[3], prompts, 'not json', raw='still not json')]
    readouts = probe.compute_readouts(r, prompts, lines)
    assert [d['class'] for d in readouts['per_draw']] == ['INVALID'] * 4
    assert [d['not_a_loop_proposal'] for d in readouts['per_draw']] == ['repair_empty', 'repair_unreadable',
                                                                          'repair_input_limit', None]
    assert readouts['decision'] == 'NO_GO' and readouts['not_a_loop_proposal']['count'] == 3
    assert '3 of the 4 draws were empty or unreadable outputs' in readouts['statement']
    assert f'over the other 1 the upper bound is {probe.wilson(0, 1)[1]:.3f}' in readouts['statement']


def test_the_operating_characteristics_are_the_designs_present_rule():
    table = {row['s']: row for row in probe.operating_characteristics()['table']}
    assert table[0.05]['p_no_go_design_r_equals_s_over_0_75'] == pytest.approx(0.1262, abs=1e-4)
    assert table[0.05]['p_no_go_if_r_equals_s'] == pytest.approx(0.2146, abs=1e-4)
    assert table[0.10]['p_no_go_design_r_equals_s_over_0_75'] == pytest.approx(0.0137, abs=1e-4)
    assert probe.operating_characteristics()['no_go_wilson95_upper_bound'] == pytest.approx(0.1135, abs=1e-4)


# ---------------------------------------------------------------- the live loop (fake provider, no network)

class FakeSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


class FakeProvider:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def complete(self, messages, *, role, max_output_tokens, timeout_seconds):
        assert role == 'mechanic' and max_output_tokens == 2000 and timeout_seconds == 20.0
        self.calls.append(messages)
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(content=outcome, model_id=probe.EXPECTED_MECHANIC_MODEL, input_tokens=10, output_tokens=5)


def _run(tmp_path, plan, prompts, script, cap=5.0, stop=lambda: False):
    provider, sleep = FakeProvider(script), FakeSleep()
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    guard = probe.SpendGuard(cap)
    try:
        reason = asyncio.run(probe.run_draws(plan['requests'], prompts, provider, guard, recorder, sleep=sleep, stop=stop))
    finally:
        recorder.close()
    results, _ = probe.load_results(tmp_path / 'responses.jsonl')
    return reason, provider, sleep, recorder.manifest, results


def test_the_loop_repairs_retries_blind_once_and_never_re_rolls_a_delivered_output(tmp_path):
    plan, prompts = _small_plan(3)
    script = ['not json', NO_CHANGE,
              RuntimeProviderError('down', code='CONNECTION_ERROR'), FIRING,
              RuntimeProviderError('empty', code='EMPTY_FINAL_RESPONSE')]
    reason, provider, sleep, manifest, results = _run(tmp_path, plan, prompts, script)
    assert reason == 'completed' and provider.script == []
    r1 = prompts[plan['requests'][0]['messages_hash']]['messages']
    assert provider.calls[0] == r1
    assert provider.calls[1] == probe.repair_messages(r1, 'not json', probe.validation_errors('not json'))
    assert [(line['request_id'], line['kind'], line['status'], len(line['attempts'])) for line in results] == [
        ('r0001', 'first', 'ok', 1), ('r0001', 'repair', 'ok', 1), ('r0002', 'first', 'ok', 2),
        ('r0003', 'first', 'empty_response', 1)]
    assert sleep.calls == [1.0] * probe.BLIND_RETRY_WAIT_SECONDS
    assert manifest['attempts'] == 5 and manifest['charged_upper_bound'] == pytest.approx(5 * 0.04984)
    assert manifest['generations_delivered'] == 4 and manifest['repairs_sent'] == 1 and manifest['requests_done'] == 3
    assert not any('class' in line or 'policy_hash' in line for line in results)
    readouts = probe.compute_readouts(plan['requests'], prompts, results)
    assert readouts['decision'] == 'GO' and readouts['classes'] == {'CANDIDATE': 1, 'INVALID': 1, 'NO_CHANGE': 1}


def test_five_errored_draws_in_a_row_stop_the_run_after_the_declared_waits(tmp_path):
    plan, prompts = _small_plan(6)
    script = [RuntimeProviderError('5xx', code='HTTP_ERROR', http_status=500)] * 12
    reason, provider, sleep, manifest, results = _run(tmp_path, plan, prompts, script)
    assert reason == 'consecutive_errors' and len(provider.calls) == 10 and len(results) == 5
    assert [w['seconds'] for w in manifest['backoff_waits']] == [30, 120, 300, 300]
    assert manifest['generations_delivered'] == 0
    readouts = probe.compute_readouts(plan['requests'], prompts, results)
    assert readouts['decision'] == 'INCOMPLETE' and readouts['any_generation_arrived'] is False
    assert "needs the owner's relaunch approval" in readouts['statement']


def test_the_spend_guard_stops_before_an_unaffordable_request(tmp_path):
    plan, prompts = _small_plan(3)
    reason, provider, _, manifest, _ = _run(tmp_path, plan, prompts, ['not json', 'not json', FIRING], cap=0.1)
    assert reason == 'spend_guard' and len(provider.calls) == 2 and manifest['attempts'] == 2


def _run_stopping(tmp_path, plan, prompts, script, stop_when, sleep=None):
    provider, sleep = FakeProvider(script), sleep or FakeSleep()
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    try:
        reason = asyncio.run(probe.run_draws(plan['requests'], prompts, provider, probe.SpendGuard(5.0), recorder,
                                             sleep=sleep, stop=lambda: stop_when(provider, sleep)))
    finally:
        recorder.close()
    results, _ = probe.load_results(tmp_path / 'responses.jsonl')
    return reason, provider, sleep, recorder.manifest, results


def test_a_stop_between_an_invalid_first_output_and_its_repair_leaves_the_draw_undelivered(tmp_path):
    """Review round 1 (E1b): a stop that arrives while a first request is in flight, whose output then fails
    validation, sends no repair and leaves that draw UNDELIVERED, never INVALID, so a stop cannot make a NO_GO."""
    plan, prompts = _small_plan(3)
    reason, provider, _, manifest, results = _run_stopping(
        tmp_path, plan, prompts, ['not json', NO_CHANGE, 'not json', FIRING, FIRING],
        lambda provider, _: len(provider.calls) >= 3)
    assert reason == 'operator_stop' and len(provider.calls) == 3 and provider.script == [FIRING, FIRING]
    assert [(line['request_id'], line['kind']) for line in results] == [('r0001', 'first'), ('r0001', 'repair'),
                                                                        ('r0002', 'first')]
    readouts = probe.compute_readouts(plan['requests'], prompts, results)
    assert [(d['request_id'], d['class'], d['undelivered']) for d in readouts['per_draw']] == [
        ('r0001', 'NO_CHANGE', None), ('r0002', 'UNDELIVERED', 'repair'), ('r0003', 'UNDELIVERED', 'first')]
    assert readouts['decision'] == 'INCOMPLETE' and manifest['repairs_sent'] == 1


def test_a_stop_during_the_blind_retry_wait_sends_no_retry(tmp_path):
    """Review round 1 (E1c): the stop arrives during the 10 s wait before a blind re-send; nothing more is sent and
    only the one attempt is charged."""
    plan, prompts = _small_plan(2)
    reason, provider, sleep, manifest, results = _run_stopping(
        tmp_path, plan, prompts, [RuntimeProviderError('down', code='CONNECTION_ERROR'), FIRING, FIRING],
        lambda _, sleep: len(sleep.calls) >= 3)
    assert reason == 'operator_stop' and len(provider.calls) == 1 and sleep.calls == [1.0, 1.0, 1.0]
    assert [(line['request_id'], line['status'], len(line['attempts'])) for line in results] == [('r0001', 'error', 1)]
    assert manifest['attempts'] == 1 and manifest['charged_upper_bound'] == pytest.approx(0.04984)
    assert manifest['generations_delivered'] == 0


def test_spend_guard_and_budget():
    guard = probe.SpendGuard(5.0)
    assert sum(guard.admit() for _ in range(200)) == 100
    probe.check_budget(60, 5.0)
    for calls, cap in ((101, 5.0), (60, 5.01), (60, 0), (60, float('nan'))):
        with pytest.raises(probe.PlanningError):
            probe.check_budget(calls, cap)
    with pytest.raises(probe.PlanningError):
        probe.SpendGuard(5.01)


class FakeOpenAI:
    """Modelled on the openai client the real RuntimeProvider builds. `cancel_on` = n raises asyncio.CancelledError
    inside the n-th call, while that request is in flight (RuntimeProvider re-raises it from inside the call); a
    scripted exception is raised as the client would raise it (RuntimeProvider maps it to a RuntimeProviderError)."""

    script, calls, cancel_on = [], [], None

    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        FakeOpenAI.calls.append(kwargs)
        if FakeOpenAI.cancel_on == len(FakeOpenAI.calls):
            raise asyncio.CancelledError()
        outcome = FakeOpenAI.script.pop(0) if FakeOpenAI.script else NO_CHANGE
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(model='served-by/test', system_fingerprint='fp_test',
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                               choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=outcome))])

    async def close(self):
        pass


def _fake_settings(dry_settings):
    return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key')


@needs_store
def test_every_send_including_the_repair_is_digest_checked_on_the_real_provider(tmp_path, dry_settings):
    plan, prompts = _small_plan(2)
    FakeOpenAI.script, FakeOpenAI.calls = ['not json', NO_CHANGE, FIRING], []
    sender = s2.RequestSender(base=FakeOpenAI)

    async def go(requests, recorder):
        async with RuntimeProvider(_fake_settings(dry_settings), live_authorized=True, client_factory=sender) as provider:
            return await probe.run_draws(requests, prompts, provider, probe.SpendGuard(5.0), recorder, sender=sender,
                                         sleep=FakeSleep())
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    try:
        assert asyncio.run(go(plan['requests'], recorder)) == 'completed'
    finally:
        recorder.close()
    r1 = prompts[plan['requests'][0]['messages_hash']]['messages']
    repair = s2.request_digest(s2.request_body(probe.repair_messages(r1, 'not json', probe.validation_errors('not json')), 0))
    assert [s2.request_digest(call) for call in FakeOpenAI.calls] == [plan['requests'][0]['request_hash'], repair,
                                                                       plan['requests'][1]['request_hash']]
    assert all(call['temperature'] == 0 for call in FakeOpenAI.calls)
    wrong = [{**plan['requests'][1], 'request_hash': '0' * 64}]
    FakeOpenAI.calls = []
    other = tmp_path / 'second'
    other.mkdir()
    recorder = probe.Recorder(other, {'statuses': {}})
    try:
        with pytest.raises(probe.PlanningError, match='Request mismatch'):
            asyncio.run(go(wrong, recorder))
    finally:
        recorder.close()
    assert FakeOpenAI.calls == []


# ---------------------------------------------------------------- output, claims and other paid runs

def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    (tmp_path / 'artifacts').mkdir(exist_ok=True)
    return tmp_path / 'artifacts'


def _manifest(artifacts, relative, name=probe.MANIFEST_NAME, **fields):
    path = artifacts / relative / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {'status': 'STOPPED', 'started_at': '2026-09-25T00:00:00Z', 'ended_at': '2026-09-25T00:10:00Z',
            'statuses': {'error': 5}, 'generations_delivered': 0, 'charged_upper_bound': 0.4984, **fields}
    path.write_text(json.dumps(body))
    return path


def _claim(artifacts, number, out, pid=999999, directory=probe.CLAIM_DIR):
    path = artifacts / directory / f'claim-{number:02d}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'claim': path.name, 'pid': pid, 'out': out, 'plan_hash': 'plan',
                                'harness_sha256': 'harness', 'spend_cap': 5.0}))
    return path


IDLE = lambda: ('down', None)  # noqa: E731
FOREIGN_RUN = (4242, 1, 'python scripts/experiments/report_narrow_probe.py --execute-live --out y')


def test_output_directories_claims_and_one_delivering_run(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    for bad in ('artifacts/phase28-2026-09-25/live', 'artifacts/phase28a-2026-09-25', 'artifacts/phase28a-x/a/b',
                f'artifacts/{probe.CLAIM_DIR}/x', '/tmp/elsewhere'):
        with pytest.raises(probe.PlanningError):
            probe.check_output(bad)
    assert probe.check_output('artifacts/phase28a-test/live') == (artifacts / 'phase28a-test/live').resolve()
    _manifest(artifacts, 'phase28a-test/old')
    assert probe.earlier_live_runs(artifacts)[0]['charged_upper_bound'] == 0.4984
    assert probe.effective_spend_cap(5.0, probe.earlier_live_runs(artifacts)) == pytest.approx(5.0 - 0.4984)
    _manifest(artifacts, 'phase28a-test/delivered', generations_delivered=1)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase28a-test/live')
    (artifacts / 'phase28a-test/delivered' / probe.MANIFEST_NAME).unlink()
    _manifest(artifacts, 'phase28a-test/running', status='RUNNING', ended_at=None)
    with pytest.raises(probe.PlanningError, match='not final'):
        probe.check_output('artifacts/phase28a-test/live')


def test_a_claim_is_atomic_and_finalize_abandoned_charges_what_was_recorded(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    out = probe.check_output('artifacts/phase28a-test/live')
    path, earlier = probe.take_claim(out, 'plan', 'harness', spend_cap=5.0)
    assert path.name == 'claim-01.json' and earlier == []
    with pytest.raises(probe.PlanningError, match='no manifest'):
        probe.check_output('artifacts/phase28a-test/live-2')
    with pytest.raises(probe.PlanningError, match='may still be running'):
        probe.finalize_abandoned(str(path), alive=lambda pid: True)
    out.mkdir(parents=True)
    (out / 'responses.jsonl').write_text(json.dumps({'request_id': 'r0001', 'kind': 'first', 'status': 'error',
                                                      'attempts': [{'code': 'CONNECTION_ERROR'}] * 2}) + '\n')
    (out / probe.MANIFEST_NAME).write_text(json.dumps({'status': 'RUNNING', 'attempts': 2, 'generations_delivered': 0}))
    manifest_path, manifest = probe.finalize_abandoned(str(path), alive=lambda pid: False)
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'abandoned'
    assert manifest['attempts'] == 2 + probe.ABANDONED_IN_FLIGHT_ATTEMPTS and manifest['generations_delivered'] == 0
    assert probe.check_output('artifacts/phase28a-test/live-2')


@pytest.mark.parametrize('last_line,cut', [('firing', True), ('errored', True), ('errored', False)])
def test_a_line_cut_off_by_a_hard_stop_counts_as_delivered_and_no_relaunch_is_offered(tmp_path, monkeypatch, last_line,
                                                                                      cut):
    """Review round 3, finding 1 (the fix-check reviewer's E1, its assertion inverted). A hard stop (kill -9, power
    loss) while the recorder writes r0001's first line leaves the RUNNING manifest saved before that send (0
    delivered) and a responses.jsonl ending in a cut-off line, part of which can be read. Round 2's
    --finalize-abandoned counted complete lines only, so the run became "final, 0 delivered" and the one-run rule
    (which reads only the manifest's count) offered a relaunch after part of a draw may have been seen. Now a cut-off
    line counts as delivered, whatever its readable part says (an errored line too: the conservative side), and a
    second run is refused as repeat-until-lucky. The contrast: the same run with a complete errored line and no cut
    still delivered nothing, and another launch needs the owner's relaunch approval."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    plan, prompts = _small_plan(3)
    harness = probe.sha256_file(probe.__file__)
    out = 'artifacts/phase28a-test/live'
    _claim(artifacts, 1, out)
    run = tmp_path / out
    run.mkdir(parents=True)
    (run / probe.MANIFEST_NAME).write_text(json.dumps({
        'schema_version': probe.SCHEMA, 'mode': 'live', 'status': 'RUNNING', 'pid': 999999,
        'plan_hash': probe.plan_hash(plan), 'harness_sha256': harness, 'started_at': 'x', 'ended_at': None,
        'requests_done': 0, 'repairs_sent': 0, 'attempts': 0, 'charged_upper_bound': 0.0, 'statuses': {},
        'generations_delivered': 0, 'in_flight_request': {'request_id': 'r0001', 'kind': 'first'}}))
    probe.write_json(run / 'plan.json', plan)
    (run / 'prompts.jsonl').write_text(''.join(json.dumps(p, sort_keys=True) + '\n' for p in prompts.values()))
    request = plan['requests'][0]
    line = (_line(request, 'first', raw=FIRING, attempts=[{'attempt': 1, 'error': None, 'served': {'model': 'm'}}])
            if last_line == 'firing' else
            _line(request, 'first', status='error', attempts=[{'attempt': 1, 'code': 'CONNECTION_ERROR', 'served': None}] * 2))
    text = json.dumps(line, sort_keys=True)
    (run / 'responses.jsonl').write_text(text[: len(text) // 2] if cut else text + '\n')
    _, final = probe.finalize_abandoned(str(artifacts / probe.CLAIM_DIR / 'claim-01.json'), alive=lambda pid: False)
    readouts = probe.recompute_readouts(run)
    assert final['finalized_abandoned']['partial_lines_skipped'] == int(cut) == readouts['partial_lines_skipped']
    recorded = 0 if cut else 2
    assert final['attempts'] == recorded + probe.ABANDONED_IN_FLIGHT_ATTEMPTS
    assert final['charged_upper_bound'] == pytest.approx((recorded + 2) * probe.PER_REQUEST_DOLLAR_BOUND)
    if cut:
        assert final['generations_delivered'] == 1
        with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
            probe.earlier_live_runs(artifacts)
        with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
            probe.check_output('artifacts/phase28a-test/live-2')
        assert readouts['any_generation_arrived'] is True
        assert 'no completion mode' in readouts['statement'] and 'relaunch approval' not in readouts['statement']
    else:
        assert final['generations_delivered'] == 0
        earlier = probe.earlier_live_runs(artifacts)
        assert earlier == [{'manifest': f'{out}/{probe.MANIFEST_NAME}', 'charged_upper_bound': pytest.approx(
            4 * probe.PER_REQUEST_DOLLAR_BOUND)}]
        with pytest.raises(probe.PlanningError, match='ended having delivered nothing'):
            probe.check_relaunch_approval(None, earlier, probe.check_output('artifacts/phase28a-test/live-2', live=False),
                                          probe.plan_hash(plan), harness)
        assert readouts['any_generation_arrived'] is False and 'relaunch approval' in readouts['statement']


def test_other_paid_runs_are_seen_and_this_phase_and_the_seals_are_not(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    assert probe.other_paid_runs(status=IDLE) == ([], 'down')
    _manifest(artifacts, 'phase28a-2026-09-25/live', status='RUNNING', ended_at=None)
    (artifacts / 'phase22-2026-09-24').mkdir()
    (artifacts / 'phase22-2026-09-24' / 'x-manifest.json').write_text('not json')
    (artifacts / 'phase24-2026-09-24').mkdir()
    (artifacts / 'phase24-2026-09-24' / 'heldout-manifest.json').write_text('not json')
    assert probe.other_paid_runs(status=IDLE)[0] == []
    for relative in ('phase30-2026-09-25/live', 'phase28-2026-09-26', 'phase29-2026-09-25/live'):
        path = _manifest(artifacts, relative, name='run-manifest.json', status='RUNNING', ended_at=None)
        assert probe.other_paid_runs(status=IDLE)[0] == [str(path.relative_to(tmp_path))]
        path.unlink()
    claim = _claim(artifacts, 1, 'artifacts/phase30-2026-09-25/live', directory='phase30-live-claims')
    assert probe.other_paid_runs(status=IDLE)[0] == [str(claim.relative_to(tmp_path))]
    _manifest(artifacts, 'phase30-2026-09-25/live', name='report-narrow-probe-manifest.json')
    assert probe.other_paid_runs(status=IDLE)[0] == []
    assert 'active campaign' in probe.other_paid_runs(status=lambda: ('active', 'c'))[0][0]
    assert 'could not be read' in probe.other_paid_runs(status=lambda: ('unknown', 'Timeout'))[0][0]
    assert probe.other_paid_runs(status=lambda: ('idle', None))[0] == []


def test_the_process_guard_ignores_this_runs_caffeinate_child_and_sees_a_foreign_run(tmp_path, monkeypatch):
    # An empty test tree, so the run-record half of the guard never reads the real repository's artifacts (applying
    # round 2, this test failed while a real Phase 30 run was live: it saw that run's open manifest and claim).
    _artifacts(tmp_path, monkeypatch)
    me, parent = os.getpid(), os.getppid()
    own = f'python scripts/experiments/upgrade_mechanic_probe.py --execute-live --out artifacts/phase28a-x/live'
    rows = [(parent, 1, '-zsh'), (me, parent, own), (me + 100000, me, f'caffeinate -is {own}'), FOREIGN_RUN,
            (4343, 1, 'grep --execute-live scripts/experiments/report_narrow_probe.py')]
    monkeypatch.setattr(probe, 'process_list', lambda: rows)
    assert probe.experiment_processes() == [f'pid 4242: {FOREIGN_RUN[2]}']
    blockers, _ = probe.other_paid_runs(status=IDLE)
    assert blockers == [f'pid 4242: {FOREIGN_RUN[2]}']


# ---------------------------------------------------------------- the live gate

def _gate(tmp_path, monkeypatch, plan, *, review=True, reviewed_line='{}', marker=None, pins=True, record=None,
          confirm_entity='entity'):
    _artifacts(tmp_path, monkeypatch)
    harness = probe.sha256_file(probe.__file__)
    plan_hash = probe.plan_hash(plan)
    lines = ['# test protocol'] + ([f'**Status:** {marker}.'] if marker else [])
    lines += ['', '## Pins'] + ([f'harness {harness}', f'plan {plan_hash}'] if pins else [])
    if reviewed_line:
        lines.append(reviewed_line.format(probe.REVIEWED_LINE.format(harness=harness, plan=plan_hash)))
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    protocol_sha = probe.sha256_file(protocol)
    if review:
        path = tmp_path / probe.REVIEW_RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {'phase': '28a', 'status': 'approved', 'approved_by': 'the reviewer (test)', 'phase_cap': 5.0,
                'configuration_hash': probe.DECLARED_CONFIGURATION_HASH, 'protocol_sha256': protocol_sha,
                'harness_sha256': harness, 'plan_hash': plan_hash, **(record or {})}
        path.write_text(json.dumps({k: v for k, v in body.items() if v is not ...}))
    return SimpleNamespace(out='artifacts/phase28a-test/live', expect_harness_sha256=harness,
                           expect_protocol_sha256=protocol_sha, expect_plan_hash=plan_hash, spend_cap=5.0,
                           confirm_entity=confirm_entity, ignore_manifest=[], relaunch_approval=None)


class CredentialRead(Exception):
    pass


def _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts, status=IDLE):
    def no_credentials(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', no_credentials)
    with pytest.raises(probe.PlanningError) as error:
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status)
    assert not (tmp_path / 'artifacts/phase28a-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    return str(error.value)


def test_the_live_gate_enforces_pins_review_and_one_paid_run(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    for change, message in ((dict(expect_harness_sha256='0' * 64), 'harness'),
                            (dict(expect_protocol_sha256='0' * 64), 'does not match the protocol'),
                            (dict(expect_plan_hash='0' * 64), '--expect-plan-hash'),
                            (dict(spend_cap=0.05), 'exceed')):
        assert message in _refused_before_credentials(tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), **change}),
                                                      plan, prompts)
    # Editing the protocol after its launch line changes its sha256, so the typed pin refuses.
    probe.PROTOCOL.write_text(probe.PROTOCOL.read_text() + 'an edit after the launch line\n')
    assert 'does not match the protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    tampered = {k: dict(v) for k, v in prompts.items()}
    tampered[plan['requests'][0]['messages_hash']]['messages'] = [{'role': 'system', 'content': 'other'}]
    args = _gate(tmp_path, monkeypatch, plan)
    assert 'no verified prompt' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, tampered)
    for marker in ('NOT yet reviewed', 'not YET reviewed'):
        args = _gate(tmp_path, monkeypatch, plan, marker=marker)
        assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, pins=False, reviewed_line=None)
    assert 'does not declare this harness' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    for wrapped in (None, '`{}`', '- {}', '**{}**'):
        args = _gate(tmp_path, monkeypatch, plan, reviewed_line=wrapped)
        assert 'Reviewed for launch' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    (tmp_path / probe.REVIEW_RECORD).unlink()
    args = _gate(tmp_path, monkeypatch, plan, review=False)
    assert 'No readable review record' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    for record, message in (({'status': ...}, 'approved'), ({'status': 'pending'}, 'approved'),
                            ({'approved_by': ' '}, 'approver'), ({'approved_by': ...}, 'approver'),
                            ({'phase_cap': 15.0}, 'phase_cap'), ({'phase_cap': ...}, 'phase_cap'),
                            ({'configuration_hash': '0' * 64}, 'review record does not name'),
                            ({'protocol_sha256': '0' * 64}, 'review record does not name'),
                            ({'harness_sha256': '0' * 64}, 'review record does not name'),
                            ({'plan_hash': '0' * 64}, 'review record does not name')):
        args = _gate(tmp_path, monkeypatch, plan, record=record)
        assert message in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    assert 'active campaign' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts,
                                                             status=lambda: ('active', 'c'))
    monkeypatch.setattr(probe, 'process_list', lambda: [FOREIGN_RUN])
    assert 'pid 4242' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    monkeypatch.setattr(probe, 'process_list', lambda: [])
    monkeypatch.setattr(probe, 'PROTOCOL', tmp_path / 'missing.md')
    assert 'No protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    # Every check passes: the next step is the credential read, and nothing was claimed before it.
    args = _gate(tmp_path, monkeypatch, plan)

    def credential_read(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', credential_read)
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts/phase28a-test').exists()


def _live(tmp_path, monkeypatch, dry_settings):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan, confirm_entity=dry_settings.wandb_entity)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', FakeOpenAI)
    return plan, prompts, args


@needs_store
def test_a_live_run_end_to_end_on_the_real_provider_with_a_fake_client(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = ['not json', FIRING, DEAD, NO_CHANGE], []
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 0
    assert len(FakeOpenAI.calls) == 4 and all(call['temperature'] == 0 for call in FakeOpenAI.calls)
    directory = tmp_path / args.out
    manifest = json.loads((directory / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'COMPLETED' and manifest['stop_reason'] == 'completed'
    assert manifest['generations_delivered'] == 4 and manifest['repairs_sent'] == 1 and manifest['attempts'] == 4
    assert manifest['claim'] == f'artifacts/{probe.CLAIM_DIR}/claim-01.json' and manifest['traceback'] is None
    assert manifest['review'] == {'status': 'approved', 'approved_by': 'the reviewer (test)', 'approved_at': None}
    assert manifest['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH and manifest['phase_spend_cap'] == 5.0
    assert 'fake-not-a-key' not in (directory / 'responses.jsonl').read_text()
    readouts = json.loads((directory / 'readouts.json').read_text())
    assert readouts['decision'] == 'GO' and readouts['classes'] == {'CANDIDATE': 2, 'NO_CHANGE': 1}
    assert readouts['labels'] == {'CAN_FIRE': 1, 'CANNOT_FIRE': 1}
    assert readouts['provider']['served_model'] == {'served-by/test': 4}
    assert probe.recompute_readouts(directory) == readouts
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase28a-test/live-2')


@needs_store
def test_another_paid_run_seen_after_the_claim_ends_the_run_at_zero_cost(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    reads = []

    def rows():
        reads.append(1)
        return [] if len(reads) < 3 else [FOREIGN_RUN]
    monkeypatch.setattr(probe, 'process_list', rows)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    assert len(reads) == 3 and FakeOpenAI.calls == []
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0
    assert probe.check_output('artifacts/phase28a-test/live-2')


@needs_store
def test_a_stop_that_arrives_as_the_handlers_are_installed_refuses_before_the_claim(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    real_signal = signal.signal

    def install_and_fire(sig, handler):
        previous = real_signal(sig, handler)
        if sig == signal.SIGTERM and callable(handler):
            handler(sig, None)
        return previous
    monkeypatch.setattr(probe.signal, 'signal', install_and_fire)
    with pytest.raises(probe.PlanningError, match='before the claim'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / args.out).exists()


@needs_store
def test_a_sigint_during_a_provider_call_stops_the_run_and_the_one_run_rule_holds(tmp_path, monkeypatch, dry_settings):
    """Review round 1 (E2): a real SIGINT to this process while the first provider call is in flight. The call
    finishes, no repair or later request is sent, the run is STOPPED (operator_stop) with the signal recorded, it is
    INCOMPLETE, a second run is refused because a generation was delivered, and the handlers are restored."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    before = signal.getsignal(signal.SIGINT)

    class SignallingOpenAI(FakeOpenAI):
        async def create(self, **kwargs):
            if not FakeOpenAI.calls:
                os.kill(os.getpid(), signal.SIGINT)
                await asyncio.sleep(0)
            return await super().create(**kwargs)
    FakeOpenAI.script, FakeOpenAI.calls = ['not json', FIRING, FIRING, FIRING], []
    monkeypatch.setattr(probe, 'openai_client_factory', SignallingOpenAI)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    assert len(FakeOpenAI.calls) == 1 and signal.getsignal(signal.SIGINT) is before
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'operator_stop'
    assert manifest['stop_signal']['signal'] == 'SIGINT' and manifest['stop_signal']['status_at_arrival'] == 'RUNNING'
    assert manifest['generations_delivered'] == 1 and manifest['attempts'] == 1
    readouts = json.loads((tmp_path / args.out / 'readouts.json').read_text())
    assert readouts['decision'] == 'INCOMPLETE' and readouts['per_draw'][0]['undelivered'] == 'repair'
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase28a-test/live-2')


@needs_store
def test_a_crash_after_a_delivery_is_aborted_final_and_ends_the_phase(tmp_path, monkeypatch, dry_settings):
    """Review round 1 (E3): an exception inside the run after one delivered generation: ABORTED with its traceback,
    final, and no second run."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = ['not json', FIRING], []

    def crash(raw):
        raise ValueError('synthetic crash in the loop')
    monkeypatch.setattr(probe, 'validation_errors', crash)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'ValueError' and probe._final(manifest)
    assert 'synthetic crash in the loop' in manifest['traceback'] and manifest['generations_delivered'] == 1
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase28a-test/live-2')


@needs_store
def test_a_base_exception_escaping_the_run_is_recorded_aborted_and_final(tmp_path, monkeypatch, dry_settings):
    """Review round 1 (E4): a cancellation escaping the run used to leave the manifest RUNNING with ended_at set. It is
    now recorded ABORTED with its traceback and then re-raised; the run is final, the handlers are restored, and
    --finalize-abandoned has nothing to close."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    FakeOpenAI.script, FakeOpenAI.calls = [NO_CHANGE] * 3, []

    def cancel(raw):
        raise asyncio.CancelledError()
    monkeypatch.setattr(probe, 'validation_errors', cancel)
    with pytest.raises(asyncio.CancelledError):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert {sig: signal.getsignal(sig) for sig in before} == before
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'CancelledError' and probe._final(manifest)
    assert manifest['traceback'] and manifest['generations_delivered'] == 1 and manifest['attempts'] == 1
    assert manifest['unrecorded_attempts_charged'] == 0   # the send had finished; round 2's in-flight case is below
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase28a-test/live-2')
    with pytest.raises(probe.PlanningError, match='already final'):
        probe.finalize_abandoned(str(tmp_path / 'artifacts' / probe.CLAIM_DIR / 'claim-01.json'), alive=lambda pid: False)


class APIConnectionError(Exception):
    """Named as the openai client's connection error, which RuntimeProvider maps to CONNECTION_ERROR."""


def _relaunch_record(tmp_path, plan, earlier, launch_out, name='relaunch-approval-01.json',
                     directory='phase28a-earlier', **fields):
    """The owner's relaunch approval (RELAUNCH_RULE), written only in a test tree."""
    path = tmp_path / 'artifacts' / directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {'status': 'approved', 'approved_by': 'the owner (test)', 'approved_at': '2026-09-25T23:00:00Z',
            'earlier_undelivered_runs': earlier, 'out': launch_out, 'plan_hash': probe.plan_hash(plan),
            'harness_sha256': probe.sha256_file(probe.__file__), **fields}
    path.write_text(json.dumps({k: v for k, v in body.items() if v is not ...}))
    return str(path.relative_to(tmp_path))


@needs_store
@pytest.mark.parametrize('cancel_on,attempts,delivered,unrecorded', [(1, 1, 0, 1), (3, 3, 1, 2)])
def test_a_cancellation_while_a_request_is_in_flight_charges_every_admitted_attempt(
        tmp_path, monkeypatch, dry_settings, cancel_on, attempts, delivered, unrecorded):
    """Review round 2, finding 1: RuntimeProvider re-raises asyncio.CancelledError from inside the provider call.
    Round 1's handler made that manifest final with the counts of the last finished send, so the attempt in flight
    (and, during a blind re-send, the errored first attempt) was never charged, and --finalize-abandoned then refused
    ('already final'). Case 1: cancelled in r0001's first call. Case 2: r0001 answers, r0002's first attempt fails at
    transport and its blind re-send is cancelled in flight. Every attempt the guard admitted is now charged."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [NO_CHANGE, APIConnectionError('down')], []
    monkeypatch.setattr(FakeOpenAI, 'cancel_on', cancel_on)
    with pytest.raises(asyncio.CancelledError):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert len(FakeOpenAI.calls) == cancel_on
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'CancelledError' and probe._final(manifest)
    assert manifest['attempts'] == attempts and manifest['charged_upper_bound'] == pytest.approx(attempts * 0.04984)
    assert manifest['unrecorded_attempts_charged'] == unrecorded and manifest['generations_delivered'] == delivered
    assert manifest['in_flight_request'] == {'request_id': f'r{1 + (cancel_on > 1):04d}', 'kind': 'first'}
    with pytest.raises(probe.PlanningError, match='already final'):
        probe.finalize_abandoned(str(tmp_path / 'artifacts' / probe.CLAIM_DIR / 'claim-01.json'), alive=lambda pid: False)
    if delivered:
        with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
            probe.check_output('artifacts/phase28a-test/live-2')
        return
    # Nothing arrived: the read-out says so, and the next launch has the rest of the cap and needs the owner's approval.
    readouts = probe.recompute_readouts(tmp_path / args.out)
    assert readouts['decision'] == 'INCOMPLETE' and readouts['any_generation_arrived'] is False
    assert readouts['statement'].startswith('INCOMPLETE: 0 of 3 draws delivered and no generation arrived')
    earlier = probe.earlier_live_runs(tmp_path / 'artifacts')
    assert earlier == [{'manifest': f'{args.out}/{probe.MANIFEST_NAME}', 'charged_upper_bound': 0.04984}]
    assert probe.phase_spend_remaining(earlier) == pytest.approx(5.0 - 0.04984)
    again = SimpleNamespace(**{**vars(args), 'out': 'artifacts/phase28a-test/live-2'})
    with pytest.raises(probe.PlanningError, match="needs the owner's approval"):
        probe.run_live(again, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / again.out).exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR / 'claim-02.json').exists()
    record = _relaunch_record(tmp_path, plan, earlier, again.out)
    monkeypatch.setattr(FakeOpenAI, 'cancel_on', None)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    assert probe.run_live(SimpleNamespace(**{**vars(again), 'relaunch_approval': record}), plan, prompts,
                          sleep=FakeSleep(), status=IDLE) == 0
    second = json.loads((tmp_path / again.out / probe.MANIFEST_NAME).read_text())
    assert second['status'] == 'COMPLETED' and second['spend_cap'] == pytest.approx(5.0 - 0.04984)
    assert second['relaunch_approval']['path'] == record and second['earlier_undelivered_runs'] == earlier
    assert second['relaunch_approval']['sha256'] == probe.sha256_file(tmp_path / record)
    claim = json.loads((tmp_path / 'artifacts' / probe.CLAIM_DIR / 'claim-02.json').read_text())
    assert claim['relaunch_approval'] == second['relaunch_approval']
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase28a-test/live-3')


def test_an_existing_output_is_never_resumed_and_a_racing_claim_is_refused(tmp_path, monkeypatch):
    """Review round 1 (E7): an existing --out is refused (the only guard against a resume), and two launches that
    read the same earlier-run state cannot both take the same claim number."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    (artifacts / 'phase28a-test/live').mkdir(parents=True)
    with pytest.raises(probe.PlanningError, match='never resumed or overwritten'):
        probe.check_output('artifacts/phase28a-test/live')
    snapshot = probe.live_run_records(artifacts)
    monkeypatch.setattr(probe, 'live_run_records', lambda _: snapshot)
    first, _ = probe.take_claim(artifacts / 'phase28a-test/live-a', 'p', 'h', spend_cap=5.0)
    assert first.name == 'claim-01.json'
    with pytest.raises(probe.PlanningError, match='already taken'):
        probe.take_claim(artifacts / 'phase28a-test/live-b', 'p', 'h', spend_cap=5.0)
    assert sorted(p.name for p in (artifacts / probe.CLAIM_DIR).iterdir()) == ['claim-01.json']


@needs_store
@pytest.mark.parametrize('case', ['entity', 'project', 'configuration', 'mechanic_model'])
def test_the_gates_after_the_credential_read_refuse_without_claiming(tmp_path, monkeypatch, dry_settings, case):
    """Review round 1 (E10): a wrong entity, a wrong project, a moved configuration hash or another Mechanic model
    refuses after the credential read, with nothing claimed and no call made."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    fake = _fake_settings(dry_settings)
    if case == 'entity':
        args = SimpleNamespace(**{**vars(args), 'confirm_entity': 'someone-else'})
        message = '--confirm-entity'
    elif case == 'project':
        fake = dataclasses.replace(fake, wandb_project='OtherProject')
        message = 'Settings project'
    elif case == 'configuration':
        monkeypatch.setattr(probe, 'configuration_pins',
                            lambda settings: {**s2.configuration_pins(settings), 'configuration_hash': '0' * 64})
        monkeypatch.setattr(probe, 'check_pins', lambda pins: None)
        message = 'differs from the declared pin'
    else:
        pins = s2.configuration_pins(fake)   # the declared pins, taken before the role is changed
        monkeypatch.setattr(probe, 'configuration_pins', lambda settings: pins)
        monkeypatch.setattr(type(fake), 'model_for_role', lambda self, role: 'another/model', raising=True)
        message = 'Mechanic role'
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: fake)
    with pytest.raises(probe.PlanningError, match=message):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / args.out).exists()
    assert FakeOpenAI.calls == []


@pytest.mark.parametrize('attempts_per_run,launches', [(12, 4), (10, 5), (2, 21), (1, 41)])
def test_the_phase_cap_admits_between_4_and_41_launches_after_runs_that_delivered_nothing(
        tmp_path, monkeypatch, attempts_per_run, launches):
    """Review round 2, finding 2 (the reviewer's arithmetic): a launch is admitted only while the rest of the $5 phase
    cap covers the 60 planned calls ($2.99), so earlier zero-delivery runs may have been charged at most 40 attempts
    in total. A finished zero-delivery run is charged at most 10 (five errored draws, each with a blind re-send): 5
    launches in all. One closed by --finalize-abandoned may carry 2 in-flight attempts more (12): 4. At 2 attempts per
    run 21 fit, at 1 attempt 41. Each launch after the first also needs the owner's relaunch approval (RELAUNCH_RULE;
    test_a_launch_after_runs_that_delivered_nothing_needs_the_owners_relaunch_approval)."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    allowed = 0
    for index in range(1, 100):
        earlier = probe.earlier_live_runs(artifacts)
        try:
            probe.check_budget(probe.PLANNED_CALLS, probe.effective_spend_cap(5.0, earlier))
        except probe.PlanningError as error:
            assert 'exceed' in str(error)
            assert probe.phase_spend_remaining(earlier) < probe.PLANNED_CALLS * probe.PER_REQUEST_DOLLAR_BOUND
            break
        allowed += 1
        _manifest(artifacts, f'phase28a-test/run-{index:03d}', charged_upper_bound=attempts_per_run * 49_840 / 1_000_000,
                  statuses={'error': attempts_per_run})
    assert allowed == launches
    assert sum(run['charged_upper_bound'] for run in probe.earlier_live_runs(artifacts)) == pytest.approx(
        launches * attempts_per_run * 0.04984)


def test_runs_that_sent_nothing_are_charged_nothing_and_never_use_up_the_cap(tmp_path, monkeypatch):
    """A run that ended before sending anything (a stop before the first request, another paid run seen after the
    claim) is charged $0, so the cap never refuses the next launch; the owner's relaunch approval still does."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    for index in range(1, 51):
        _manifest(artifacts, f'phase28a-test/run-{index:03d}', charged_upper_bound=0.0, statuses={})
    assert probe.effective_spend_cap(5.0, probe.earlier_live_runs(artifacts)) == 5.0


def test_a_launch_after_runs_that_delivered_nothing_needs_the_owners_relaunch_approval(tmp_path, monkeypatch):
    """Review round 2, finding 2, option (b): design §6.0 makes completing an INCOMPLETE run the owner's decision.
    Round 1 let a run that delivered nothing be followed by launches with no approval. Now: with no earlier run the
    argument must be absent; after runs that delivered nothing, a launch needs the owner's record naming exactly it
    (earlier runs, out, plan, harness), refused before any credential read or claim otherwise; one record admits one
    launch, because the next launch sees one more earlier run."""
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    artifacts = tmp_path / 'artifacts'
    with_record = lambda record: SimpleNamespace(**{**vars(args), 'relaunch_approval': record})  # noqa: E731
    stray = _relaunch_record(tmp_path, plan, [], args.out)
    assert 'there is none' in _refused_before_credentials(tmp_path, monkeypatch, with_record(stray), plan, prompts)
    _manifest(artifacts, 'phase28a-earlier/run-1')
    earlier = probe.earlier_live_runs(artifacts)
    assert earlier == [{'manifest': f'artifacts/phase28a-earlier/run-1/{probe.MANIFEST_NAME}', 'charged_upper_bound': 0.4984}]
    message = _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    assert "needs the owner's approval" in message and json.dumps(earlier) in message and args.out in message
    for fields, expected in (({'status': 'pending'}, 'approved'), ({'status': ...}, 'approved'),
                             ({'approved_by': ' '}, 'approved_by'), ({'approved_at': ...}, 'approved_at'),
                             ({'earlier_undelivered_runs': []}, 'exactly this launch'),
                             ({'earlier_undelivered_runs': [{**earlier[0], 'charged_upper_bound': 0.0}]}, 'exactly this launch'),
                             ({'out': 'artifacts/phase28a-test/other'}, 'exactly this launch'),
                             ({'plan_hash': '0' * 64}, 'exactly this launch'),
                             ({'harness_sha256': '0' * 64}, 'exactly this launch')):
        record = _relaunch_record(tmp_path, plan, earlier, args.out, **fields)
        assert expected in _refused_before_credentials(tmp_path, monkeypatch, with_record(record), plan, prompts)
    # The record's place is checked before it is read: artifacts/phase28a-<date>/relaunch-approval-NN.json only.
    out = probe.check_output(args.out, live=False)
    for where in ('artifacts/phase28a-earlier/run-1/relaunch-approval-01.json', 'artifacts/elsewhere/relaunch-approval-01.json',
                  'artifacts/phase28a-earlier/approval.json', f'artifacts/{probe.CLAIM_DIR}/relaunch-approval-01.json',
                  str(tmp_path.parent / 'relaunch-approval-01.json')):
        with pytest.raises(probe.PlanningError, match='must name artifacts/'):
            probe.check_relaunch_approval(where, earlier, out, probe.plan_hash(plan), probe.sha256_file(probe.__file__))
    (artifacts / 'phase28a-earlier/relaunch-approval-02.json').write_text('not json')
    assert 'No readable relaunch approval' in _refused_before_credentials(
        tmp_path, monkeypatch, with_record('artifacts/phase28a-earlier/relaunch-approval-02.json'), plan, prompts)
    # The owner's record for exactly this launch passes every offline check; the next step is the credential read.
    record = _relaunch_record(tmp_path, plan, earlier, args.out)
    with pytest.raises(CredentialRead):
        probe.run_live(with_record(record), plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / args.out).exists() and not (artifacts / probe.CLAIM_DIR).exists()
    # Once another run has ended with nothing delivered, the same record no longer names the launch.
    _manifest(artifacts, 'phase28a-earlier/run-2')
    assert 'exactly this launch' in _refused_before_credentials(tmp_path, monkeypatch, with_record(record), plan, prompts)


def test_readouts_refuse_until_the_run_has_ended(tmp_path):
    directory = tmp_path / 'run'
    directory.mkdir()
    with pytest.raises(probe.PlanningError, match='No readable'):
        probe.recompute_readouts(directory)
    (directory / probe.MANIFEST_NAME).write_text(json.dumps({'status': 'RUNNING', 'ended_at': None}))
    with pytest.raises(probe.PlanningError, match='has not ended'):
        probe.recompute_readouts(directory)
    plan, prompts = _small_plan(1)
    (directory / probe.MANIFEST_NAME).write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x',
                                                             'harness_sha256': '0' * 64, 'plan_hash': probe.plan_hash(plan)}))
    (directory / 'plan.json').write_text(json.dumps(plan))
    (directory / 'prompts.jsonl').write_text(''.join(json.dumps(p) + '\n' for p in prompts.values()))
    (directory / 'responses.jsonl').write_text(json.dumps(_line(plan['requests'][0], 'first', raw=FIRING)) + '\n')
    with pytest.raises(probe.PlanningError, match="NOT THE RUN'S HARNESS"):
        probe.recompute_readouts(directory)
    labelled = probe.recompute_readouts(directory, allow_other_harness=True)
    assert labelled['harness_matches_run'] is False and labelled['readouts']['decision'] == 'GO'
