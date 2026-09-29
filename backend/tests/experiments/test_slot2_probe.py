"""Offline checks of the Phase 25 slot-2 probe. No provider call, no .env read, no store write."""
import asyncio
from collections import Counter
import dataclasses
from fractions import Fraction
import importlib.util
import json
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('slot2_probe', ROOT / 'scripts/experiments/slot2_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['slot2_probe'] = probe
SPEC.loader.exec_module(probe)

from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.lab.policy_state import PolicyState  # noqa: E402
from app.providers.runtime import RuntimeProvider, RuntimeProviderError  # noqa: E402

STORE = ROOT / 'artifacts/lab.sqlite3'

# The Phase 17 settings file lives under the git-ignored artifacts/ folder, so a fresh clone does not have it.
# Tests that read it skip there with this reason (as test_run_dev_probe.py and test_run_gap_probe.py already
# do); where the file exists they run unchanged.
PHASE17_SETTINGS_ABSENT = not (ROOT / probe.DECLARED_SETTINGS).is_file()
NO_PHASE17_SETTINGS = ('needs the Phase 17 settings file (artifacts/phase16-2026-09-22/settings-phase17.json; '
                       'git-ignored, so a fresh clone does not have it)')
needs_phase17_settings = pytest.mark.skipif(PHASE17_SETTINGS_ABSENT, reason=NO_PHASE17_SETTINGS)


@pytest.fixture(autouse=True)
def no_real_process_list(monkeypatch):
    """No test reads the machine's real process list; the process guard is tested with injected rows."""
    monkeypatch.setattr(probe, 'process_list', lambda: [])


def _policy(rules, explanation='A bounded recovery policy.'):
    return json.dumps({'candidate': {'scope': 'orders.upgrade_then_confirm/v1', 'parent_version': 'policy-v0',
                                     'rules': rules}, 'explanation': explanation})


STEP_RULE = {'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
             'steps': [{'op': 'retry_original_request', 'service': 'notifications'}]}
READ_RULE = {'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
             'steps': [{'op': 'read_notification_operation'},
                       {'op': 'require_receipt', 'service': 'notifications', 'status': 'SUCCEEDED'}]}
# A premature defer (pitfall 78): harmful, and it does not stop the source path.
DEFER_RULE = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
              'steps': [{'op': 'defer_unresolved'}]}
STEP = _policy([STEP_RULE])
NO_STEP = _policy([READ_RULE])
STEP_AND_DEFER = _policy([STEP_RULE, DEFER_RULE])
NO_CHANGE = json.dumps({'no_change_reason': 'nothing supported'})


def _hash(raw):
    return content_hash(probe.parse_policy(raw).candidate)


REFERENCE = {'slot1_policy_hash': _hash(NO_STEP), 'slot1_raw_sha256': probe.sha256_text(NO_STEP),
             'slot1_rules_text_sha256': probe.sha256_text(probe.rules_text(NO_STEP)),
             'slot1_step_fires': False, 'slot1_harmful': False,
             'historical_raw_sha256': probe.sha256_text(NO_STEP), 'historical_policy_hash': _hash(NO_STEP),
             'historical_class': 'CANDIDATE', 'historical_duplicate_of_slot1': True, 'historical_attempts': 1}
REFERENCE_SLOT1_FIRES = {**REFERENCE, 'slot1_step_fires': True}


# ---------------------------------------------------------------- the real store (read-only)

def _tree_is_the_declared_configuration():
    try:
        settings = probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)
        return probe.configuration_pins(settings)['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    except Exception:
        return False


needs_store = pytest.mark.skipif(not STORE.exists() or not _tree_is_the_declared_configuration(),
                                 reason='needs the local lab store and the tree Phase 25 is pinned to')


@pytest.fixture(scope='module')
def real_plan():
    if not STORE.exists() or not _tree_is_the_declared_configuration():
        pytest.skip('needs the local lab store and the tree Phase 25 is pinned to')
    return probe.build_plan()


@pytest.fixture(scope='module')
def dry_settings():
    if PHASE17_SETTINGS_ABSENT:
        pytest.skip(NO_PHASE17_SETTINGS)
    return probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)


