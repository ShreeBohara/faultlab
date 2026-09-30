"""Offline checks of the pre-registered request-only diagnosis probe (scripts/experiments/diagnosis_probe.py).

$0: no provider, W&B, Weave or network call (conftest blocks the network). The live path is exercised only with a scripted
provider injected through main(provider_factory=...), so no settings are read and no RuntimeProvider is built. Output
folders are pytest temporary folders.
"""
import csv
import hashlib
import importlib.util
import json
import pathlib

import pytest

from app.contracts.models import canonical_json, content_hash
from app.contracts.tokens import input_token_bound
from app.lab import diagnosis_guide, diagnosis_protocol
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/experiments/diagnosis_probe.py'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'


def load():
    spec = importlib.util.spec_from_file_location('diagnosis_probe_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


probe = load()


@pytest.fixture(scope='module')
def built():
    return probe.build_plan()


@pytest.fixture
def anyio_backend(): return 'asyncio'


def test_the_dry_run_builds_140_requests_and_prints_the_maximum_charge_without_writing(built, tmp_path, capsys, monkeypatch):
    plan, messages = built
    assert plan['counts']['first_turn_calls'] == 100 and plan['counts']['repair_calls'] == 40 and plan['counts']['total_calls'] == 140
    assert set(plan['counts']['calls_per_request_key'].values()) == {10} and len(plan['counts']['calls_per_request_key']) == 14
    assert plan['charge']['per_call_dollar_upper_bound'] == 0.04984 and plan['charge']['max_charge_dollars'] == pytest.approx(6.9776)
    assert plan['charge']['max_charge_dollars'] <= probe.HARD_SPEND_CAP == 8.0
    assert plan['sampling']['request_settings'] == {'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}, 'max_input_tokens': 32000,
                                                    'max_output_tokens': 2000, 'response_format': {'type': 'json_object'}, 'retries': 0,
                                                    'temperature': 0, 'timeout_seconds': 20}
    assert plan['sampling']['campaign_id'] == 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530'
    assert plan['network_calls'] == 0 and plan['harness_sha256'] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert plan['plan_hash'] == content_hash({k: v for k, v in plan.items() if k != 'plan_hash'})
    monkeypatch.chdir(tmp_path)
    assert probe.main([]) == 0
    printed = capsys.readouterr().out
    assert 'maximum charge: 140 x $0.04984 = $6.9776' in printed and 'network calls: 0' in printed
    # Review finding MEDIUM-3 / F1 (fixer): the dry run states the frozen temperature and that repeats may be identical.
    assert 'sampling: temperature 0, frozen from the saved plan; the declaration cannot change it' in printed
    assert 'distinct answers per request key' in printed
    assert list(tmp_path.iterdir()) == []                                                    # a dry run writes nothing


def test_every_request_is_the_saved_bytes_or_exactly_one_declared_change(built):
    plan, messages = built
    for name in probe.FIRST_TURN_REQUESTS:
        saved = json.loads((ROOT / probe.INPUT_DIR / f'{name}-diagnosis-request.json').read_text())
        control, guide = messages[f'{name}/CONTROL'], messages[f'{name}/GUIDE']
        assert control == saved['turns'][0]['messages']
        assert guide[0] == control[0]
        full, guided = json.loads(control[1]['content']), json.loads(guide[1]['content'])
        assert set(guided) - set(full) == {'diagnosis_guide'} and all(canonical_json(guided[k]) == canonical_json(full[k]) for k in full)
        assert guided['diagnosis_guide'] == diagnosis_guide.block(saved_task_text := plan['inputs'][name]['task_text'])
        assert saved_task_text == 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
        # +608: the guide block with its two neutral checks_note sentences (PM decision on review finding F4; +569 without them)
        assert plan['requests'][f'{name}/GUIDE']['input_tokens'] - plan['requests'][f'{name}/CONTROL']['input_tokens'] == 608
        if name in probe.REPAIR_SETUPS:
            assert messages[f'{name}/REPAIR_TODAY'] == saved['turns'][1]['messages']
            rule1 = messages[f'{name}/REPAIR_RULE1']
            assert rule1[:3] == saved['turns'][1]['messages'][:3]
            assert json.loads(rule1[3]['content'])['validation_errors'][0]['your_characters'] == probe.REPAIR_SETUPS[name]
            assert plan['requests'][f'{name}/REPAIR_RULE1']['input_tokens'] - plan['requests'][f'{name}/REPAIR_TODAY']['input_tokens'] == 47
    for key, request in plan['requests'].items():
        assert request['messages_sha256'] == content_hash(messages[key]) and request['input_tokens'] == input_token_bound(messages[key], MODEL)


@pytest.mark.anyio
@pytest.mark.parametrize('name', ['v2f-dev5', 'v2g-dev5'])
async def test_the_rule_1_repair_request_is_exactly_what_the_real_mechanic_sends(built, tmp_path, name):
    from app.agents.mechanic import Mechanic
    from app.lab.storage import LabStore
    plan, messages = built
    saved = json.loads((ROOT / probe.INPUT_DIR / f'{name}-diagnosis-request.json').read_text())
    raw = saved['turns'][1]['messages'][2]['content']
    sent = []
    class Provider:
        def role_model(self, role): return MODEL
        async def complete(self, messages, **kwargs):
            sent.append(json.loads(json.dumps(messages))); return RuntimeGeneration(raw, MODEL)
    class Ledger:
        def consume_call(self, **kwargs): pass
        def reconcile(self, generation): pass
    mechanic = Mechanic(Provider(), LabStore(tmp_path / 'lab.db'), Ledger())
    mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
    context = {k: v for k, v in json.loads(saved['turns'][0]['messages'][1]['content']).items() if k != 'output_schema'}
    await mechanic.diagnose(context)
    assert sent[1] == messages[f'{name}/REPAIR_RULE1']
    assert probe.mechanic_errors(raw, context, rule1=False) == json.loads(saved['turns'][1]['messages'][3]['content'])['validation_errors']


def test_the_schedule_interleaves_the_arms(built):
    plan, _ = built
    calls = plan['schedule']
    assert [c['call_index'] for c in calls] == list(range(140))
    for round_index in range(10):
        block = [c for c in calls if c['round'] == round_index]
        assert [c['turn'] for c in block] == ['first'] * 10 + ['repair'] * 4
    firsts = [c['arm'] for c in calls if c['turn'] == 'first']
    # 50 CONTROL/GUIDE pairs; each arm goes first in exactly half of them.
    assert sum(firsts[i] == 'CONTROL' for i in range(0, 100, 2)) == 25 == sum(firsts[i] == 'GUIDE' for i in range(0, 100, 2))
    assert all({firsts[i], firsts[i + 1]} == {'CONTROL', 'GUIDE'} for i in range(0, 100, 2))


# --------------------------------------------------------------------------------------------- the live path (scripted)

class Scripted:
    """No network: answers every call from the request itself. A GUIDE answer never blames citations; a CONTROL answer on
    dev-5 does; a repair answer is valid and short."""
    def __init__(self, *, fail=False): self.calls = []; self.fail = fail; self.closed = False
    def role_model(self, role): return MODEL
    async def complete(self, messages, *, role, max_output_tokens, timeout_seconds):
        self.calls.append((role, max_output_tokens, timeout_seconds, len(messages)))
        if self.fail:
            raise RuntimeProviderError('W&B inference failed; no generation retry was made.', code='CONNECTION_ERROR', error_class='APIConnectionError')
        context = json.loads(messages[1]['content'])
        guide = 'diagnosis_guide' in context
        dev6 = context['target_invariant'] == 'C4'
        hypothesis = ('The agent sent a confirmation after the delivered FAILED receipt (C3), and its report is inconsistent with it (C5).'
                      if guide or len(messages) == 4 else
                      'The report cites evidence labels that were never shown to the agent.')
        if dev6: hypothesis = 'A second confirmation effect was committed (C4).'
        answer = {'proposed_kind': 'POLICY_GAP' if guide else 'CONTRACT_EVIDENCE_GAP', 'hypothesis': hypothesis,
                  'evidence_ids': context['evidence_ids'][:1], 'requested_intervention_id': context['intervention_ids'][0]}
        return RuntimeGeneration(canonical_json(answer), MODEL, input_tokens=9000, output_tokens=120)
    async def close(self): self.closed = True


PRECONDITIONS = {'ledger_checked': True, 'dashboard_closed': True, 'no_other_paid_run': True, 'clock_drift_checked': True}


def declaration_file(tmp_path, plan, out, **changes):
    value = probe.declaration_template(plan, str(pathlib.Path(out).resolve()))
    value.update(approved_by='Offline test (not an approval)', preconditions=dict(PRECONDITIONS))
    value['sampling']['repeats_reading'] = 'Offline test: a request-and-arm cell whose repeats are identical counts as one sample.'
    value.update(changes)
    path = tmp_path / 'DECLARATION.json'
    path.write_text(json.dumps(value, indent=1))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_execute_live_refuses_without_a_declaration_and_builds_no_provider(tmp_path, capsys):
    built_providers = []
    factory = lambda: built_providers.append(1) or Scripted()      # noqa: E731
    out = tmp_path / 'live'
    assert probe.main(['--execute-live', '--out', str(out)], provider_factory=factory) == 2
    assert 'needs --declaration FILE and --declaration-sha256 HEX' in capsys.readouterr().err
    assert probe.main(['--execute-live'], provider_factory=factory) == 2
    assert built_providers == [] and not out.exists()


@pytest.mark.parametrize('change,message', [
    ({'harness_sha256': '0' * 64}, 'another harness, plan or model'),
    ({'plan_hash': '0' * 64}, 'another harness, plan or model'),
    ({'spend_cap_dollars': 9.0}, 'at most $8.00'),
    ({'spend_cap_dollars': 5.0}, 'exceed the $5.00 cap'),
    ({'approved_by': ' '}, 'names no approver'),
    ({'preconditions': {'ledger_checked': True, 'dashboard_closed': False, 'no_other_paid_run': True}}, 'preconditions'),
    ({'pre_registered_outcomes': {'P1': 'x'}}, 'pre-registered outcomes'),
    ({'output_folder': '/somewhere/else'}, 'another output folder'),
    # Fixer (review findings LOW-3, MEDIUM-3 / F1, F5): the clock-drift check, the sampling read-out and the exact scoring text.
    ({'preconditions': {'ledger_checked': True, 'dashboard_closed': True, 'no_other_paid_run': True}}, 'clock drift checked'),
    ({'sampling': {'temperature': 0, 'repeats_reading': ''}}, 'how repeated answers will be read'),
    ({'sampling': {'temperature': 0.7, 'repeats_reading': 'x'}}, 'temperature the harness sends'),
    ({'pre_registered_outcomes': {'P1': 'x', 'P2': 'x', 'P3': 'x', 'P4': 'x', 'decision_rule': 'x'}}, 'pre-registered outcomes'),
])
def test_execute_live_refuses_a_declaration_that_does_not_bind_this_plan(built, tmp_path, capsys, change, message):
    plan, _ = built
    out = tmp_path / 'live'
    path, digest = declaration_file(tmp_path, plan, out, **change)
    built_providers = []
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=lambda: built_providers.append(1) or Scripted()) == 2
    assert message in capsys.readouterr().err and built_providers == [] and not out.exists()