@needs_store
def test_every_slot_verifies_and_the_census_is_the_phase17_and_23_studies(real_plan):
    plan, prompts = real_plan
    assert plan['populations']['by_phase'] == {'phase17': 5, 'phase23': 21}
    assert plan['populations']['verification_failures'] == []
    assert plan['verification']['slots_checked'] == plan['verification']['slots_verified'] == 52
    assert 'stored_payload_canonical' in plan['verification']['rule'] and len(plan['verification']['rule']) == 12
    assert plan['populations']['slot2_prompts'] == 26 and len(plan['populations']['prompts_whose_slot1_policy_fires']) == 2
    assert plan['populations']['excluded_in_scope'] == {'no_slot2_proposal': 13}
    assert plan['counts']['by_population_and_arm'] == {'slot2/C': 78, 'slot2/H': 78, 'slot2/N': 26, 'slot2/T': 78}
    assert plan['counts']['total_requests'] == 260 and plan['counts']['distinct_prompts'] == 78 == len(prompts)
    assert plan['cost']['planned_upper_bound'] == pytest.approx(12.9584) and plan['cost']['retry_headroom_attempts'] == 40
    assert plan['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert plan['mechanic_model_settings']['temperature'] == 0


@needs_store
def test_every_rebuilt_prompt_is_what_the_real_mechanic_sends(real_plan):
    """All 52 stored contexts, and the C, H and N arm prompts: the harness's rebuild equals the messages the
    real Mechanic.propose_completion sends for that context (captured with a fake provider)."""
    from app.agents.mechanic import Mechanic
    plan, prompts = real_plan
    by_prompt = {}
    for request in plan['requests']:
        by_prompt.setdefault(request['prompt_id'], {})[request['arm']] = request['messages_hash']
    seen = []

    class Provider:
        def role_model(self, role):
            return probe.EXPECTED_MECHANIC_MODEL

        async def complete(self, messages, **kwargs):
            seen.append((messages, kwargs))
            return SimpleNamespace(content=NO_STEP, model_id=probe.EXPECTED_MECHANIC_MODEL, input_tokens=1,
                                   output_tokens=1, cost_usd=None)

    def sent(context):
        seen.clear()
        ledger = SimpleNamespace(consume_call=lambda **_: None, reconcile=lambda _: None)
        store = SimpleNamespace(put_record=lambda *_, **__: None)
        asyncio.run(Mechanic(Provider(), store, ledger).propose_completion(context))
        messages, kwargs = seen[0]
        assert kwargs == {'role': 'mechanic', 'max_output_tokens': 2000, 'timeout_seconds': 20}
        return messages
    connection = probe.connect(STORE)
    checked = Counter()
    try:
        for study_id in plan['populations']['studies']:
            for slot in (1, 2):
                context, _ = probe.load_record(connection, 'completion_proposal_inputs', f'{study_id}-{slot}')
                assert sent(context) == probe.mechanic_messages(context)
                checked['slots'] += 1
                if slot == 2:
                    for arm in ('C', 'H', 'N'):
                        messages_hash = by_prompt[f'{study_id}:slot2'][arm]
                        assert sent(probe.arm_context(context, arm)) == prompts[messages_hash]['messages'], arm
                        checked[arm] += 1
    finally:
        connection.close()
    assert checked == {'slots': 52, 'C': 26, 'H': 26, 'N': 26}


def _copy_study_records(tmp_path, study_id):
    """A tmp store holding exactly the records verify_slot reads for one study."""
    source = probe.connect(STORE)
    target_path = tmp_path / 'copy.sqlite3'
    target = sqlite3.connect(target_path)
    target.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,'
                   'immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    study, _ = probe.load_record(source, 'completion_studies', study_id)
    wanted = [('completion_studies', study_id), ('configurations', study['configuration_hash'])]
    wanted += [('completion_proposal_inputs', f'{study_id}-{slot}') for slot in (1, 2)]
    wanted += [('evidence', row['trial']['episode_id']) for row in study['trial_rows']]
    for candidate in study['candidates']:
        record, _ = probe.load_record(source, 'mechanic_outputs', candidate['proposal_ref'])
        for (ref,) in source.execute("select id from records where kind='mechanic_outputs' and "
                                     "json_extract(payload,'$.request_id')=?", (record['request_id'],)):
            wanted.append(('mechanic_outputs', ref))
    for kind, record_id in wanted:
        row = source.execute('select kind,id,payload,immutable from records where kind=? and id=?',
                             (kind, record_id)).fetchone()
        if row:
            target.execute('insert into records values(?,?,?,?)', row)
    target.commit()
    source.close()
    return target, study


def _tamper(connection, kind, record_id, change, *, serialise=canonical_json):
    payload = json.loads(connection.execute('select payload from records where kind=? and id=?',
                                            (kind, record_id)).fetchone()[0])
    change(payload)
    connection.execute('update records set payload=? where kind=? and id=?', (serialise(payload), kind, record_id))
    connection.commit()


@needs_store
def test_a_tampered_input_fails_exactly_its_check(tmp_path, real_plan, dry_settings):
    plan, _ = real_plan
    pins = probe.configuration_pins(dry_settings)
    study_id = plan['populations']['studies'][0]
    connection, study = _copy_study_records(tmp_path, study_id)

    def failed():
        _, checks, _ = probe.verify_slot(connection, study, 2, pins)
        return sorted(k for k, v in checks.items() if not v)
    assert failed() == [] and probe.verify_slot(connection, study, 2, pins)[2]['framing'] == probe.FRAMING_TOKENS
    first = study['trial_rows'][0]['trial']['episode_id']
    ref = study['candidates'][1]['proposal_ref']
    key = f'{study_id}-2'
    settings_change = lambda c: c['model_settings_by_role']['mechanic'].update(max_output_tokens=4000)  # noqa: E731
    for kind, record_id, change, serialise, expected in (
            ('evidence', first, lambda e: e['observations'][0].update(delivered_tick=(e['observations'][0]['delivered_tick'] + 1) % 20),
             canonical_json, ['development_evidence']),
            ('evidence', first, lambda e: e['observations'][0].update(delivered_tick=99), canonical_json,
             ['development_evidence']),
            ('mechanic_outputs', ref, lambda m: m['usage'].update(input_tokens=m['usage']['input_tokens'] + 1),
             canonical_json, ['provider_token_fingerprint']),
            ('completion_proposal_inputs', key, lambda c: c['candidate_history'][0].update(decision='SOURCE_QUALIFIED'),
             canonical_json, ['candidate_history', 'provider_token_fingerprint']),
            ('completion_proposal_inputs', key, lambda c: c['observed_outcomes'].pop(), canonical_json,
             ['observed_outcomes', 'provider_token_fingerprint']),
            ('completion_proposal_inputs', key, lambda c: c.update(parent_version='policy-v9'), canonical_json,
             # A same-count substitution keeps the provider's token count: the fingerprint is a count, not
             # a hash, which is why the recomputation checks carry the byte-level claim.
             ['fixed_fields']),
            # The same value stored with other bytes: only the stored-bytes check can see it.
            ('completion_proposal_inputs', key, lambda c: None, json.dumps, ['stored_payload_canonical']),
            ('configurations', study['configuration_hash'], settings_change, canonical_json,
             ['configuration_source_and_contract']),
            ('configurations', study['configuration_hash'], lambda c: c.update(dependency_lock_hash='0' * 64),
             canonical_json, ['configuration_source_and_contract'])):
        original = connection.execute('select payload from records where kind=? and id=?', (kind, record_id)).fetchone()[0]
        _tamper(connection, kind, record_id, change, serialise=serialise)
        assert failed() == expected, (kind, expected)
        connection.execute('update records set payload=? where kind=? and id=?', (original, kind, record_id))
        connection.commit()
    assert failed() == []
    connection.execute('update records set immutable=0 where kind=? and id=?', ('completion_proposal_inputs', key))
    connection.commit()
    assert failed() == ['input_record_immutable']
    connection.close()


@needs_store
def test_the_arms_differ_from_the_control_by_exactly_the_declared_change(real_plan):
    plan, prompts = real_plan
    precheck = plan['precheck']
    assert precheck['passed'] and precheck['slot2_prompts'] == 26
    assert precheck['N_differs_only_by_an_empty_candidate_history'] == precheck['N_user_message_holds_no_prior_candidate'] == 26
    by_prompt = {}
    for request in plan['requests']:
        by_prompt.setdefault(request['prompt_id'], {})[request['arm']] = request
    assert len(by_prompt) == 26
    for prompt_id, arms in by_prompt.items():
        control, tempered, hidden, reference = arms['C'], arms['T'], arms['H'], arms['N']
        assert tempered['messages_hash'] == control['messages_hash'] and tempered['temperature'] == 0.7
        assert tempered['request_hash'] != control['request_hash']
        assert hidden['temperature'] == control['temperature'] == reference['temperature'] == 0
        c_messages = prompts[control['messages_hash']]['messages']
        h_messages = prompts[hidden['messages_hash']]['messages']
        n_messages = prompts[reference['messages_hash']]['messages']
        assert h_messages[0] == c_messages[0] == n_messages[0]
        c_user, h_user, n_user = (json.loads(m[1]['content']) for m in (c_messages, h_messages, n_messages))
        assert all('raw_outputs' not in entry and 'content' in entry for entry in h_user['candidate_history'])
        for entry, original in zip(h_user['candidate_history'], c_user['candidate_history']):
            entry['raw_outputs'] = original['raw_outputs']
        assert canonical_json(h_user) == canonical_json(c_user)
        assert n_user['candidate_history'] == [] and control['reference']['slot1_policy_hash'] not in n_messages[1]['content']
        n_user['candidate_history'] = c_user['candidate_history']
        assert canonical_json(n_user) == canonical_json(c_user)


@needs_store
def test_the_request_order_is_round_one_with_every_arm_then_rounds_two_and_three(real_plan):
    plan, _ = real_plan
    requests = plan['requests']
    assert [r['request_id'] for r in requests] == [f'r{i:04d}' for i in range(1, 261)]
    assert all(r['population'] == 'slot2' for r in requests)
    assert [r['repeat'] for r in requests[:104]] == [0] * 104
    for start in range(0, 104, 4):
        block = requests[start:start + 4]
        assert len({r['prompt_id'] for r in block}) == 1 and {r['arm'] for r in block} == {'C', 'T', 'H', 'N'}
    assert [r['repeat'] for r in requests[104:182]] == [1] * 78 and [r['repeat'] for r in requests[182:]] == [2] * 78
    for start in range(104, 260, 3):
        block = requests[start:start + 3]
        assert len({r['prompt_id'] for r in block}) == 1 and {r['arm'] for r in block} == {'C', 'T', 'H'}
    fires = {r['prompt_id'] for r in requests if r['reference']['slot1_step_fires']}
    assert sorted(fires) == plan['populations']['prompts_whose_slot1_policy_fires']


@needs_store
def test_the_investigation_records_the_census_and_the_auditor_matches_what_stored_candidates_did(real_plan):
    plan, _ = real_plan
    mechanism = plan['investigation']['mechanism']
    totals = mechanism['totals']
    assert mechanism['studies'] == 26 and mechanism['framing_tokens_observed'] == [24]
    assert totals['slot2_input_differs'] == 26 and totals['slot1_raw_text_in_slot2_input'] == 26
    assert totals['policy_duplicate_of_slot1'] == 18 and totals['rules_text_identical_to_slot1'] == 18
    assert totals['byte_identical_to_slot1'] == 1
    assert totals['duplicates_whose_explanation_claims_different'] == 16
    assert totals['duplicates_whose_explanation_mentions_retry_without_the_step'] == 10
    # The one historical distinct firing draw is a premature defer, so it is not WORKING.
    assert totals['distinct_firing'] == 1 and totals['distinct_working'] == 0
    assert totals['slot1_step_fires'] == 2 and totals['slot1_harmful'] == 2
    layout = plan['investigation']['slot1_layout_identity']
    assert (layout['same_policy_pairs'], layout['rules_text_identical'], layout['raw_identical']) == (6, 5, 0)
    assert (layout['census_same_policy_pairs'], layout['census_rules_text_identical']) == (5, 4)
    validation = plan['investigation']['auditor_validation']
    assert validation['agreement'] == validation['candidates_with_triggered_source_trials'] == 40
    assert validation['static_fires_vs_dynamic'] == {'static_fires/dynamic_all': 10, 'static_silent/dynamic_none': 30}
    rows = validation['premature_defer_vs_terminal_rejection']
    assert all(row['premature_defer'] == row['terminal_rejection_regressed'] for row in rows) and len(rows) == 6


@needs_store
def test_the_dry_plan_never_reads_env_and_refuses_an_altered_settings_file(tmp_path, monkeypatch, real_plan):
    real = probe.settings_from_file
    seen = []

    def spy(path, *, env_path):
        seen.append(env_path)
        return real(path, env_path=env_path)
    monkeypatch.setattr(probe, 'settings_from_file', spy)
    plan, _ = probe.build_plan()
    assert seen == [os.devnull] and probe.plan_hash(plan) == probe.plan_hash(real_plan[0])
    altered = tmp_path / 'settings.json'
    altered.write_text((ROOT / probe.DECLARED_SETTINGS).read_text().replace('0.55', '0.56'))
    with pytest.raises(probe.PlanningError, match='not the declared Phase 17 settings'):
        probe.build_plan(settings_path=altered)


@needs_store
def test_check_pins_and_the_freeze_refuse_each_altered_pin(dry_settings, tmp_path):
    pins = probe.configuration_pins(dry_settings)
    probe.check_pins(pins)
    for change, message in (({'configuration_hash': '0' * 64}, 'configuration_hash'),
                            ({'mechanic_model': 'other'}, 'Mechanic model'),
                            ({'mechanic_model_settings': {**pins['mechanic_model_settings'], 'temperature': 0.7}},
                             'frozen ones'),
                            ({'per_request_dollar_bound': 0.05}, 'dollar bound')):
        with pytest.raises(probe.PlanningError, match=message):
            probe.check_pins({**pins, **change})
    assert probe.check_freeze(pins)['freeze_sha256'] == probe.DECLARED_FREEZE_SHA256
    with pytest.raises(probe.PlanningError, match='no longer matches'):
        probe.check_freeze({**pins, 'source_hash': '0' * 64})


@needs_phase17_settings
def test_build_plan_runs_the_pin_and_freeze_checks(monkeypatch):
    def refuse(message):
        def check(*_, **__):
            raise probe.PlanningError(message)
        return check
    monkeypatch.setattr(probe, 'check_pins', refuse('pins sentinel'))
    with pytest.raises(probe.PlanningError, match='pins sentinel'):
        probe.build_plan()
    monkeypatch.setattr(probe, 'check_pins', lambda pins: None)
    monkeypatch.setattr(probe, 'check_freeze', refuse('freeze sentinel'))
    with pytest.raises(probe.PlanningError, match='freeze sentinel'):
        probe.build_plan()


@needs_store
def test_the_census_must_equal_the_run_manifests_and_honours_the_cutoff(monkeypatch, dry_settings):
    pins = probe.configuration_pins(dry_settings)
    manifest_studies = probe.manifest_studies
    assert set(manifest_studies().values()) == {'phase17', 'phase23'} and len(manifest_studies()) == 26
    connection = probe.connect(STORE)
    try:
        studies, _ = probe.load_population(connection)
        earlier, excluded = probe.load_population(connection, cutoff=studies[-1]['created_at'])
        assert len(earlier) == len(studies) - 1 and 'at_or_after_cutoff' not in excluded
        outside = probe.store_outside_scope(connection, cutoff=studies[-1]['created_at'])
        assert outside['declared_configuration_at_or_after_cutoff'] >= 1
        monkeypatch.setattr(probe, 'manifest_studies', lambda root=None: {s['study_id']: 'phase23' for s in studies[1:]})
        with pytest.raises(probe.PlanningError, match='differs from the Phase 17 and 23 run manifests'):
            probe.survey(connection, pins)
    finally:
        connection.close()
    monkeypatch.setattr(probe, 'PHASE_MANIFESTS', {'phase17': (probe.PHASE_MANIFESTS['phase17'][0], '0' * 64)})
    with pytest.raises(probe.PlanningError, match='not the pinned one'):
        manifest_studies()


def test_studies_outside_the_scope_never_enter_the_plan_counts(tmp_path):
    """A later study, or one of another configuration, is counted in the dry summary only, so it cannot move
    the plan hash (review round 1)."""
    path = tmp_path / 'store.sqlite3'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,'
                       'immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    declared = probe.DECLARED_CONFIGURATION_HASH
    for index, study in enumerate(({'configuration_hash': '0' * 64, 'created_at': '2026-09-01T00:00:00Z'},
                                   {'configuration_hash': declared, 'created_at': '2026-09-30T00:00:00Z'},
                                   {'configuration_hash': declared, 'created_at': '2026-09-23T00:00:00Z',
                                    'replay_of': 'x'})):
        connection.execute('insert into records values(?,?,?,0)',
                           ('completion_studies', f's{index}', json.dumps({'study_id': f's{index}', **study})))
    connection.commit()
    connection.close()
    connection = probe.connect(path)
    try:
        assert probe.load_population(connection) == ([], {'replay': 1})
        assert probe.store_outside_scope(connection) == {'declared_configuration_at_or_after_cutoff': 1,
                                                         'other_configuration': 1}
    finally:
        connection.close()


# ---------------------------------------------------------------- the static auditor (pure)

class AbstractPolicyState(PolicyState):
    """The runtime's own PolicyState.condition, fed an abstract state."""

    def __init__(self, state, flag):
        self.state, self.receipt_missing = state, flag

    def receipt(self, service):
        receipt = self.state[service]['receipt']
        return SimpleNamespace(status=receipt) if receipt else None

    def status(self, service):
        receipt = self.state[service]['receipt']
        return receipt if receipt else self.state[service]['status']

    def attempted(self, service):
        return self.state[service]['attempted']


def test_the_abstract_condition_is_the_runtimes_condition():
    from typing import get_args
    from app.contracts.models import Condition
    states = []
    for attempted in (False, True):
        for receipt in (None, 'SUCCEEDED', 'FAILED'):
            for status in (None, 'PENDING', 'UNKNOWN'):
                states.append({'attempted': attempted, 'receipt': receipt, 'status': status})
    for orders in states:
        for notifications in states:
            state = {'orders': orders, 'notifications': notifications}
            for flag in (False, True):
                for name in get_args(Condition):
                    assert probe.condition(name, state, flag) == AbstractPolicyState(state, flag).condition(name), name


def _audit(*rules):
    return probe.audit_policy({'rules': list(rules)})


def test_a_retry_gated_on_pending_is_present_and_dead():
    gated = {**STEP_RULE, 'when': 'notification_operation_pending'}
    only_if = {**STEP_RULE, 'steps': [{'op': 'retry_original_request', 'service': 'notifications',
                                       'only_if': 'notification_operation_pending'}]}
    for rule in (gated, only_if):
        audit = _audit(rule)
        assert audit['step_present'] and not audit['step_fires'] and audit['dead_step']
    for when in ('always', 'notification_outcome_uncertain', 'notification_receipt_missing', 'upgrade_succeeded'):
        assert _audit({**STEP_RULE, 'when': when})['step_fires'], when


def test_a_read_before_the_retry_cannot_make_it_pending():
    rule = {'hook': 'after_notification_response', 'when': 'always', 'steps': [
        {'op': 'read_notification_operation'}, {'op': 'wait_ticks', 'ticks': 1},
        {'op': 'retry_original_request', 'service': 'notifications', 'only_if': 'notification_operation_pending'}]}
    assert not _audit(rule)['step_fires']
    rule['steps'][2]['only_if'] = 'notification_outcome_uncertain'
    assert _audit(rule)['step_fires']


def test_the_receipt_missing_flag_is_hook_local_and_set_by_require_receipt():
    require = {'hook': 'after_notification_response', 'when': 'always',
               'steps': [{'op': 'require_receipt', 'service': 'notifications', 'status': 'SUCCEEDED'}]}
    flagged = {**STEP_RULE, 'when': 'receipt_missing'}
    assert _audit(require, flagged)['step_fires']
    assert not _audit(flagged)['step_fires']
    orders = {**require, 'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}
    assert not _audit(orders, flagged)['step_fires']
    earlier_hook = {**require, 'hook': 'before_confirmation',
                    'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}
    assert not _audit(earlier_hook, flagged)['step_fires']


def test_a_rule_that_stops_the_first_confirmation_kills_the_step():
    block = {'hook': 'before_confirmation', 'when': 'always',
             'steps': [{'op': 'require_receipt', 'service': 'notifications', 'status': 'SUCCEEDED'}]}
    audit = _audit(block, STEP_RULE)
    assert audit['stops_first_confirmation'] and audit['harmful'] and not audit['step_fires'] and audit['dead_step']
    upgrade_receipt = {**block, 'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}
    assert not _audit(upgrade_receipt, STEP_RULE)['stops_first_confirmation']
    close_early = {'hook': 'after_upgrade_response', 'when': 'always', 'steps': [{'op': 'defer_unresolved'}]}
    assert not _audit(close_early, STEP_RULE)['step_fires']
    defer_first = {'hook': 'after_notification_response', 'when': 'always', 'steps': [{'op': 'defer_unresolved'}]}
    assert not _audit(defer_first, STEP_RULE)['step_fires'] and _audit(STEP_RULE, defer_first)['step_fires']


def test_premature_defer_is_a_defer_before_any_wait_on_a_pending_upgrade():
    attempt4 = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain', 'steps': [
        {'op': 'read_current_operation'}, {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'},
        {'op': 'defer_unresolved'}]}
    assert _audit(attempt4)['premature_defer'] and _audit(attempt4)['harmful']
    certified = {**attempt4, 'steps': [{'op': 'read_current_operation'}, {'op': 'wait_ticks', 'ticks': 1},
                                       {'op': 'read_current_operation'}, {'op': 'defer_unresolved'}]}
    assert not _audit(certified)['premature_defer']
    report_side = {**attempt4, 'hook': 'before_final_report'}
    assert not _audit(report_side)['premature_defer']


def test_the_policy_step_cap_is_counted_across_hooks():
    busy = {'hook': 'after_upgrade_response', 'when': 'always', 'steps': [{'op': 'read_order'}] * 8}
    rules = [busy] * 4 + [STEP_RULE]
    assert not _audit(*rules)['step_fires']
    assert _audit(*([busy] * 3 + [STEP_RULE]))['step_fires']
    waits = {'hook': 'after_notification_response', 'when': 'always', 'steps': [{'op': 'wait_ticks', 'ticks': 1}] * 5}
    assert not _audit(waits, STEP_RULE)['step_fires']


def test_classify_response_follows_the_study_rules():
    classify = lambda raw: probe.classify_response(raw, REFERENCE)  # noqa: E731
    assert classify('not json')['class'] == 'INVALID' and classify('')['class'] == 'INVALID'
    assert classify(json.dumps({'candidate': {'rules': []}, 'explanation': 'x'}))['class'] == 'INVALID'
    assert classify(NO_CHANGE)['class'] == 'NO_CHANGE'
    stale = json.loads(STEP)
    stale['candidate']['parent_version'] = 'policy-v9'
    assert classify(json.dumps(stale))['class'] == 'STALE_PARENT'
    notification_retry_elsewhere = _policy([{**STEP_RULE, 'hook': 'before_final_report'}])
    assert classify(notification_retry_elsewhere)['class'] == 'INVALID'
    same = classify(NO_STEP)
    assert same['duplicate_of_slot1'] and same['byte_identical_to_slot1'] and not same['distinct']
    relaid = classify(_policy([READ_RULE], explanation='This materially different policy adds a retry.'))
    assert relaid['duplicate_of_slot1'] and not relaid['byte_identical_to_slot1']
    assert relaid['explanation_claims_different'] and relaid['explanation_mentions_retry']
    working = classify(STEP)
    assert working['distinct'] and working['distinct_firing'] and working['working'] and working['audit']['step_fires']
    harmful = classify(STEP_AND_DEFER)
    assert harmful['distinct_firing'] and harmful['audit']['harmful'] and not harmful['working']


# ---------------------------------------------------------------- statistics and read-outs (pure)

def test_statistics():
    low, high = probe.wilson(3, 30)
    assert (round(low, 3), round(high, 3)) == (0.035, 0.256)
    assert probe.wilson(0, 0) == [None, None]
    assert probe.sign_test_greater(0, 0) == 1.0
    assert probe.sign_test_greater(5, 0) == pytest.approx(1 / 32)
    assert probe.sign_test_greater(8, 2) == pytest.approx(56 / 1024)
    assert probe.sign_test_greater(9, 1) == pytest.approx(11 / 1024)
    low, high = probe.newcombe(20, 26, 7, 26)
    assert low < 20 / 26 - 7 / 26 < high and -1 <= low and high <= 1
    assert probe.newcombe(5, 10, 5, 10)[0] < 0 < probe.newcombe(5, 10, 5, 10)[1]


def _rows(arm, pattern, prompts=26, repeats=3, missing=0, missing_if=None, reference=lambda p: REFERENCE):
    """Draw rows for one arm; pattern(prompt, repeat) returns a raw output. The first `missing` rows, and
    any row where missing_if(prompt, repeat) holds, are missing."""
    rows = []
    for p in range(prompts):
        for r in range(repeats):
            request = {'request_id': f'{arm}{p}-{r}', 'prompt_id': f'p{p}', 'arm': arm, 'repeat': r,
                       'population': 'slot2', 'reference': reference(p)}
            received = len(rows) >= missing and not (missing_if and missing_if(p, r))
            raw = pattern(p, r)
            rows.append({'request': request, 'received': received,
                         'result': {'status': 'ok', 'raw': raw} if received else None,
                         'c': probe.classify_response(raw, request['reference']) if received else None})
    return rows


def _distinct(i):
    return _policy([READ_RULE, {'hook': 'before_final_report', 'when': 'always',
                                'steps': [{'op': 'wait_ticks', 'ticks': 1 + i % 4}]}])


def _harmful_distinct(i):
    return _policy([READ_RULE, DEFER_RULE, {'hook': 'before_final_report', 'when': 'always',
                                            'steps': [{'op': 'wait_ticks', 'ticks': 1 + i % 4}]}])


K = f'working_share_gain_at_least_{probe.gain_label(probe.WORKING_SHARE_GAIN_MIN)}'
HARM = 'harmful_share_of_firing_at_most_0.50'


def test_a_recommendation_needs_every_condition():
    control = _rows('C', lambda p, r: NO_STEP if p % 4 else _distinct(p))
    good = _rows('T', lambda p, r: STEP if p % 3 == 0 else _distinct(p + r))
    result = probe.contrast(good, control, 'T')
    assert result['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP' and result['failed'] == []
    assert result['working_share']['gain'] == 9 and result['working_share']['eligible_prompts'] == 26
    no_step = _rows('T', lambda p, r: _distinct(p + r))
    assert probe.contrast(no_step, control, 'T')['failed'] == [K]
    invalid = _rows('T', lambda p, r: 'not json' if r == 0 else (STEP if p % 3 == 0 else _distinct(p)))
    failed = probe.contrast(invalid, control, 'T')['failed']
    assert 'invalid_at_most_C_plus_0.10' in failed and 'distinct_at_least_0.70' in failed
    harmful = _rows('T', lambda p, r: STEP if p % 3 == 0 else STEP_AND_DEFER)
    assert probe.contrast(harmful, control, 'T')['failed'] == [HARM]
    # Harmful draws whose step does not fire cannot qualify at the source; they are reported, not counted.
    inert = _rows('T', lambda p, r: STEP if p % 3 == 0 else _harmful_distinct(p))
    assert probe.contrast(inert, control, 'T')['failed'] == []
    same = _rows('T', lambda p, r: NO_STEP if p % 4 else _distinct(p))
    assert probe.contrast(same, control, 'T')['decision'] == 'NOT_RECOMMENDED'


def test_the_declared_working_share_minimums_and_their_boundaries():
    """Review rounds 2 and 3: 10/3 over all rounds and 4 in the round-1 fallback, chosen by
    slot2_protocol_numbers.py (round 3 added the repeat model, under which 8/3 acted as a count of 3 prompts)."""
    assert probe.WORKING_SHARE_GAIN_MIN == Fraction(10, 3) and probe.WORKING_SHARE_GAIN_MIN_ROUND1 == 4
    assert K == 'working_share_gain_at_least_3.33'
    control = _rows('C', lambda p, r: NO_STEP if p % 4 else _distinct(p))
    spread = lambda n: _rows('T', lambda p, r: STEP if r == 0 and 2 <= p < 2 + n else _distinct(p + r))  # noqa: E731
    # One WORKING draw on each of 10 prompts is a gain of exactly 10/3 and passes; 9 (a gain of 3) does not.
    assert probe.contrast(spread(10), control, 'T')['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
    assert probe.contrast(spread(9), control, 'T')['failed'] == [K]
    # Review round 3: when every repeat copies its prompt's first draw, a prompt's share is 0 or 1 and the gain is
    # a whole number. Three prompts WORKING on all three draws (a gain of 3) do not pass; four do.
    repeated = lambda n: _rows('T', lambda p, r: STEP if 2 <= p < 2 + n else _distinct(p + r))  # noqa: E731
    assert probe.contrast(repeated(3), control, 'T')['failed'] == [K]
    assert probe.contrast(repeated(4), control, 'T')['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
    r1 = f'working_share_gain_at_least_{probe.gain_label(4)}'
    fallback = lambda n: probe.contrast(probe._round1(spread(n)), probe._round1(control), 'T',  # noqa: E731
                                        working_gain_min=probe.WORKING_SHARE_GAIN_MIN_ROUND1)
    assert fallback(4)['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP' and fallback(3)['failed'] == [r1]


def test_firing_draws_that_are_harmful_do_not_count_as_working():
    """Review round 1: an arm whose every firing draw is a premature defer must not pass condition 5."""
    control = _rows('C', lambda p, r: NO_STEP if p % 4 else _distinct(p))
    treated = _rows('T', lambda p, r: STEP_AND_DEFER if p in (0, 3) else _distinct(p + r))
    result = probe.contrast(treated, control, 'T')
    assert result['failed'] == [K, HARM] and result['working_share']['gain'] == 0
    summary = probe.arm_summary(treated)
    assert summary['distinct_firing'] == summary['distinct_firing_harmful'] == 6 and summary['working'] == 0


def test_the_harmful_limit_is_not_diluted_by_distinct_draws_that_do_not_fire():
    control = _rows('C', lambda p, r: NO_STEP)
    harmful = lambda p, r: (6 <= p < 15 and r < 2) or (p == 15 and r == 0)  # noqa: E731
    treated = _rows('T', lambda p, r: STEP if p < 6 else (STEP_AND_DEFER if harmful(p, r) else _distinct(p + r)))
    result = probe.contrast(treated, control, 'T')
    # 19 harmful of 78 distinct is a share of 0.24, which the round-0 ceiling of 0.25 let through; of the 37
    # draws whose step fires, 19 are harmful.
    assert result['received']['harmful_share_of_distinct_X_descriptive'] == pytest.approx(19 / 78)
    assert result['received']['harmful_share_of_firing_X'] == pytest.approx(19 / 37) and result['failed'] == [HARM]


def test_the_working_share_is_per_prompt_and_leaves_out_prompts_whose_slot1_policy_fires():
    control = _rows('C', lambda p, r: NO_STEP)
    fires = lambda p: REFERENCE_SLOT1_FIRES if p < 9 else REFERENCE  # noqa: E731
    on_fired = _rows('T', lambda p, r: STEP if p < 9 else _distinct(p + r), reference=fires)
    control_fired = _rows('C', lambda p, r: NO_STEP, reference=fires)
    result = probe.contrast(on_fired, control_fired, 'T')
    assert result['working_share']['eligible_prompts'] == 17 and result['working_share']['gain'] == 0
    assert probe.arm_summary(on_fired)['working_on_prompts_whose_slot1_policy_fires'] == 27
    # Three working draws on one prompt add 1, never more.
    one_prompt = _rows('T', lambda p, r: STEP if p < 2 else _distinct(p + r))
    assert probe.contrast(one_prompt, control, 'T')['working_share']['gain'] == 2
    # A missing C draw counts as working on its prompt (worst case for X): 2 - 1/3.
    control_missing = _rows('C', lambda p, r: NO_STEP, missing_if=lambda p, r: p == 0 and r == 2)
    share = probe.contrast(one_prompt, control_missing, 'T')['working_share']
    assert share['gain_exact'] == '5/3' and share['working_or_missing_draws_C_on_eligible'] == 1
    # A missing X draw is not working: X's share is over its planned draws, not its received ones.
    x_missing = _rows('T', lambda p, r: STEP if p < 2 else _distinct(p + r), missing_if=lambda p, r: p == 0 and r > 0)
    assert probe.contrast(x_missing, control, 'T')['working_share']['gain_exact'] == '4/3'
    # Review round 3: a prompt with no rows in one arm is still eligible. With no X rows, X's share there is 0;
    # with no C rows, C's share there is 1 (the worst case for X).
    without = lambda rows, prompt: [r for r in rows if r['request']['prompt_id'] != prompt]  # noqa: E731
    share = probe.working_share(without(one_prompt, 'p25'), control)
    assert share['eligible_prompts'] == 26 and share['gain_exact'] == '2'
    assert probe.working_share(one_prompt, without(control, 'p25'))['gain_exact'] == '1'


def test_the_working_share_is_not_moved_by_how_draws_cluster_within_a_prompt():
    """Review round 2: at equal per-draw WORKING rates the gain is 0, however the draws cluster. Here X has one
    WORKING draw on each of six prompts and C three on each of two: six WORKING draws each. Round 1's count of
    prompts with any WORKING draw called that a gain of 4 for X; it is kept, labelled breadth, deciding nothing."""
    spread = _rows('T', lambda p, r: STEP if p < 6 and r == 0 else _distinct(p + r))
    clustered = _rows('C', lambda p, r: STEP if p >= 24 else NO_STEP)
    result = probe.contrast(spread, clustered, 'T')
    # Every other condition holds; the breadth count (4) would have passed condition 5, the share (0) does not.
    assert result['decision'] == 'NOT_RECOMMENDED' and result['failed'] == [K]
    share = result['working_share']
    assert share['gain'] == 0 and share['working_draws_X_on_eligible'] == 6
    assert share['working_or_missing_draws_C_on_eligible'] == 6
    assert share['breadth_prompt_count_descriptive']['gain'] == 4
    assert (share['prompts_favouring'], share['prompts_against']) == (6, 2)
    # The same working draws, clustered like C's: the same gain.
    same_cluster = _rows('T', lambda p, r: STEP if p < 2 else _distinct(p + r))
    assert probe.contrast(same_cluster, clustered, 'T')['working_share']['gain'] == 0


def test_missing_draws_count_against_the_treatment_and_make_an_arm_incomplete():
    control = _rows('C', lambda p, r: NO_STEP)
    treated = _rows('H', lambda p, r: STEP if p % 3 == 0 else _distinct(p + r), missing=3)
    result = probe.contrast(treated, control, 'H')
    assert result['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
    assert result['worst_case']['D_X'] == pytest.approx(75 / 78) and result['working_share']['gain'] == 8
    short = _rows('H', lambda p, r: STEP, missing=4)
    assert probe.contrast(short, control, 'H')['decision'] == 'INCOMPLETE'
    control_short = _rows('C', lambda p, r: NO_STEP, missing=3)
    result = probe.contrast(treated, control_short, 'H')
    assert result['worst_case']['D_C'] == pytest.approx(3 / 78) and result['worst_case']['W_C_descriptive'] == pytest.approx(3 / 78)


def test_the_mechanism_readout_and_the_evidence_alone_reference():
    control = _rows('C', lambda p, r: NO_STEP if p % 5 else _distinct(p))
    hidden = _rows('H', lambda p, r: _distinct(p + r) if p % 5 else NO_STEP)
    tempered = _rows('T', lambda p, r: NO_STEP)
    reference = _rows('N', lambda p, r: NO_STEP if p % 2 else _distinct(p), repeats=1)
    mechanism = probe.mechanism_readout(control, hidden, tempered, reference)
    assert mechanism['decision'] == 'COPYING_OF_THE_PRIOR_TEXT_SHOWN' and mechanism['failed'] == []
    assert mechanism['N_writes_slot1_policy'] == [13, 26]
    assert probe.mechanism_readout(control, control, tempered, reference)['decision'] == 'NOT_SHOWN'
    assert probe.mechanism_readout(control, _rows('H', lambda p, r: STEP, missing=10), tempered,
                                   reference)['decision'] == 'INCOMPLETE'


@pytest.mark.parametrize('output', [NO_CHANGE, 'not json'])
def test_fewer_duplicates_from_outputs_that_are_no_policy_do_not_show_copying(output):
    """Review round 1: H answering NO_CHANGE or INVALID where C duplicates lowers dup_H without any distinct
    policy; the mechanism read-out must say NOT_SHOWN."""
    control = _rows('C', lambda p, r: NO_STEP if p < 18 else _distinct(p))
    hidden = _rows('H', lambda p, r: output if p < 18 else _distinct(p))
    mechanism = probe.mechanism_readout(control, hidden, [], [])
    assert mechanism['decision'] == 'NOT_SHOWN'
    assert mechanism['conditions']['duplicate_drop_at_least_0.30'] and mechanism['conditions']['sign_test_p_below_0.05']
    assert set(mechanism['failed']) == {'distinct_gain_at_least_0.30', 'non_candidate_at_most_C_plus_0.10'}


def _saved(*row_sets):
    """Planned requests and saved lines from _rows output."""
    requests, results = [], []
    for rows in row_sets:
        for row in rows:
            requests.append(row['request'])
            if row['received']:
                results.append({'request_id': row['request']['request_id'], 'status': 'ok', 'raw': row['result']['raw'],
                                'attempts': [{'attempt': 1}]})
    return requests, results


def _run_end(status='STOPPED', stop_reason='consecutive_errors', **changes):
    return probe.run_end_of({'status': status, 'stop_reason': stop_reason, 'traceback': None, 'stop_signal': None,
                             'resend_pass': None, **changes})


def _stopped_after_round_one():
    control = _rows('C', lambda p, r: NO_STEP if p % 4 else _distinct(p))
    reference = _rows('N', lambda p, r: NO_STEP, repeats=1)
    stopped = lambda p, r: r > 0  # noqa: E731
    tempered = _rows('T', lambda p, r: STEP if p % 3 == 0 else _distinct(p + r), missing_if=stopped)
    hidden = _rows('H', lambda p, r: NO_STEP, missing_if=stopped)
    return control, tempered, hidden, reference


def test_an_incomplete_decision_falls_back_to_a_complete_round_one():
    control, tempered, hidden, reference = _stopped_after_round_one()
    readouts = probe.compute_readouts(*_saved(control, tempered, hidden, reference), run_end=_run_end())
    t, h = readouts['decisions']['T'], readouts['decisions']['H']
    assert t['decision'] == h['decision'] == 'INCOMPLETE'
    assert t['declared'] == {'decision': 'RECOMMEND_FOR_A_LATER_LOOP', 'basis': 'round_1_only', 'failed': []}
    assert t['round1_fallback']['planned_draws'] == {'X': 26, 'C': 26}
    assert (f'working_share_gain_at_least_{probe.gain_label(probe.WORKING_SHARE_GAIN_MIN_ROUND1)}'
            in t['round1_fallback']['conditions'])
    # The all-rounds contrast stays beside the round-1 decision (PHASE25_RESULTS quotes both).
    assert t['worst_case']['D_X'] == pytest.approx(26 / 78) and t['working_share']['gain'] == 3
    assert h['declared']['basis'] == 'round_1_only' and h['declared']['decision'] == 'NOT_RECOMMENDED'
    assert readouts['statement'] == "recommended for a later loop's own declaration: T (round 1 only)"
    assert readouts['mechanism']['decision'] == 'INCOMPLETE' and readouts['mechanism']['declared']['basis'] == 'round_1_only'
    # Review round 2: the mechanism fallback uses round-1 C and round-1 H, 26 planned draws each.
    assert readouts['mechanism']['round1_fallback']['planned_draws'] == {'C': 26, 'H': 26}
    assert readouts['run_end']['round1_fallback_permitted'] is True
    complete = probe.compute_readouts(*_saved(control, _rows('T', lambda p, r: NO_STEP), _rows('H', lambda p, r: NO_STEP),
                                              reference), run_end=_run_end('COMPLETED', 'completed'))
    assert complete['decisions']['T']['round1_fallback'] is None
    assert complete['decisions']['T']['declared']['basis'] == 'all_rounds'


@pytest.mark.parametrize('run_end,permitted', [
    (_run_end('STOPPED', 'spend_guard'), True),
    (_run_end('COMPLETED', 'completed'), True),
    (_run_end('ABORTED', 'PlanningError', traceback='Traceback ...'), True),
    (_run_end('STOPPED', 'operator_stop'), False),
    (_run_end('ABORTED', 'abandoned'), False),
    (_run_end('COMPLETED', 'completed', stop_signal={'signal': 'SIGTERM'}), False),
    (_run_end('STOPPED', 'consecutive_errors', stop_signal={'signal': 'SIGINT'}), False),
    (_run_end('COMPLETED', 'completed', resend_pass={'ended': 'operator_stop'}), False),
    (_run_end('ABORTED', 'another_paid_run_after_claim'), False),
    # Review round 3: a stop reason that permits the fallback counts only with its own final status.
    (_run_end('ABORTED', 'completed'), False),
    (None, False),
])
def test_the_round1_fallback_applies_only_after_a_stop_the_operator_does_not_choose(run_end, permitted):
    """Review round 2: stopping once round 1 has arrived (a signal, or kill -9 then --finalize-abandoned) must
    not choose which rule decides, so an operator stop leaves an INCOMPLETE decision INCOMPLETE."""
    readouts = probe.compute_readouts(*_saved(*_stopped_after_round_one()), run_end=run_end)
    t, mechanism = readouts['decisions']['T'], readouts['mechanism']
    assert readouts['run_end']['round1_fallback_permitted'] is permitted
    if permitted:
        assert t['declared']['basis'] == 'round_1_only' and mechanism['declared']['basis'] == 'round_1_only'
    else:
        assert t['round1_fallback'] is None and mechanism['round1_fallback'] is None
        assert t['declared'] == {'decision': 'INCOMPLETE', 'basis': 'all_rounds', 'failed': t['failed']}
        assert mechanism['declared']['decision'] == 'INCOMPLETE'
        assert readouts['statement'].startswith('no arm is recommended: T INCOMPLETE')


def test_compute_readouts_from_saved_lines():
    requests = [{'request_id': f'r{i:04d}', 'population': 'slot2', 'prompt_id': f'p{i // 3}',
                 'arm': ('C', 'T', 'H')[i % 3], 'repeat': 0, 'reference': REFERENCE} for i in range(6)]
    results = [{'request_id': 'r0000', 'status': 'ok', 'raw': NO_STEP, 'served_model': 'm',
                'attempts': [{'attempt': 1, 'code': 'REQUEST_TIMEOUT'}, {'attempt': 2, 'error': None}]},
               {'request_id': 'r0001', 'status': 'ok', 'raw': STEP, 'served_model': 'm'},
               {'request_id': 'r0002', 'status': 'empty_response', 'raw': None},
               {'request_id': 'r0003', 'status': 'error', 'raw': None, 'attempts': [{'attempt': 1, 'code': 'HTTP_ERROR'}]},
               {'request_id': 'r0003', 'status': 'ok', 'raw': STEP, 'resend': True, 'served_model': 'm',
                'attempts': [{'attempt': 1}]}]
    readouts = probe.compute_readouts(requests, results)
    assert readouts['requests_received'] == 4 and readouts['arms']['C']['duplicate'] == 1
    assert readouts['arms']['T']['working'] == 1 and readouts['arms']['H']['invalid'] == 1
    assert readouts['arms']['C']['missing'] == 0 and readouts['provider']['served_model'] == {'m': 3}
    c = readouts['arms']['C']
    assert (c['received_on_blind_retry'], c['received_on_resend'], c['resent_requests'], c['timeouts']) == (1, 1, 1, 1)
    assert readouts['arms']['T']['never_attempted'] == 1 and readouts['arms']['N']['planned'] == 0
    assert readouts['decisions']['T']['declared']['decision'] == 'INCOMPLETE'
    assert readouts['determinism']['C']['byte_identical_to_historical_output'] == [1, 2]
    # H has no historical output of its own, so it is compared with none.
    assert set(readouts['determinism']['H']) == {'repeat_pairs', 'byte_identical_pairs', 'same_policy_pairs',
                                                 'prompts_all_repeats_byte_identical'}


def test_readouts_refuse_until_the_run_has_ended(tmp_path, capsys):
    """Review round 3: --readouts on a run whose manifest is still RUNNING printed every arm's classes and each
    condition while the run was live. It now refuses until the manifest is final, with or without
    --not-the-runs-harness."""
    control, tempered, hidden, reference = _stopped_after_round_one()
    requests, results = _saved(control, tempered, hidden, reference)
    plan = {'requests': requests}
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    (tmp_path / 'responses.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in results))
    manifest = {'status': 'RUNNING', 'ended_at': None, 'stop_reason': None, 'traceback': None, 'stop_signal': None,
                'resend_pass': None, 'harness_sha256': probe.sha256_file(probe.__file__), 'plan_hash': probe.plan_hash(plan)}
    path = tmp_path / probe.MANIFEST_NAME
    for status, ended_at in (('RUNNING', None), ('STARTING', None), ('COMPLETED', None), (None, 'x')):
        path.write_text(json.dumps({**manifest, 'status': status, 'ended_at': ended_at}))
        for other in (False, True):
            with pytest.raises(probe.PlanningError, match='has not ended'):
                probe.recompute_readouts(tmp_path, allow_other_harness=other)
    assert probe.main(['--readouts', str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    assert 'REJECTED' in printed and 'has not ended' in printed and 'decisions' not in printed
    path.write_text(json.dumps({**manifest, 'status': 'STOPPED', 'stop_reason': 'consecutive_errors',
                                'ended_at': '2026-09-24T00:00:00Z'}))
    assert probe.recompute_readouts(tmp_path)['decisions']['T']['declared']['basis'] == 'round_1_only'


# ---------------------------------------------------------------- live execution (fakes, no network)

def test_spend_guard_admits_exactly_what_the_cap_allows():
    guard = probe.SpendGuard(15.0)
    assert sum(guard.admit() for _ in range(400)) == 300
    assert guard.charged == pytest.approx(300 * 0.04984)
    probe.check_budget(260, 15.0)
    for total, cap in ((301, 15.0), (10, 15.01), (10, 0), (10, float('nan'))):
        with pytest.raises(probe.PlanningError):
            probe.check_budget(total, cap)
    with pytest.raises(probe.PlanningError):
        probe.SpendGuard(25.0)


class FakeProvider:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    async def complete(self, messages, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else STEP
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(content=outcome, model_id=probe.EXPECTED_MECHANIC_MODEL, input_tokens=100,
                               output_tokens=20)


class FakeSleep:
    def __init__(self, on_call=None):
        self.calls, self.on_call = [], on_call

    async def __call__(self, seconds):
        self.calls.append(seconds)
        if self.on_call:
            self.on_call(len(self.calls))

    @property
    def total(self):
        return sum(self.calls)


def _small_plan(n=6):
    requests, prompts = [], {}
    for index in range(n):
        messages = [{'role': 'system', 'content': 'You are a test.'}, {'role': 'user', 'content': f'prompt {index // 3}'}]
        arm = probe.SLOT2_ARMS[index % 3]
        if arm == 'H':
            messages = [messages[0], {'role': 'user', 'content': f'prompt {index // 3} without the raw text'}]
        messages_hash = content_hash(messages)
        prompts[messages_hash] = {'messages_hash': messages_hash, 'messages': messages}
        temperature = probe.ARM_TEMPERATURE[arm]
        requests.append({'request_id': f'r{index + 1:04d}', 'population': 'slot2', 'prompt_id': f's{index // 3}:slot2',
                         'study_id': f's{index // 3}', 'phase': 'phase23', 'arm': arm, 'repeat': 0,
                         'temperature': temperature, 'messages_hash': messages_hash,
                         'request_hash': probe.request_digest(probe.request_body(messages, temperature)),
                         'reference': REFERENCE})
    return {'counts': {'total_requests': n}, 'requests': requests}, prompts


def _run(requests, prompts, provider, guard, recorder, **kwargs):
    kwargs.setdefault('sleep', FakeSleep())
    try:
        return asyncio.run(probe.run_requests(requests, prompts, provider, guard, recorder, **kwargs))
    finally:
        recorder.close()


def _lines(directory):
    return [json.loads(line) for line in (directory / 'responses.jsonl').read_text().splitlines()]


# Review round 2: fields a live line no longer carries (each one said which arm was ahead while the run was live).
LIVE_LINE_FORBIDDEN = ('class', 'policy_hash', 'raw_sha256', 'matches_historical_raw')


def test_live_loop_stops_at_the_spend_guard_and_retries_only_transport_failures(tmp_path):
    plan, prompts = _small_plan(3)
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    guard = probe.SpendGuard(2 * probe.PER_REQUEST_DOLLAR_BOUND)
    assert _run(plan['requests'], prompts, FakeProvider([]), guard, recorder) == 'spend_guard'
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['attempts'] == 2 and manifest['charged_upper_bound'] == pytest.approx(0.09968)
    assert manifest['resend_pass'] is None
    other = tmp_path / 'second'
    other.mkdir()
    recorder = probe.Recorder(other, {'statuses': {}})
    outcomes = [RuntimeProviderError('x', code='CONNECTION_ERROR'), NO_STEP,
                RuntimeProviderError('x', code='HTTP_ERROR'), RuntimeProviderError('x', code='EMPTY_FINAL_RESPONSE')]
    provider, sleep = FakeProvider(outcomes), FakeSleep()
    assert _run(plan['requests'], prompts, provider, probe.SpendGuard(15.0), recorder, sleep=sleep) == 'completed'
    lines = _lines(other)
    # The HTTP error delivered nothing, so it is re-sent once after the main pass; the empty response is a
    # received INVALID and is never re-sent.
    assert [len(line['attempts']) for line in lines] == [2, 1, 1, 1]
    assert [line['status'] for line in lines] == ['ok', 'error', 'empty_response', 'ok']
    assert [line.get('resend', False) for line in lines] == [False, False, False, True]
    assert lines[3]['request_id'] == lines[1]['request_id']
    # Review round 2: nothing on a live line says which arm is ahead; the read-outs classify the raw text later.
    assert not any(key in line for line in lines for key in LIVE_LINE_FORBIDDEN)
    assert sleep.total == probe.BLIND_RETRY_WAIT_SECONDS + probe.BACKOFF_SECONDS[0]
    assert all(call == {'role': 'mechanic', 'max_output_tokens': 2000, 'timeout_seconds': 20} for call in provider.calls)
    manifest = json.loads((other / probe.MANIFEST_NAME).read_text())
    assert manifest['requests_done'] == 3 and manifest['resend_lines'] == 1 and manifest['attempts'] == 5
    assert {k: manifest['resend_pass'][k] for k in ('eligible', 'sent', 'received', 'ended')} == {
        'eligible': 1, 'sent': 1, 'received': 1, 'ended': 'completed'}


def test_the_resend_pass_skips_anything_delivered_and_local_refusals(tmp_path):
    plan, prompts = _small_plan(6)
    usage = SimpleNamespace(input_tokens=5, output_tokens=5)
    outcomes = [RuntimeProviderError('x', code='INVALID_RESPONSE_SHAPE', generation=usage),
                RuntimeProviderError('x', code='INPUT_LIMIT'),
                RuntimeProviderError('x', code='REQUEST_TIMEOUT'), RuntimeProviderError('x', code='REQUEST_TIMEOUT'),
                # A code that is re-sendable, but this one carried a generation: delivered, so never re-sent.
                RuntimeProviderError('x', code='PROVIDER_ERROR', generation=usage),
                NO_STEP, NO_STEP, STEP]
    provider = FakeProvider(outcomes)
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    assert _run(plan['requests'], prompts, provider, probe.SpendGuard(15.0), recorder) == 'completed'
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    # The shape and provider errors carried a generation: delivered, counted, never re-sent. The input
    # refusal is local. Only the request whose two attempts both timed out is re-sent.
    assert manifest['generations_delivered'] == 2 + 2 + 1   # two delivered errors, 2 answers, 1 re-send
    assert manifest['resend_pass']['request_ids'] == ['r0003']
    lines = _lines(tmp_path)
    assert [line['request_id'] for line in lines if line.get('resend')] == ['r0003']
    readouts = probe.compute_readouts(plan['requests'], lines)
    assert readouts['arms']['H']['received_on_resend'] == 1 and readouts['arms']['H']['timeouts'] == 2


def test_the_resend_pass_stops_at_the_fifth_errored_request_in_a_row(tmp_path):
    """Review round 2: the consecutive-error stop holds in the re-send pass too."""
    plan, prompts = _small_plan(12)
    error = lambda: RuntimeProviderError('x', code='HTTP_ERROR')  # noqa: E731
    # The main pass alternates an error with an answer (never 5 in a row), leaving 6 requests to re-send.
    outcomes = [outcome for _ in range(6) for outcome in (error(), NO_STEP)] + [error() for _ in range(6)]
    provider, sleep = FakeProvider(outcomes), FakeSleep()
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    assert _run(plan['requests'], prompts, provider, probe.SpendGuard(15.0), recorder, sleep=sleep) == 'completed'
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['resend_pass']['eligible'] == 6 and manifest['resend_pass']['ended'] == 'consecutive_errors'
    assert manifest['resend_pass']['sent'] == 5 and manifest['resend_pass']['received'] == 0
    assert len(provider.calls) == 12 + 5 and manifest['resend_lines'] == 5
    assert [w['consecutive_errors'] for w in manifest['backoff_waits'] if w['resend']] == [1, 2, 3, 4]


def test_persistent_errors_stop_after_the_ladder_and_an_operator_stop_sends_nothing(tmp_path):
    plan, prompts = _small_plan(6)
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    errors = [RuntimeProviderError('x', code='HTTP_ERROR') for _ in range(8)]
    sleep = FakeSleep()
    assert _run(plan['requests'], prompts, FakeProvider(errors), probe.SpendGuard(15.0), recorder,
                sleep=sleep) == 'consecutive_errors'
    assert sleep.total == sum(probe.BACKOFF_SECONDS)
    assert json.loads((tmp_path / probe.MANIFEST_NAME).read_text())['resend_pass'] is None
    other = tmp_path / 'second'
    other.mkdir()
    provider = FakeProvider([])
    assert _run(plan['requests'], prompts, provider, probe.SpendGuard(15.0), probe.Recorder(other, {'statuses': {}}),
                stop=lambda: True) == 'operator_stop'
    assert provider.calls == []


def test_a_stop_during_the_blind_retry_wait_sends_no_retry_and_cuts_the_wait(tmp_path):
    plan, prompts = _small_plan(3)
    stopped = []
    sleep = FakeSleep(on_call=lambda n: stopped.append(True))
    provider = FakeProvider([RuntimeProviderError('x', code='CONNECTION_ERROR')])
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    assert _run(plan['requests'], prompts, provider, probe.SpendGuard(15.0), recorder, sleep=sleep,
                stop=lambda: bool(stopped)) == 'operator_stop'
    assert len(provider.calls) == 1 and sleep.calls == [1.0]
    assert [len(line['attempts']) for line in _lines(tmp_path)] == [1]


def test_each_line_is_on_disk_before_the_manifest_that_counts_it(tmp_path, monkeypatch):
    plan, prompts = _small_plan(3)
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    on_disk = []
    save = recorder.save

    def checked_save():
        # A separate read of the file: only flushed bytes are visible.
        on_disk.append((len((tmp_path / 'responses.jsonl').read_text().splitlines()), recorder.manifest['requests_done']))
        save()
    monkeypatch.setattr(recorder, 'save', checked_save)
    assert _run(plan['requests'], prompts, FakeProvider([]), probe.SpendGuard(15.0), recorder) == 'completed'
    assert on_disk and all(lines == done for lines, done in on_disk) and on_disk[-1][0] == 3


def test_the_live_loop_never_classifies_so_a_classifier_fault_cannot_lose_a_paid_response(tmp_path, monkeypatch):
    plan, prompts = _small_plan(3)
    calls = []

    def broken(raw, reference):
        calls.append(raw)
        raise RuntimeError('classifier broke')
    monkeypatch.setattr(probe, 'classify_response', broken)
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    assert _run(plan['requests'], prompts, FakeProvider([STEP]), probe.SpendGuard(15.0), recorder) == 'completed'
    lines = _lines(tmp_path)
    assert len(lines) == 3 and lines[0]['raw'] == STEP and calls == []
    assert not any(key in line for line in lines for key in LIVE_LINE_FORBIDDEN + ('describe_error',))


class FakeOpenAI:
    """Modelled on the openai client the real RuntimeProvider builds."""

    script, calls = [], []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        FakeOpenAI.calls.append(kwargs)
        outcome = FakeOpenAI.script.pop(0) if FakeOpenAI.script else STEP
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(model='served-by/another-model', system_fingerprint='fp_test',
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                               choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=outcome))])

    async def close(self):
        pass


def _fake_settings(dry_settings, **changes):
    return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key', **changes)


def test_the_sender_changes_only_the_temperature_and_never_sends_an_unplanned_request(tmp_path, dry_settings):
    plan, prompts = _small_plan(3)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    sender = probe.RequestSender(base=FakeOpenAI)
    recorder = probe.Recorder(tmp_path, {'statuses': {}})

    async def go(requests, recorder):
        async with RuntimeProvider(_fake_settings(dry_settings), live_authorized=True, client_factory=sender) as provider:
            return await probe.run_requests(requests, prompts, provider, probe.SpendGuard(15.0), recorder,
                                            sender=sender, sleep=FakeSleep())
    try:
        assert asyncio.run(go(plan['requests'], recorder)) == 'completed'
    finally:
        recorder.close()
    assert [call['temperature'] for call in FakeOpenAI.calls] == [0, 0.7, 0]
    assert [probe.request_digest(call) for call in FakeOpenAI.calls] == [r['request_hash'] for r in plan['requests']]
    assert FakeOpenAI.calls[0]['extra_body'] == {'chat_template_kwargs': {'enable_thinking': False}}
    lines = _lines(tmp_path)
    assert {line['served_model'] for line in lines} == {'served-by/another-model'}
    wrong = [{**plan['requests'][0], 'request_hash': '0' * 64}]
    FakeOpenAI.calls = []
    other = tmp_path / 'second'
    other.mkdir()
    recorder = probe.Recorder(other, {'statuses': {}})
    try:
        with pytest.raises(probe.PlanningError, match='Request mismatch'):
            asyncio.run(go(wrong, recorder))
    finally:
        recorder.close()
    assert FakeOpenAI.calls == [] and _lines(other)[0]['request_mismatch']


def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    (tmp_path / 'artifacts').mkdir(exist_ok=True)
    return tmp_path / 'artifacts'


def _manifest(artifacts, relative, name=probe.MANIFEST_NAME, **fields):
    path = artifacts / relative / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {'status': 'STOPPED', 'ended_at': '2026-09-24T00:00:00Z', 'statuses': {'error': 5},
            'generations_delivered': 0, 'charged_upper_bound': 0.4984, **fields}
    path.write_text(json.dumps(body))
    return path


def _claim(artifacts, number, out, pid=999999, directory=probe.CLAIM_DIR):
    path = artifacts / directory / f'claim-{number:02d}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'claim': path.name, 'pid': pid, 'out': out, 'plan_hash': 'plan',
                                'harness_sha256': 'harness', 'spend_cap': 15.0}))
    return path


IDLE = lambda: ('down', None)  # noqa: E731


def test_other_paid_runs_block_a_launch(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    assert probe.other_paid_runs(status=IDLE) == ([], 'down')
    running = _manifest(artifacts, 'phase20-2026-09-24/run', name='dev-probe-manifest.json', stop_reason='running')
    blockers, _ = probe.other_paid_runs(status=IDLE)
    assert blockers and 'phase20' in blockers[0]
    assert probe.other_paid_runs(status=IDLE, ignore=[str(running)])[0] == []
    running.write_text(json.dumps({'stop_reason': 'completed', 'ended_at': 'x'}))
    for phase, name in (('phase26-2026-09-24/live', 'gap-probe-manifest.json'),
                        ('phase27-2026-09-24/live', 'word-probe-manifest.json')):
        path = _manifest(artifacts, phase, name=name, status='RUNNING', ended_at=None)
        assert 'phase26-29' in probe.other_paid_runs(status=IDLE)[0][0]
        path.write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x'}))
    assert probe.other_paid_runs(status=IDLE)[0] == []
    claim = _claim(artifacts, 1, 'artifacts/phase26-2026-09-24/next', directory='phase26-live-claims')
    assert 'no final manifest' in probe.other_paid_runs(status=IDLE)[0][0]
    _manifest(artifacts, 'phase26-2026-09-24/next', name='gap-probe-manifest.json', status='COMPLETED')
    assert probe.other_paid_runs(status=IDLE)[0] == [] and claim.exists()
    assert 'active campaign' in probe.other_paid_runs(status=lambda: ('active', 'campaign-x'))[0][0]
    assert 'could not be read' in probe.other_paid_runs(status=lambda: ('unknown', 'TimeoutError'))[0][0]
    assert probe.other_paid_runs(status=lambda: ('idle', None))[0] == []
    heldout = _manifest(artifacts, 'phase26-2026-09-24', name='heldout-manifest.json', status='RUNNING', ended_at=None)
    assert probe.other_paid_runs(status=IDLE)[0] == [] and heldout.exists()
    assert probe.other_paid_runs(status=IDLE, processes=['pid 7: python scripts/experiments/x.py --execute-live'])[0] == [
        'pid 7: python scripts/experiments/x.py --execute-live']


@pytest.mark.parametrize('relative,name', [
    ('phase20-2026-09-23/run', 'dev-probe-manifest.json'),
    ('phase21-2026-09-23/live', 'lapse-probe-manifest.json'),
    ('phase23-2026-09-24', 'full-loop-manifest.json'),
    ('phase26-2026-09-24', 'gap-probe-manifest.json'),
    ('phase29-2026-09-24/run', 'any-manifest.json'),
])
def test_every_sibling_manifest_glob_blocks_while_its_run_is_not_final(tmp_path, monkeypatch, relative, name):
    """Review round 2: each glob in OTHER_RUN_MANIFESTS, not only the shared loop, is tested."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    path = _manifest(artifacts, relative, name=name, status='RUNNING', ended_at=None)
    assert probe.other_paid_runs(status=IDLE)[0], relative
    path.write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x'}))
    assert probe.other_paid_runs(status=IDLE)[0] == []


# Written out, not read from the harness: a list taken from the module under test would shrink with it.
@pytest.mark.parametrize('directory', ['phase21-live-claims', 'phase26-live-claims', 'phase27-live-claims',
                                       'phase28-live-claims', 'phase29-live-claims'])
def test_every_sibling_claim_directory_blocks_until_its_run_is_final(tmp_path, monkeypatch, directory):
    artifacts = _artifacts(tmp_path, monkeypatch)
    phase = directory.split('-')[0]
    _claim(artifacts, 1, f'artifacts/{phase}-2026-09-24/live', directory=directory)
    assert 'no final manifest' in probe.other_paid_runs(status=IDLE)[0][0]
    _manifest(artifacts, f'{phase}-2026-09-24/live', name='run-manifest.json', status='COMPLETED')
    assert probe.other_paid_runs(status=IDLE)[0] == []


FOREIGN_RUN = (4242, 1, 'python scripts/experiments/run_gap_probe.py --execute-live --out y')


def test_the_real_process_list_feeds_every_paid_run_check_and_the_refusal_says_what_clears_it(tmp_path, monkeypatch):
    """Review round 2: other_paid_runs reads the process list itself when no rows are injected, so run_live and
    main refuse beside another paid run's process; --ignore-manifest is offered only for a manifest or claim."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'process_list', lambda: [FOREIGN_RUN])
    blockers, _ = probe.other_paid_runs(status=IDLE)
    assert blockers == [f'pid 4242: {FOREIGN_RUN[2]}']
    with pytest.raises(probe.PlanningError) as error:
        probe.check_other_paid_runs(SimpleNamespace(ignore_manifest=[]), status=IDLE)
    assert 'cannot clear a process' in str(error.value) and 'pass its exact path' not in str(error.value)
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    assert 'pid 4242' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    # Review round 3: a refusal counts every blocker and says what clears each kind.
    with pytest.raises(probe.PlanningError) as error:
        probe.check_other_paid_runs(SimpleNamespace(ignore_manifest=[]), status=lambda: ('unknown', 'TimeoutError'))
    assert '(and 1 more: the lab backend status could not be read' in str(error.value)
    assert 'Check the lab backend by hand' in str(error.value)
    monkeypatch.setattr(probe, 'process_list', lambda: [])
    _manifest(artifacts, 'phase20-2026-09-24/run', name='dev-probe-manifest.json', stop_reason='running')
    with pytest.raises(probe.PlanningError, match='pass its exact path to --ignore-manifest'):
        probe.check_other_paid_runs(SimpleNamespace(ignore_manifest=[]), status=IDLE)


@needs_store
def test_a_paid_run_process_seen_only_after_the_claim_ends_the_run_at_zero_cost(tmp_path, monkeypatch, dry_settings):
    """Review round 2: the re-check right after the claim reads the process list too."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    reads = []

    def rows():
        reads.append(1)
        return [] if len(reads) < 3 else [FOREIGN_RUN]
    monkeypatch.setattr(probe, 'process_list', rows)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    assert len(reads) == 3 and FakeOpenAI.calls == []
    directory = tmp_path / args.out
    manifest = json.loads((directory / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert manifest['attempts'] == 0 and manifest['charged_upper_bound'] == 0 and manifest['generations_delivered'] == 0
    assert manifest['blockers_after_claim'] == [f'pid 4242: {FOREIGN_RUN[2]}'] and not (directory / 'plan.json').exists()


def test_a_sibling_claim_is_followed_only_into_a_run_directory_and_never_into_the_seal(tmp_path, monkeypatch):
    """Review round 1: a claim naming phase22-* (the heldout-2 seal), heldout2 or any other shape is a blocker
    and nothing it names is read; heldout-manifest.json never counts."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    # A final manifest inside the seal: if it were read, the claim below would not block.
    _manifest(artifacts, 'phase22-2026-09-24/x', name='run-manifest.json', status='COMPLETED')
    opened = []
    real = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(str(self))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, 'read_text', spy)
    for number, out in enumerate(('artifacts/phase22-2026-09-24/x', 'artifacts/heldout2/x', 'artifacts/phase26-x/../phase22-2026-09-24/x',
                                  'artifacts/phase26-live-claims/x', '/etc/x', None), 1):
        claim = _claim(artifacts, number, out, directory='phase27-live-claims')
        blockers, _ = probe.other_paid_runs(status=IDLE)
        assert blockers == [f'phase27-live-claims/{claim.name} cannot be read or names no valid run directory; '
                            'nothing it names was read'], out
        claim.unlink()
    assert not any('phase22' in path or 'heldout2' in path for path in opened)
    _manifest(artifacts, 'phase27-2026-09-24/run', name=probe.HELDOUT_MANIFEST_NAME, status='COMPLETED')
    _claim(artifacts, 1, 'artifacts/phase27-2026-09-24/run', directory='phase27-live-claims')
    assert 'no final manifest' in probe.other_paid_runs(status=IDLE)[0][0]
    _manifest(artifacts, 'phase27-2026-09-24/run', name='report-word-probe-manifest.json', status='COMPLETED')
    assert probe.other_paid_runs(status=IDLE)[0] == []


LAUNCH = ('./.venv/bin/python scripts/experiments/slot2_probe.py --execute-live --confirm-entity shreetbohara-quinstreet '
          '--out artifacts/phase25-2026-09-24/live --expect-plan-hash X')


def test_the_process_guard_on_the_measured_caffeinate_tree_sees_no_run_but_this_one():
    """Review round 2 (the launch blocker): `caffeinate -is <python ...>` keeps the original pid for Python and
    forks the caffeinate helper as Python's CHILD, with the launch arguments on its command line (measured on
    this Mac). The runbook's own launch must see no other paid run."""
    own, shell = os.getpid(), os.getppid()
    rows = [(shell, 1, '/bin/zsh -c cd faultlab && nohup caffeinate -is ./.venv/bin/python ...'),
            (own, shell, LAUNCH), (own + 100000, own, f'caffeinate -is {LAUNCH}')]
    assert probe.live_experiment_processes(lambda: rows) == []
    # Another run launched the same way is still flagged, through its Python process.
    other = [(9000, 1, LAUNCH.replace('/live', '/live-x')), (9001, 9000, f'caffeinate -is {LAUNCH}')]
    assert [b.split(':')[0] for b in probe.live_experiment_processes(lambda: rows + other)] == ['pid 9000']
    # A Python ancestor carrying the launch arguments (a wrapper that re-executes this run) is this run, at any
    # depth (review round 3: a grandparent too).
    assert probe.live_experiment_processes(lambda: [(shell, 1, LAUNCH), (own, shell, LAUNCH)]) == []
    assert probe.live_experiment_processes(lambda: [(own + 200000, 1, LAUNCH), (shell, own + 200000, '/bin/zsh'),
                                                    (own, shell, LAUNCH)]) == []
    # A descendant's descendant is this run's too.
    assert probe.live_experiment_processes(lambda: rows + [(own + 100001, own + 100000, LAUNCH)]) == []


def test_the_process_guard_matches_tokens_not_substrings_and_fails_closed():
    """Review round 2: a shell, grep or heredoc that merely mentions the words is not a paid run. Review round 3:
    the rule is widened in the fail-closed direction (every shape below that round 1's substring rule caught)."""
    runs = ['python scripts/experiments/run_gap_probe.py --execute-live --out y',
            '/Users/x/.pyenv/versions/3.12.8/bin/python3.12 -B /abs/faultlab/scripts/experiments/lapse_probe.py --execute-live',
            'Python -X dev scripts/experiments/run_dev_probe.py --out z --execute-live',
            # argparse accepts an unambiguous abbreviation of --execute-live; older runners have no other --e* option
            'python scripts/experiments/slot2_probe.py --exec --out w',
            'python scripts/experiments/slot2_probe.py --exe',
            'python scripts/experiments/run_replication.py --ex',
            'python scripts/experiments/native_baseline.py --e',
            # a runner started from scripts/, and interpreter names that only start with "python"
            '../.venv/bin/python experiments/run_gap_probe.py --execute-live --out artifacts/phase26-x/live',
            'python3.13t scripts/experiments/run_gap_probe.py --execute-live',
            '/usr/local/bin/python3.12-intel64 scripts/experiments/run_gap_probe.py --execute-live',
            # Python options that take a separate value
            'python -W ignore scripts/experiments/run_gap_probe.py --execute-live',
            'python --check-hash-based-pycs always scripts/experiments/run_gap_probe.py --execute-live',
            # a real launch whose command line shlex cannot parse is split on whitespace
            "python scripts/experiments/run_gap_probe.py --execute-live --out artifacts/phase26-x/it's",
            # fail closed: any path ending in experiments/<name>.py (round 2 treated this one as not a run)
            'python tests/experiments/test_slot2_probe.py --execute-live']
    not_runs = ['/bin/sh -c sleep 20; echo grep -n -- --execute-live scripts/experiments/slot2_probe.py',
                'grep scripts/experiments/slot2_probe.py --execute-live',
                'rg python scripts/experiments/slot2_probe.py --execute-live',
                'zsh -c ./.venv/bin/python scripts/experiments/slot2_probe.py --execute-live',
                f'caffeinate -is {LAUNCH}',
                'python scripts/experiments/run_gap_probe.py',
                'python scripts/experiments/run_gap_probe.py --',
                'python scripts/experiments/run_gap_probe.py -e --expect-plan-hash x',
                'python -m pytest --execute-live',
                'python -m scripts/experiments/slot2_probe.py --execute-live',
                'python -c scripts/experiments/slot2_probe.py --execute-live',
                'python - scripts/experiments/slot2_probe.py --execute-live',
                'python scripts/experiments/slot2_probe.py --out artifacts/phase25-x/--execute-live-notes',
                'python "unbalanced scripts/experiments/slot2_probe.py --execute-live']
    assert [probe.paid_run_command(c) for c in runs] == [True] * len(runs)
    assert [probe.paid_run_command(c) for c in not_runs] == [False] * len(not_runs)
    rows = [(5000 + i, 1, c) for i, c in enumerate(runs + not_runs)]
    assert len(probe.live_experiment_processes(lambda: rows)) == len(runs)

    def broken():
        raise OSError('no ps')
    assert 'could not be read' in probe.live_experiment_processes(broken)[0]


def test_backend_status_reads_a_refused_connection_as_down(monkeypatch):
    import urllib.error

    def refused(*_, **__):
        raise urllib.error.URLError(ConnectionRefusedError(61, 'refused'))
    monkeypatch.setattr(probe.urllib.request, 'urlopen', refused)
    assert probe.backend_status() == ('down', None)

    def timeout(*_, **__):
        raise urllib.error.URLError(TimeoutError())
    monkeypatch.setattr(probe.urllib.request, 'urlopen', timeout)
    assert probe.backend_status() == ('unknown', 'TimeoutError')

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(self.body).encode()
    monkeypatch.setattr(probe.urllib.request, 'urlopen', lambda *_, **__: Response({'active_campaign_id': 'c-1'}))
    assert probe.backend_status() == ('active', 'c-1')
    monkeypatch.setattr(probe.urllib.request, 'urlopen', lambda *_, **__: Response({'active_campaign_id': None}))
    assert probe.backend_status() == ('idle', None)


def test_output_directories_claims_and_one_delivering_run(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    for bad in ('artifacts/phase21-2026-09-24/live', 'artifacts/phase25-2026-09-24', 'artifacts/phase25-x/a/b',
                f'artifacts/{probe.CLAIM_DIR}/x', '/tmp/elsewhere'):
        with pytest.raises(probe.PlanningError):
            probe.check_output(bad)
    assert probe.check_output('artifacts/phase25-2026-09-24/live')
    _manifest(artifacts, 'phase25-2026-09-24/live')
    with pytest.raises(probe.PlanningError, match='exists'):
        probe.check_output('artifacts/phase25-2026-09-24/live')
    assert probe.earlier_live_runs(artifacts) == [
        {'manifest': f'artifacts/phase25-2026-09-24/live/{probe.MANIFEST_NAME}', 'charged_upper_bound': 0.4984}]
    assert probe.effective_spend_cap(15.0, probe.earlier_live_runs(artifacts)) == pytest.approx(15 - 0.4984)
    with pytest.raises(probe.PlanningError, match='changed during the launch checks'):
        probe.take_claim((artifacts / 'phase25-2026-09-24/live-2').resolve(), 'plan', 'harness', expected_earlier=[])
    assert not (artifacts / probe.CLAIM_DIR).exists()
    path, _ = probe.take_claim((artifacts / 'phase25-2026-09-24/live-2').resolve(), 'plan', 'harness',
                               expected_earlier=probe.earlier_live_runs(artifacts))
    assert path.name == 'claim-01.json'
    with pytest.raises(probe.PlanningError, match='no manifest'):
        probe.check_output('artifacts/phase25-2026-09-24/live-3')
    _manifest(artifacts, 'phase25-2026-09-24/live-2', statuses={'ok': 1}, generations_delivered=1)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase25-2026-09-24/live-3')


def test_a_claim_name_already_taken_refuses_and_is_left_untouched(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _claim(artifacts, 1, 'artifacts/phase25-2026-09-24/live')
    before = (artifacts / probe.CLAIM_DIR / 'claim-01.json').read_text()
    # Two launches racing: both computed claim-01 from the same listing.
    monkeypatch.setattr(probe, 'live_run_records', lambda a: {'undelivered': [], 'claim_numbers': []})
    with pytest.raises(probe.PlanningError, match='already taken'):
        probe.take_claim((artifacts / 'phase25-2026-09-24/live-2').resolve(), 'plan', 'harness')
    assert (artifacts / probe.CLAIM_DIR / 'claim-01.json').read_text() == before
    assert sorted(p.name for p in (artifacts / probe.CLAIM_DIR).iterdir()) == ['claim-01.json']


def test_finalize_abandoned_closes_a_dead_claim(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase25-2026-09-24/live', pid=4242)
    with pytest.raises(probe.PlanningError, match='may still be running'):
        probe.finalize_abandoned(claim, alive=lambda pid: True)
    path, manifest = probe.finalize_abandoned(claim, alive=lambda pid: False)
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'abandoned'
    assert manifest['generations_delivered'] == 0 and manifest['charged_upper_bound'] == 0
    assert probe.check_output('artifacts/phase25-2026-09-24/live-2')
    with pytest.raises(probe.PlanningError, match='already final'):
        probe.finalize_abandoned(claim, alive=lambda pid: False)
    assert probe.claim_process_alive(None) is True and probe.claim_process_alive(-1) is True


def test_finalize_abandoned_charges_recorded_and_in_flight_attempts_and_counts_delivery(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase25-2026-09-24/live', pid=4242)
    _manifest(artifacts, 'phase25-2026-09-24/live', status='RUNNING', ended_at=None, attempts=3,
              statuses={'ok': 1}, generations_delivered=1, charged_upper_bound=0.14952)
    lines = [{'request_id': 'r0001', 'status': 'ok', 'raw': STEP, 'attempts': [{'attempt': 1}]},
             {'request_id': 'r0002', 'status': 'ok', 'raw': STEP, 'attempts': [{'attempt': 1}]},
             {'request_id': 'r0003', 'status': 'error', 'raw': None,
              'attempts': [{'attempt': 1, 'code': 'REQUEST_TIMEOUT'}, {'attempt': 2, 'code': 'REQUEST_TIMEOUT'}]}]
    (artifacts / 'phase25-2026-09-24/live/responses.jsonl').write_text(
        '\n'.join(json.dumps(line) for line in lines) + '\n{"request_id": "r00')
    _, manifest = probe.finalize_abandoned(claim, alive=lambda pid: False)
    # max(3 in the manifest, 4 recorded) + 2 in flight; 2 delivered in the lines, not the manifest's 1.
    assert manifest['attempts'] == 6 and manifest['charged_upper_bound'] == pytest.approx(6 * 0.04984)
    assert manifest['generations_delivered'] == 2 and manifest['requests_done'] == 3
    assert manifest['finalized_abandoned']['partial_lines_skipped'] == 1
    assert manifest['finalized_abandoned']['unrecorded_in_flight_attempts_charged'] == 2
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase25-2026-09-24/live-2')


def test_a_live_slot2_probe_process_counts_as_alive():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'slot2_probe'])
    try:
        assert probe.claim_process_alive(child.pid) is True
    finally:
        child.kill()
        child.wait()
    assert probe.claim_process_alive(child.pid) is False


def _gate(tmp_path, monkeypatch, plan, *, review=True, reviewed_line=True, marker=False, pins=True):
    _artifacts(tmp_path, monkeypatch)
    harness = probe.sha256_file(probe.__file__)
    plan_hash = probe.plan_hash(plan)
    lines = ['# test protocol']
    if marker:
        lines.append(f'Status: {probe.REVIEW_PENDING_MARKER}.')
    lines += ['', '## Pins'] + ([f'harness {harness}', f'plan {plan_hash}'] if pins else [])
    if reviewed_line:
        lines.append(probe.REVIEWED_LINE.format(harness=harness, plan=plan_hash))
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    protocol_sha = probe.sha256_file(protocol)
    if review:
        record = tmp_path / probe.REVIEW_RECORD
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'protocol_sha256': protocol_sha, 'harness_sha256': harness, 'plan_hash': plan_hash}))
    return SimpleNamespace(out='artifacts/phase25-test/live', expect_harness_sha256=harness,
                           expect_protocol_sha256=protocol_sha, expect_plan_hash=plan_hash, spend_cap=15.0,
                           confirm_entity='shreetbohara-quinstreet', ignore_manifest=[])


class CredentialRead(Exception):
    pass


def _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts, status=IDLE):
    def no_credentials(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', no_credentials)
    with pytest.raises(probe.PlanningError) as error:
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status)
    assert not (tmp_path / 'artifacts/phase25-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
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
    tampered = {k: dict(v) for k, v in prompts.items()}
    first = plan['requests'][0]['messages_hash']
    tampered[first]['messages'] = [{'role': 'system', 'content': 'other'}]
    assert 'no verified prompt' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, tampered)
    args = _gate(tmp_path, monkeypatch, plan, marker=True)
    assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, pins=False, reviewed_line=False)
    assert 'does not declare this harness' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, reviewed_line=False)
    assert 'Reviewed for launch' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    (tmp_path / probe.REVIEW_RECORD).unlink()
    args = _gate(tmp_path, monkeypatch, plan, review=False)
    assert 'No readable review record' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    record = tmp_path / probe.REVIEW_RECORD
    for key in ('protocol_sha256', 'harness_sha256', 'plan_hash'):
        good = record.read_text()
        record.write_text(json.dumps({**json.loads(good), key: '0' * 64}))
        assert 'review record does not name' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
        record.write_text(good)
    assert 'active campaign' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts,
                                                             status=lambda: ('active', 'c'))
    monkeypatch.setattr(probe, 'PROTOCOL', tmp_path / 'missing.md')
    assert 'No protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)

    def credential_read(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', credential_read)
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts/phase25-test').exists()


def test_the_run_cap_is_what_the_phase_cap_leaves_after_earlier_undelivered_runs(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    plan['counts']['total_requests'] = 260
    args = _gate(tmp_path, monkeypatch, plan)
    _manifest(tmp_path / 'artifacts', 'phase25-2026-09-24/live-0', charged_upper_bound=2.1)
    assert '260 planned requests exceed the $12.90 cap' in _refused_before_credentials(
        tmp_path, monkeypatch, args, plan, prompts)


@needs_store
def test_the_spend_guard_of_a_live_run_is_built_on_the_phase_cap_remainder(tmp_path, monkeypatch, dry_settings):
    plan, prompts = _small_plan(3)
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', FakeOpenAI)
    # An earlier run that delivered nothing charged $14.85, so this run may spend $0.15: 3 attempts.
    _manifest(tmp_path / 'artifacts', 'phase25-2026-09-24/live-0', charged_upper_bound=14.85)
    FakeOpenAI.script, FakeOpenAI.calls = [TimeoutError(), NO_STEP], []
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['spend_cap'] == pytest.approx(0.15) and manifest['spend_cap_requested'] == 15.0
    assert manifest['stop_reason'] == 'spend_guard' and manifest['attempts'] == 3 and len(FakeOpenAI.calls) == 3


@pytest.mark.parametrize('change,message', [
    ({'confirm_entity': 'someone-else'}, '--confirm-entity'),
    ({'settings': {'wandb_project': 'Other'}}, 'project'),
    ({'settings': {'wandb_mechanic_model': 'deepseek-ai/DeepSeek-V3.1'}}, 'configuration_hash'),
])
def test_the_live_run_refuses_a_wrong_entity_project_or_model_after_the_credential_read(
        tmp_path, monkeypatch, dry_settings, change, message):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    if 'confirm_entity' in change:
        args.confirm_entity = change['confirm_entity']
    settings = _fake_settings(dry_settings, **change.get('settings', {}))

    def live_settings(path, *, env_path):
        assert env_path is None, 'the live path reads credentials through the runtime loader only'
        return settings
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    with pytest.raises(probe.PlanningError, match=message):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts/phase25-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


def test_the_mechanic_role_must_resolve_to_the_declared_model_even_if_the_pins_were_passed(
        tmp_path, monkeypatch, dry_settings):
    """Defence in depth: the configuration hash covers the role models, so this refusal is reached only if
    the pin check were bypassed; it is bypassed here to show the refusal itself."""
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    settings = _fake_settings(dry_settings, wandb_mechanic_model='deepseek-ai/DeepSeek-V3.1')
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: settings)
    monkeypatch.setattr(probe, 'check_pins', lambda pins: None)
    with pytest.raises(probe.PlanningError, match='does not resolve to the declared model'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


def _live(tmp_path, monkeypatch, dry_settings, factory=None):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', factory or FakeOpenAI)
    return plan, prompts, args


@needs_store
def test_a_live_run_end_to_end_on_the_real_provider_with_a_fake_client(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [NO_STEP, STEP, 'not json'], []
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 0
    directory = tmp_path / args.out
    manifest = json.loads((directory / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'COMPLETED' and manifest['generations_delivered'] == 6
    assert manifest['claim'] == f'artifacts/{probe.CLAIM_DIR}/claim-01.json' and manifest['traceback'] is None
    assert manifest['stop_signal'] is None and manifest['stop_signals_received'] == 0
    assert manifest['in_flight_request'] is None and manifest['last_request'] == {'request_id': 'r0006', 'resend': False}
    assert manifest['backend_state_at_launch'] == 'down' and 'fake-not-a-key' not in (directory / 'responses.jsonl').read_text()
    assert manifest['resend_pass']['ended'] == 'nothing_to_resend'
    readouts = json.loads((directory / 'readouts.json').read_text())
    assert readouts['arms']['C']['duplicate'] == 1 and readouts['arms']['T']['working'] == 2
    assert readouts['arms']['H']['invalid'] == 1 and readouts['provider']['served_model'] == {'served-by/another-model': 6}
    assert readouts['run_end']['round1_fallback_permitted'] is True and readouts['run_end']['stop_reason'] == 'completed'
    assert probe.recompute_readouts(directory) == readouts
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase25-test/live-2')
    plan_file = directory / 'plan.json'
    plan_file.write_text(json.dumps({**json.loads(plan_file.read_text()), 'counts': {'total_requests': 7}}))
    with pytest.raises(probe.PlanningError, match="NOT THE RUN'S HARNESS"):
        probe.recompute_readouts(directory)
    assert probe.recompute_readouts(directory, allow_other_harness=True)['plan_matches_run'] is False


@needs_store
def test_an_unexpected_exception_is_recorded_with_its_traceback(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []

    def broken(self, entry):
        raise RuntimeError('disk broke')
    monkeypatch.setattr(probe.Recorder, 'record', broken)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and 'disk broke' in manifest['traceback']
    assert manifest['generations_delivered'] == 1 and 'fake-not-a-key' not in manifest['traceback']


@needs_store
def test_another_paid_run_seen_after_the_claim_ends_the_run_at_zero_cost(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    calls = []

    def status():
        calls.append(1)
        return ('down', None) if len(calls) < 3 else ('active', 'sibling-campaign')
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status) == 1
    assert len(calls) == 3 and FakeOpenAI.calls == []
    directory = tmp_path / args.out
    manifest = json.loads((directory / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert manifest['attempts'] == 0 and manifest['charged_upper_bound'] == 0 and manifest['generations_delivered'] == 0
    assert 'sibling-campaign' in manifest['blockers_after_claim'][0] and not (directory / 'plan.json').exists()
    assert probe.check_output('artifacts/phase25-test/live-2')


@needs_store
def test_a_sigterm_during_a_request_stops_after_it(tmp_path, monkeypatch, dry_settings):
    class Killer(FakeOpenAI):
        async def create(self, **kwargs):
            if not FakeOpenAI.calls:
                os.kill(os.getpid(), signal.SIGTERM)
            return await super().create(**kwargs)
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings, factory=Killer)
    FakeOpenAI.script, FakeOpenAI.calls = [NO_STEP] * 6, []
    before = signal.getsignal(signal.SIGTERM)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'operator_stop' and manifest['ended_at']
    assert manifest['requests_done'] == 1 and len(FakeOpenAI.calls) == 1 and manifest['resend_pass'] is None
    assert signal.getsignal(signal.SIGTERM) == before
    # Review round 2: where the stop signal arrived is recorded, and an operator stop never earns the fallback.
    stop = manifest['stop_signal']
    assert stop['signal'] == 'SIGTERM' and stop['in_flight_request'] == {'request_id': 'r0001', 'resend': False}
    assert stop['requests_done_at_arrival'] == 0 and stop['status_at_arrival'] == 'RUNNING'
    assert manifest['stop_signals_received'] == 1
    readouts = json.loads((tmp_path / args.out / 'readouts.json').read_text())
    assert readouts['run_end']['round1_fallback_permitted'] is False


@needs_store
def test_the_first_of_two_stop_signals_is_the_one_recorded(tmp_path, monkeypatch, dry_settings):
    """Review round 3: a later signal never overwrites the first record, and every signal is counted."""
    class TwoSignals(FakeOpenAI):
        async def create(self, **kwargs):
            if not FakeOpenAI.calls:
                os.kill(os.getpid(), signal.SIGINT)
                os.kill(os.getpid(), signal.SIGTERM)
            return await super().create(**kwargs)
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings, factory=TwoSignals)
    FakeOpenAI.script, FakeOpenAI.calls = [NO_STEP] * 6, []
    before = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    assert (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)) == before
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['stop_reason'] == 'operator_stop' and manifest['requests_done'] == 1
    assert manifest['stop_signal']['signal'] == 'SIGINT' and manifest['stop_signals_received'] == 2
    assert manifest['stop_signal']['in_flight_request'] == {'request_id': 'r0001', 'resend': False}


@needs_store
def test_a_sigterm_during_a_backoff_wait_cuts_it_short(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [RuntimeError('boom')] * 6, []
    sleep = FakeSleep(on_call=lambda n: os.kill(os.getpid(), signal.SIGTERM) if n == 1 else None)
    assert probe.run_live(args, plan, prompts, sleep=sleep, status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['stop_reason'] == 'operator_stop' and manifest['requests_done'] == 1
    assert sleep.calls == [1.0] and manifest['backoff_waits'][0]['seconds'] == probe.BACKOFF_SECONDS[0]
    stop = manifest['stop_signal']
    assert stop['in_flight_request'] is None and stop['last_request'] == {'request_id': 'r0001', 'resend': False}


@needs_store
def test_a_stop_that_arrives_as_the_handlers_are_installed_refuses_before_the_claim(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    real = signal.signal

    def install_and_fire(sig, handler):
        previous = real(sig, handler)
        if sig == signal.SIGTERM and callable(handler):
            handler(sig, None)
        return previous
    monkeypatch.setattr(probe.signal, 'signal', install_and_fire)
    with pytest.raises(probe.PlanningError, match='before the claim'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / args.out).exists()


def test_main_needs_every_live_flag_before_any_plan_is_built(capsys, monkeypatch):
    def no_plan(**_):
        raise AssertionError('no plan may be built')
    monkeypatch.setattr(probe, 'build_plan', no_plan)
    assert probe.main(['--execute-live', '--out', 'artifacts/phase25-x/live']) == 1
    assert '--execute-live needs' in capsys.readouterr().out


def test_main_checks_for_other_paid_runs_before_any_plan_is_built(tmp_path, capsys, monkeypatch):
    _artifacts(tmp_path, monkeypatch)

    def no_plan(**_):
        raise AssertionError('no plan may be built')
    monkeypatch.setattr(probe, 'build_plan', no_plan)
    monkeypatch.setattr(probe, 'other_paid_runs', lambda **_: (['phase26 run may be in progress (x)'], 'down'))
    assert probe.main(['--execute-live', '--out', 'artifacts/phase25-x/live', '--confirm-entity', 'e',
                       '--expect-plan-hash', 'p', '--expect-harness-sha256', 'h', '--expect-protocol-sha256', 'q']) == 1
    assert 'One paid run at a time' in capsys.readouterr().out