def test_execute_live_refuses_a_wrong_declaration_sha256_or_a_used_output_folder(built, tmp_path, capsys):
    plan, _ = built
    out = tmp_path / 'live'
    path, digest = declaration_file(tmp_path, plan, out)
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', '0' * 64],
                      provider_factory=Scripted) == 2
    assert 'sha256 differs' in capsys.readouterr().err
    out.mkdir(); (out / 'answers.jsonl').write_text('')
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=Scripted) == 2
    assert 'not empty' in capsys.readouterr().err


def test_a_scripted_live_run_charges_every_call_through_the_ledger_writes_only_under_out_and_scores(built, tmp_path):
    plan, messages = built
    out = tmp_path / 'live'
    path, digest = declaration_file(tmp_path, plan, out)
    provider = Scripted()
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=lambda: provider) == 0
    assert provider.closed and len(provider.calls) == 140
    assert {call[:3] for call in provider.calls} == {('mechanic', 2000, 20)}
    written = sorted(p.name for p in out.iterdir() if not p.name.startswith('probe-ledger.sqlite3-'))   # sqlite may keep -wal/-shm
    assert written == ['answers.jsonl', 'manifest.json', 'plan.json', 'probe-ledger.sqlite3', 'requests.json', 'review-blinded.csv',
                       'review-key.json', 'scoring.json']
    assert sorted(p.name for p in tmp_path.iterdir()) == ['DECLARATION.json', 'live']      # nothing outside out
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['status'] == 'COMPLETED' and manifest['delivered_answers'] == 140 and manifest['failed_calls'] == 0
    assert manifest['ledger']['charged_calls'] == 140 and manifest['ledger']['charged_dollar_upper_bound'] == pytest.approx(6.9776)
    assert manifest['declaration_sha256'] == digest and manifest['plan_hash'] == plan['plan_hash']
    answers = [json.loads(line) for line in (out / 'answers.jsonl').read_text().splitlines()]
    assert [a['call_index'] for a in answers] == list(range(140)) and all(a['delivered'] and a['raw'] for a in answers)
    from app.lab.storage import ReadOnlyLabStore
    ledger = ReadOnlyLabStore(out / 'probe-ledger.sqlite3')
    try:
        budget = ledger.get_record('budgets', probe.LEDGER_ID)
    finally:
        ledger.close()
    assert budget['used_calls'] == 140 and budget['charged_dollar_upper_bound'] == pytest.approx(6.9776)
    assert budget['caps']['dollars'] == 8.0 and budget['dollar_bounds']['mechanic'] == 0.04984
    scoring = json.loads((out / 'scoring.json').read_text())
    assert scoring['P1']['status'] == 'PENDING_HUMAN_CONFIRMATION'
    assert scoring['P1']['arms']['CONTROL']['auto_matched'] == 40 and scoring['P1']['arms']['GUIDE']['auto_matched'] == 0
    assert scoring['P2']['status'] == 'PASS' and scoring['P4']['status'] == 'PASS'
    assert scoring['P3']['arms']['GUIDE']['dev5_hint_c3'] == 40 and scoring['P3']['arms']['CONTROL']['dev5_hint_c3'] == 0
    # The person's review file is blind to arm and shows no checker output or hint (review finding MEDIUM-2, fixer): the person
    # judges each hypothesis on its own. With the person marking exactly the label-blaming hypotheses, P1 passes.
    with open(out / 'review-blinded.csv', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100 and all(r['blinded_id'].startswith('h') for r in rows)
    assert list(rows[0]) == list(probe.REVIEW_COLUMNS) and not any(c.startswith(('auto', 'hint')) or c == 'arm' for c in rows[0])
    for row in rows:
        row['human_blames_citations_labels_or_evidence_ids'] = 'Y' if 'never shown' in row['hypothesis'] else 'N'
    review = tmp_path / 'review-filled.csv'
    with open(review, 'w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    rescored = probe.score(out, review=review)          # from the folder alone: its plan.json and requests.json
    assert rescored['plan_hash'] == plan['plan_hash']
    assert rescored['P1']['status'] == 'PASS' and rescored['P1']['arms']['CONTROL']['confirmed'] == 40
    assert rescored['P1']['arms']['GUIDE']['counted_against_bar'] == 0
    # Every answer's model id is the one the product's provider path returns (RuntimeProvider echoes the requested model).
    assert all(a['model_id'] == MODEL and 'served_model' not in a for a in answers)
    assert manifest['project_ledger_note'].startswith('Add ledger.charged_dollar_upper_bound')


@pytest.mark.anyio
async def test_the_cap_holds_when_every_call_fails_and_retries_come_only_from_the_rest_of_the_cap(built, tmp_path):
    plan, messages = built
    out = tmp_path / 'live'
    manifest = await probe.execute(plan, messages, out, Scripted(fail=True))
    # 140 first attempts were reserved (6.9776 $); only 20 retries fit in the remaining 1.0224 $ of the 8 $ cap.
    assert manifest['status'] == 'COMPLETED' and manifest['failed_calls'] == 140 and manifest['delivered_answers'] == 0
    assert manifest['ledger']['charged_calls'] == 160 and manifest['retry_calls_allowed_by_cap'] == 20
    assert manifest['ledger']['charged_dollar_upper_bound'] == pytest.approx(160 * 0.04984) and manifest['ledger']['charged_dollar_upper_bound'] <= 8.0
    answers = [json.loads(line) for line in (out / 'answers.jsonl').read_text().splitlines()]
    assert sum(len(a['failures']) for a in answers) == 160 and all(not a['delivered'] for a in answers)


def test_the_budget_check_refuses_caps_above_8_dollars_or_below_the_planned_calls(built):
    plan, _ = built
    for cap in (8.01, 9, 0, -1, float('nan'), 6.97):
        with pytest.raises(probe.ProbeRefused):
            probe.check_budget(plan, cap)
    probe.check_budget(plan, 8.0); probe.check_budget(plan, 6.98)


def test_the_one_sided_fisher_test():
    assert probe.fisher_one_sided_greater(10, 10, 0, 10) == pytest.approx(1 / 184756)
    assert probe.fisher_one_sided_greater(0, 10, 10, 10) == pytest.approx(1.0)
    assert probe.fisher_one_sided_greater(5, 10, 5, 10) == pytest.approx(0.6718, abs=1e-4)


def test_a_changed_input_or_checker_is_refused(tmp_path):
    import shutil
    root = tmp_path / 'root'
    for relative in [f'{probe.INPUT_DIR}/{n}-diagnosis-request.json' for n in probe.INPUTS] + [p for p, _ in probe.EXPORTS.values()] + [probe.CHECKER[0]]:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    probe.load_inputs(root); probe.load_checker(root)
    path = root / f'{probe.INPUT_DIR}/v2e-dev5-diagnosis-request.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(probe.ProbeRefused, match='not the pinned file'):
        probe.load_inputs(root)


# --------------------------------------------------------------------------------------------- fixer: review findings

class Rewording(Scripted):
    """Like Scripted, but every GUIDE answer blames the evidence labels in words checker v2 does not match, and every call of a
    request key returns the same bytes (as temperature 0 may do)."""
    async def complete(self, messages, *, role, max_output_tokens, timeout_seconds):
        generation = await super().complete(messages, role=role, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
        context = json.loads(messages[1]['content'])
        if 'diagnosis_guide' in context and context['target_invariant'] != 'C4':
            answer = json.loads(generation.content)
            answer['hypothesis'] = 'The report followed the shown-order label contract and cited the label of the first write attempt.'
            return RuntimeGeneration(canonical_json(answer), MODEL, input_tokens=9000, output_tokens=120)
        return generation


def test_fix_p1_counts_person_flagged_guide_hypotheses_the_checker_misses_against_the_guide_bar(built, tmp_path):
    """Review finding MEDIUM-2 / F5(c): a GUIDE hypothesis that blames labels in words checker v2 misses must count against
    the GUIDE bar once a person flags it; before this fix it was only 'descriptive' and P1 passed."""
    plan, messages = built
    out = tmp_path / 'live'
    path, digest = declaration_file(tmp_path, plan, out)
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=Rewording) == 0
    checker = probe.load_checker()
    assert checker.claim_matches('The report followed the shown-order label contract and cited the label of the first write attempt.')[0] == []
    with open(out / 'review-blinded.csv', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:                                   # the person flags every hypothesis that blames labels or citations
        row['human_blames_citations_labels_or_evidence_ids'] = 'Y' if ('never shown' in row['hypothesis'] or 'label' in row['hypothesis']) else 'N'
    review = tmp_path / 'review-filled.csv'
    with open(review, 'w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    scoring = probe.score(out, review=review)
    guide, control = scoring['P1']['arms']['GUIDE'], scoring['P1']['arms']['CONTROL']
    assert control['confirmed'] == 40 and guide['confirmed'] == 0 and guide['person_flagged_without_auto_match'] == 40
    assert guide['counted_against_bar'] == 40 and scoring['P1']['status'] == 'FAIL'


def test_fix_scoring_reports_distinct_answers_per_request_key(built, tmp_path, capsys):
    """Review finding MEDIUM-3 / F1: at temperature 0 the ten repeats of a request may be identical; scoring must say how many
    distinct answers each request key got, so a pass cannot look stronger than its samples."""
    plan, messages = built
    out = tmp_path / 'live'
    path, digest = declaration_file(tmp_path, plan, out)
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=Scripted) == 0
    printed = capsys.readouterr().out
    scoring = json.loads((out / 'scoring.json').read_text())
    repeats = scoring['repeats']
    assert set(repeats['by_request_key']) == set(plan['requests'])
    assert all(row == {'delivered': 10, 'distinct_raw_answers': 1, 'distinct_hypotheses': 1} for row in repeats['by_request_key'].values())
    assert repeats['keys_with_one_distinct_answer'] == 14 and 'one sample' in repeats['note']
    assert scoring['P1']['arms']['CONTROL']['distinct_hypotheses'] == 1 and scoring['P4']['setups']['v2g-dev5/REPAIR_RULE1']['distinct_raw_answers'] == 1
    assert '14 of 14 request keys got one distinct answer' in printed


def test_fix_the_declaration_carries_the_full_pre_registration_and_the_sampling_facts(built):
    """Review findings F5(a, b) and MEDIUM-3: the hashed declaration states P4's 'worse', P1's treatment of person-only flags,
    the full decision rule, the frozen temperature and the clock-drift precondition; the harness accepts only that text."""
    plan, _ = built
    template = probe.declaration_template(plan)
    outcomes = template['pre_registered_outcomes']
    assert 'counted against the GUIDE bar' in outcomes['P1'] and 'without seeing the checker' in outcomes['P1']
    assert "'worse' means" in outcomes['P4'] and 'total' in outcomes['P4']
    for clause in ('Rule 1 ships', 'Rule 2 ships only if P1 and P2 pass', 'If P1 fails, the next design trims the label text',
                   "the Mechanic's veto persists"):
        assert clause in outcomes['decision_rule']
    assert 'distinct' in outcomes['repeats']
    assert template['sampling'] == {'temperature': 0, 'repeats_reading': ''}
    assert template['preconditions'] == {'ledger_checked': False, 'dashboard_closed': False, 'no_other_paid_run': False, 'clock_drift_checked': False}
    assert 'project ledger' in template['after_run']
