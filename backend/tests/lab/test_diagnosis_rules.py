"""The two diagnosis rules built on September 30, 2026 (artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md,
sections 2 and 5, and the PM decision at its end). $0 and offline: no provider, W&B or Weave call (conftest blocks the
network); saved public development requests and answers are read from the source-controlled
tests/fixtures/diagnosis-rules pack. Its README records the original artifact paths and exact-byte provenance.

Rule 1, faultlab-mechanic-diagnosis/v1-repair-and-record (``mechanic_diagnosis``), frozen into every new Learn plan:
  1a. a diagnosis request's format-repair turn states max_characters and your_characters for string_too_long;
  1b. an immutable diagnosis_requests/<diagnostic_id> record before the POLICY_GAP gate.
Rule 2, faultlab-diagnosis-guide/v1-kinds-and-checks (``diagnosis_guide``): built and tested, NOT offered
(DIAGNOSIS_GUIDE_OFFERED is False); the draft's interpretive C6 sentence is dropped and its two neutral checks_note
sentences are kept exactly as drafted (PM decisions, the second on review finding F4).

The memo's tests: T1 plans, T2 flag-off golden bytes, T3 the guide is additive, T4 the repair turn, T5 the record,
T6 gate invariance, T7 export, T9 the prototypes replay. T8 (the offline end-to-end campaign) and the loop's wrapper order
are in test_diagnosis_rules_loop.py.
"""
import functools
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.agents.explorer import PUBLIC_INVARIANTS
from app.agents.mechanic import FORMAT_REPAIR_INSTRUCTION, Mechanic
from app.contracts.models import (CheckResult, DiagnosticProposal, FaultSpec, PublicObservation, TaskReport, ToolResult,
                                  TrialResult, Usage, canonical_json, content_hash)
from app.contracts.tokens import input_token_bound
from app.lab import diagnosis_guide, diagnosis_protocol, loop_limits
from app.lab.citation_status import V2_MEMORY_WITH_CITATION_STATUS
from app.lab.diagnosis import Diagnostician, summarize_evidence
from app.lab.storage import LabStore, StoreConflict
from app.providers.runtime import RuntimeGeneration
from test_loop_limits_mechanic_context import bundle

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS = ROOT / 'backend/tests/fixtures/diagnosis-rules'
INPUTS = ANALYSIS / 'probe-inputs'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
NAMES = ('v2d-dev5', 'v2e-dev5', 'v2f-dev5', 'v2g-dev5', 'v2g-dev6')
FIRST_TOKENS = {'v2d-dev5': 8990, 'v2e-dev5': 9088, 'v2f-dev5': 9639, 'v2g-dev5': 9794, 'v2g-dev6': 9352}
REPAIR_TOKENS = {'v2f-dev5': 10030, 'v2g-dev5': 10153}
REPLAYED_LENGTH = {'v2f-dev5': 743, 'v2g-dev5': 614}
# The prototype's block added 631 tokens. The PM dropped only the interpretive C6 sentence of its checks_note (23 tokens)
# and kept the two neutral sentences (review finding F4; the builder had dropped all three, 62 tokens, for +569).
GUIDE_TOKENS = 608
C6_SENTENCE = "C6 is the check of the report's citations: where C6 passed, that report's citations met it."
CHECKS_NOTE = ("Each episode's checks row gives the fixed checks by check_id and category; the checks field gives each check's "
               "public meaning. Explain each failed check from its own meaning.")
TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
PINNED_INPUTS = {  # sha256 of the files this test reads (the probe inputs are byte copies of inv-a's rebuilt requests)
    'v2d-dev5': '7cb9ac8c3338d49b59cde38b8cc58747e18a3073a56426b78b8a48228296d03d',
    'v2e-dev5': '905228fbdda067b467a8e1b0e9bf2807854c44720b4e4d1362eb718c53e6f655',
    'v2f-dev5': '4ab16a7e3665209fd015255c47a955e17a708e62c6fc3791f7f259fb72011672',
    'v2g-dev5': '098c2cda59979cd60e7f86b4dc41cc4382b787886e9e817447756167ac97e13b',
    'v2g-dev6': 'd76f2e4ad3f7ce7918b5a9b05cebfb62849281902a60962ca6fd530514fe287e',
}
OUTPUTS_FILE = (ANALYSIS / 'inv-a/mechanic-outputs.json', 'fd48d11197d164509fa2345a500429c1df3f4a689db2984c426a552335e3e166')


def sha256_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def anyio_backend(): return 'asyncio'


def saved(name):
    path = INPUTS / f'{name}-diagnosis-request.json'
    assert sha256_file(path) == PINNED_INPUTS[name]
    return json.loads(path.read_text())


def saved_outputs():
    assert sha256_file(OUTPUTS_FILE[0]) == OUTPUTS_FILE[1]
    return json.loads(OUTPUTS_FILE[0].read_text())


def context_of(name):
    full = json.loads(saved(name)['turns'][0]['messages'][1]['content'])
    return {key: value for key, value in full.items() if key != 'output_schema'}


def saved_raws(name):
    """The provider's answers of this diagnosis, in attempt order. Attempt 0 of v2f and v2g is the exact saved bytes (the
    saved repair turn carries them); v2g's attempt 1 had the same fields; other answers are canonical JSON of their fields."""
    request, answers = saved(name), saved_outputs()[name]['answers']
    fields = ('proposed_kind', 'hypothesis', 'evidence_ids', 'requested_intervention_id')
    raws = []
    for answer in answers:
        if len(request['turns']) == 2 and (answer['attempt'] == 0 or name == 'v2g-dev5'):
            exact = request['turns'][1]['messages'][2]['content']
            assert {k: json.loads(exact)[k] for k in fields} == {k: answer[k] for k in fields}
            raws.append(exact)
        else:
            raws.append(canonical_json({k: answer[k] for k in fields}))
    return raws


class Provider:
    """Keeps every request (a deep copy, as sent) and answers with scripted outputs; a callable gets the messages."""
    def __init__(self, outputs): self.outputs = list(outputs); self.requests = []
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        self.requests.append(json.loads(json.dumps(messages)))
        output = self.outputs.pop(0)
        return RuntimeGeneration(output(messages) if callable(output) else output, MODEL, input_tokens=100, output_tokens=20)


class Ledger:
    """Records every reservation, release and charge in order (the Diagnostician's and the Mechanic's calls)."""
    def __init__(self): self.reservations = {}; self.log = []
    def consume_call(self, *, reservation=None, role='actor'): self.log.append(('consume', reservation, role))
    def reconcile(self, generation): self.log.append(('reconcile',))
    def reserve(self, name, calls, tokens=None): self.reservations[name] = calls; self.log.append(('reserve', name, calls))
    def release(self, name): self.reservations.pop(name, None); self.log.append(('release', name))


def real_mechanic(tmp_path, outputs, *, flag, label):
    store, provider, ledger = LabStore(tmp_path / f'{label}.db'), Provider(outputs), Ledger()
    mechanic = Mechanic(provider, store, ledger)
    if flag: mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
    return mechanic, provider, store, ledger


# =================================================================================================== T2: flag off is golden

@pytest.mark.anyio
@pytest.mark.parametrize('name', NAMES)
async def test_T2_flag_off_sends_the_saved_bytes_and_flag_on_changes_only_the_repair_turn(tmp_path, name):
    request, raws = saved(name), saved_raws(name)
    runs = {}
    for flag in (False, True):
        mechanic, provider, store, _ = real_mechanic(tmp_path, raws, flag=flag, label=f'{name}-{flag}')
        ref, proposal, got = await mechanic.diagnose(context_of(name))
        runs[flag] = SimpleNamespace(requests=provider.requests, raws=got, proposal=proposal, outputs=store.list_records('mechanic_outputs'))
    off, on = runs[False], runs[True]
    # Flag off: every turn is exactly what the live run sent (rebuilt by investigation A), byte for byte.
    assert len(off.requests) == len(request['turns'])
    for turn, sent in zip(request['turns'], off.requests):
        assert sent == turn['messages']
        assert [m['content'] for m in sent] == [m['content'] for m in turn['messages']]
    assert input_token_bound(off.requests[0], MODEL) == FIRST_TOKENS[name]
    if name in REPAIR_TOKENS:
        assert input_token_bound(off.requests[1], MODEL) == REPAIR_TOKENS[name]
    # Flag on: the first turn is identical; only a repair turn differs (T4).
    assert on.requests[0] == off.requests[0] and len(on.requests) == len(off.requests)
    assert off.raws == on.raws == raws[:len(off.requests)]                        # the model's text, verbatim
    assert (off.proposal is None) == (on.proposal is None) == (name == 'v2g-dev5')
    # mechanic_outputs records: the same fields and values with or without the rule (only the per-request id is random).
    strip = lambda rows: [{k: v for k, v in row.items() if k != 'request_id'} for row in rows]
    assert strip(off.outputs) == strip(on.outputs)
    assert all(set(row) == {'raw', 'role', 'prompt', 'attempt', 'model_id', 'request_id', 'campaign_id', 'episode_id', 'usage'}
               for row in off.outputs)


# =================================================================================================== T4: the repair turn

def test_T4_the_flag_off_repair_line_is_the_one_before_the_rule_and_its_text_is_the_constant():
    source = (ROOT / 'backend/app/agents/mechanic.py').read_text()
    line = ("                messages.extend([{'role':'assistant','content':generation.content},{'role':'user','content':canonical_json("
            "{'validation_errors':errors,'instruction':'" + FORMAT_REPAIR_INSTRUCTION + "'})}])\n")
    assert source.count(line) == 1
    import subprocess
    before = subprocess.run(['git', 'show', '626bae4:backend/app/agents/mechanic.py'], cwd=ROOT, capture_output=True, text=True)
    if before.returncode == 0:                                   # the backup tip, when this clone has it
        assert before.stdout.count(line) == 1


@pytest.mark.anyio
@pytest.mark.parametrize('name', ['v2g-dev5', 'v2f-dev5'])
async def test_T4_the_rule_1_repair_turn_states_the_limit_and_the_answers_length(tmp_path, name):
    request = saved(name)
    mechanic, provider, _, _ = real_mechanic(tmp_path, saved_raws(name), flag=True, label=name)
    await mechanic.diagnose(context_of(name))
    repair = provider.requests[1]
    assert repair[:3] == request['turns'][1]['messages'][:3]                     # same first turn, same verbatim answer
    message = json.loads(repair[3]['content'])
    assert message == {'validation_errors': [{'location': ['hypothesis'], 'type': 'string_too_long', 'max_characters': 600,
                                              'your_characters': REPLAYED_LENGTH[name]}],
                       'instruction': FORMAT_REPAIR_INSTRUCTION + ' ' + diagnosis_protocol.REPAIR_SENTENCE}
    assert repair[3]['content'] == canonical_json(message) == diagnosis_protocol.repair_message(message['validation_errors'])
    today = json.loads(request['turns'][1]['messages'][3]['content'])
    assert today['instruction'] == FORMAT_REPAIR_INSTRUCTION and message['instruction'].startswith(today['instruction'] + ' ')
    assert input_token_bound(repair, MODEL) - REPAIR_TOKENS[name] == 47
    state = mechanic.last_diagnosis
    assert state['request_id'].startswith('mechanic-request-') and state['first_turn_hash'] == content_hash(request['turns'][0]['messages'])
    assert len(state['output_refs']) == 2 and state['validation_errors'][0] == message['validation_errors']
    assert state['validation_errors'][1] == ([] if name == 'v2f-dev5' else message['validation_errors'])


@pytest.mark.anyio
@pytest.mark.parametrize('flag', [False, True])
async def test_T4_the_600_character_limit_is_unchanged_and_text_is_never_shortened(tmp_path, flag):
    context = context_of('v2d-dev5')
    base = json.loads(saved_raws('v2d-dev5')[0])
    long, exact = canonical_json({**base, 'hypothesis': 'x' * 601}), canonical_json({**base, 'hypothesis': 'y' * 600})
    mechanic, provider, store, _ = real_mechanic(tmp_path, [long, exact], flag=flag, label='fits')
    _, proposal, raws = await mechanic.diagnose(context)
    assert raws == [long, exact] and proposal.hypothesis == 'y' * 600
    errors = json.loads(provider.requests[1][3]['content'])['validation_errors']
    assert errors == ([{'location': ['hypothesis'], 'type': 'string_too_long', 'max_characters': 600, 'your_characters': 601}]
                      if flag else [{'location': ['hypothesis'], 'type': 'string_too_long'}])
    mechanic, _, store, _ = real_mechanic(tmp_path, [long, long], flag=flag, label='fails')
    _, proposal, raws = await mechanic.diagnose(context)
    assert proposal is None and raws == [long, long]
    assert [row['raw'] for row in store.list_records('mechanic_outputs')] == [long, long]     # stored verbatim, 601 characters
    with pytest.raises(ValidationError):
        TypeAdapter(DiagnosticProposal).validate_json(long)
    assert TypeAdapter(DiagnosticProposal).validate_json(exact).hypothesis == 'y' * 600


@pytest.mark.anyio
async def test_T4_other_errors_keep_todays_form_under_the_rule(tmp_path):
    context = context_of('v2d-dev5')
    base = json.loads(saved_raws('v2d-dev5')[0])
    unknown = canonical_json({**base, 'evidence_ids': ['evidence-00000000000000000000000000000000']})
    results = {}
    for flag in (False, True):
        mechanic, provider, _, _ = real_mechanic(tmp_path, [unknown, saved_raws('v2d-dev5')[0]], flag=flag, label=f'b{flag}')
        await mechanic.diagnose(context)
        results[flag] = json.loads(provider.requests[1][3]['content'])
    assert results[False]['validation_errors'] == results[True]['validation_errors'] == [{'location': ['evidence_ids'], 'type': 'unknown_evidence_reference'}]
    assert results[False]['instruction'] == FORMAT_REPAIR_INSTRUCTION
    assert results[True]['instruction'] == diagnosis_protocol.REPAIR_INSTRUCTION


@pytest.mark.anyio
async def test_T4_candidate_and_completion_requests_are_never_changed_by_the_rule(tmp_path):
    from app.contracts.models import MechanicOutput
    too_long = canonical_json({'no_change_reason': 'z' * 700})
    for flag in (False, True):
        mechanic, provider, _, _ = real_mechanic(tmp_path, [too_long, too_long], flag=flag, label=f'p{flag}')
        await mechanic.propose({'campaign_id': 'campaign-x'})
        assert json.loads(provider.requests[1][3]['content'])['instruction'] == FORMAT_REPAIR_INSTRUCTION
        assert mechanic.last_diagnosis is None
    assert MechanicOutput is not None


# =================================================================================================== T3: the guide is additive

@pytest.mark.parametrize('name', NAMES)
def test_T3_the_guide_adds_exactly_one_key_and_the_same_number_of_tokens_to_every_first_turn(name):
    first = saved(name)['turns'][0]['messages']
    full = json.loads(first[1]['content'])
    guided = diagnosis_guide.attach(full, task_text=TASK_TEXT)
    assert set(guided) - set(full) == {'diagnosis_guide'}
    assert all(canonical_json(guided[key]) == canonical_json(full[key]) for key in full)     # every other key byte-identical
    assert input_token_bound([first[0], {'role': 'user', 'content': canonical_json(guided)}], MODEL) - FIRST_TOKENS[name] == GUIDE_TOKENS
    block = guided['diagnosis_guide']
    assert block == diagnosis_guide.block(TASK_TEXT)
    assert set(block) == {'protocol', 'meaning', 'task', 'kinds', 'checks', 'checks_note', 'contract_note', 'use', 'hypothesis_length'}
    assert block['checks'] == PUBLIC_INVARIANTS and block['task'] == TASK_TEXT
    if name in ('v2f-dev5', 'v2g-dev5', 'v2g-dev6'):
        # The citation block and the V2 memory pointer (citation-status rule) are carried unchanged.
        assert guided['native_citation_status'] == full['native_citation_status']
        assert guided['runtime_contract']['actor_contract']['memory'] == V2_MEMORY_WITH_CITATION_STATUS
    with pytest.raises(RuntimeError, match='already carries'):
        diagnosis_guide.attach(guided, task_text=TASK_TEXT)


def test_T3_the_guide_interprets_no_check_and_names_no_episode():
    """PM decisions: the draft's interpretive checks_note sentence (C6 is the citation check; where C6 passed, the citations
    met it) is dropped; its two neutral sentences, which name no check, are kept word for word (review finding F4). The
    C1-C8 public meanings are included verbatim only; no fixed sentence mentions a check or a worked example."""
    declared = diagnosis_guide.declaration()
    assert declared['checks_note'] == diagnosis_guide.block(TASK_TEXT)['checks_note'] == diagnosis_guide.CHECKS_NOTE == CHECKS_NOTE
    assert C6_SENTENCE not in canonical_json(declared) and C6_SENTENCE not in canonical_json(diagnosis_guide.block(TASK_TEXT))
    assert declared['checks'] == PUBLIC_INVARIANTS and declared['checks_hash'] == content_hash(PUBLIC_INVARIANTS)
    fixed = [declared['meaning'], declared['checks_note'], declared['contract_note'], declared['use'], declared['hypothesis_length'],
             *declared['kinds'].values()]
    import re
    assert not any(re.search(r'\bC[1-8]\b', text) for text in fixed)
    assert not any(word in ' '.join(fixed).lower() for word in ('dev-5', 'dev-6', 'express', 'citation'))
    assert 'Requesting an intervention is not a claim' not in canonical_json(declared)
    assert 'not scored' not in canonical_json(declared)


def test_T3_the_size_rule_counts_the_guide_and_never_compacts_it(tmp_path):
    """A synthetic diagnosis request at most 32,000 tokens without the guide and over it with the guide: the size rule
    (faultlab-mechanic-context/v2-bounded) compacts only the version with the guide, to at most 28,000 tokens, and the
    compacted request keeps the guide block byte for byte."""
    store = LabStore(tmp_path / 'lab.db')
    counter = SimpleNamespace(counterexample_id='counterexample-synthetic', source_episode_id='episode-source',
                              reproduction_trial_ids=['episode-r1', 'episode-r2'])
    mechanic = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: MODEL), metadata=None)
    bound = lambda value: loop_limits.mechanic_request_bound(mechanic, 'diagnosis.md', TypeAdapter(DiagnosticProposal), value)

    def rich_bundle(episode, count, failed=()):
        observations = [PublicObservation(episode_id=episode, evidence_id=f'evidence-{episode}-{i}', call_id=f'call-{episode}-{i}',
                                          delivered_tick=min(i + 1, 20),
                                          result=ToolResult(call_id=f'call-{episode}-{i}', tool='get_operation_status', transport='ok',
                                                            status='PENDING', error_code=f'synthetic note {episode} {i} ' + 'w' * 40))
                        for i in range(count)]
        report = TaskReport.model_validate({'upgrade_outcome': 'SUCCEEDED', 'notification_outcome': 'SUCCEEDED', 'overall': 'COMPLETED',
                                            'evidence_ids': [observations[0].evidence_id], 'next_action': {'kind': 'NONE'}})
        findings = [CheckResult(check_id=f'C{n}', passed=f'C{n}' not in failed, category='fixture',
                                evidence_ids=[o.evidence_id for o in observations], event_ids=['event-0']) for n in range(1, 9)]
        return SimpleNamespace(episode_id=episode, source='weave_verified', observations=observations, report=report, findings=findings)

    protected = [rich_bundle(e, 6, failed=('C3',)) for e in ('episode-source', 'episode-r1', 'episode-r2')]

    def context(clean, pad):
        bundles = protected + [rich_bundle(f'episode-clean-{i}', 18) for i in range(clean)]
        return {'counterexample_id': counter.counterexample_id, 'target_invariant': 'C3',
                'evidence_ids': [o.evidence_id for b in protected for o in b.observations][:36], 'intervention_ids': [],
                'interventions': [], 'observations': summarize_evidence(bundles), 'reduction': {'note': 'pad ' * pad}}
    low, high = 1, 200                        # the most clean episodes that keep the request under 31,000 tokens
    while low < high:
        middle = (low + high + 1) // 2
        if bound(context(middle, 0)) <= 31000: low = middle
        else: high = middle - 1
    small, large = 0, 4000                    # then pad to just under the 32,000 limit
    while small < large:
        middle = (small + large + 1) // 2
        if bound(context(low, middle)) <= loop_limits.MODEL_INPUT_TOKEN_LIMIT: small = middle
        else: large = middle - 1
    plain = context(low, small)
    guided = diagnosis_guide.attach(plain, task_text=TASK_TEXT)
    assert 31000 < bound(plain) <= loop_limits.MODEL_INPUT_TOKEN_LIMIT < bound(guided)
    unchanged, ref = loop_limits.fit_request(store, mechanic, plain, request_kind='mechanic_diagnosis', campaign_id='campaign-x', counterexample=counter)
    assert unchanged is plain and ref is None                                   # without the guide it would be sent as is
    fitted, ref = loop_limits.fit_request(store, mechanic, guided, request_kind='mechanic_diagnosis', campaign_id='campaign-x', counterexample=counter)
    record, = store.list_records('mechanic_context_records')
    assert record['outcome'] == 'COMPACTED' and record['full_request_tokens'] == bound(guided)   # counted with the guide
    assert bound(fitted) <= loop_limits.COMPACTION_TARGET_TOKENS
    assert fitted['diagnosis_guide'] == guided['diagnosis_guide']               # never compacted
    assert canonical_json(fitted['diagnosis_guide']) == canonical_json(diagnosis_guide.block(TASK_TEXT))


# =================================================================================================== T5 / T6: record and gate

RECIPE = FaultSpec.model_validate({'seed': 5, 'primitives': [{'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders',
                                                              'occurrence': 1, 'parameters': {'completion_delay_ticks': 3,
                                                              'terminal_status': 'SUCCEEDED', 'failure_code': None}}]})
POLICY = SimpleNamespace(policy_hash=content_hash('policy-fixture'), version='policy-v0')
EVIDENCE = [bundle(e, ['PENDING', 'FAILED'], failed=('C3',)) for e in ('episode-source', 'episode-r0', 'episode-r1')]
CAMPAIGN = SimpleNamespace(campaign_id='campaign-fixture', task_text=TASK_TEXT)


def reproduction(valid=True):
    trials = [TrialResult(episode_id=f'episode-r{i}', world_id=f'world-r{i}', scenario_hash=content_hash(RECIPE), policy_hash=POLICY.policy_hash,
                          arm='B0', trial_index=i, lifecycle='COMPLETED', outcome='VIOLATION', failed_checks=['C3'], fault_scheduled=True,
                          fault_triggered=True, usage=Usage(actor_calls=3, http_attempts=3)) for i in range(3)]
    return trials if valid else trials[:2]


class Runner:
    """Deterministic fresh trials: control violates C3; the treatment is clean (SUPPORTED), violates too (CONTRADICTED), or
    the second control trial is clean (INCONCLUSIVE)."""
    def __init__(self, mode): self.mode = mode; self.calls = []
    async def run(self, campaign, spec, policy, *, purpose, trial_index, fixture_id, ledger, reservation, stop):
        control = content_hash(spec) == content_hash(RECIPE)
        index = len(self.calls); self.calls.append((purpose, control, trial_index, reservation))
        violation = control or self.mode == 'CONTRADICTED'
        if self.mode == 'INCONCLUSIVE' and control and trial_index == 1: violation = False
        return TrialResult(episode_id=f'episode-i{index}', world_id=f'world-i{index}', scenario_hash=content_hash(spec), policy_hash=policy.policy_hash,
                           arm='B0', trial_index=trial_index, lifecycle='COMPLETED', outcome='VIOLATION' if violation else 'COMPLETED',
                           failed_checks=['C3'] if violation else [], fault_scheduled=bool(spec.primitives), fault_triggered=bool(spec.primitives),
                           usage=Usage(actor_calls=3, http_attempts=3))


def answer(kind, *, requested=True, length=None):
    def output(messages):
        context = json.loads(messages[1]['content'])
        hypothesis = 'Offline fixture: removing the delay removes the premature confirmation.' if length is None else 'h' * length
        return canonical_json({'proposed_kind': kind, 'hypothesis': hypothesis, 'evidence_ids': context['evidence_ids'][:1],
                               'requested_intervention_id': context['intervention_ids'][0] if requested else None})
    return output


ANSWERS = {'null': [answer('CONTRACT_EVIDENCE_GAP', requested=False)],
           'valid_request': [answer('POLICY_GAP')],
           'invalid_output': [answer('CONTRACT_EVIDENCE_GAP', length=614), answer('CONTRACT_EVIDENCE_GAP', length=614)],
           'invalid_then_valid': [answer('CONTRACT_EVIDENCE_GAP', length=743), answer('CONTRACT_EVIDENCE_GAP')]}


async def diagnose(tmp_path, monkeypatch, *, answers, mode='SUPPORTED', reproduced=True, flag, label, stop=None, runner=None):
    import app.lab.diagnosis as diagnosis
    original = diagnosis.run_interventions
    if mode == 'PREFLIGHT_REJECTED':
        monkeypatch.setattr(diagnosis, 'run_interventions', functools.partial(original, validate=lambda recipe: False))
    store, provider, ledger = LabStore(tmp_path / f'{label}.db'), Provider(list(answers)), Ledger()
    mechanic = Mechanic(provider, store, ledger); runner = runner or Runner(mode)
    chain = mechanic
    if flag:
        mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
        chain = diagnosis_protocol.RecordingDiagnosisMechanic(mechanic, mechanic)
    counter = SimpleNamespace(counterexample_id='counterexample-fixture', target_invariant='C3', attempted_count=3, valid_count=3,
                              target_violation_count=3)
    try:
        diagnostic, run = await Diagnostician(store, runner, ledger, chain).run(CAMPAIGN, counter, RECIPE, POLICY, reproduction(reproduced),
                                                                                evidence=EVIDENCE, **({'stop': stop} if stop else {}))
    finally:
        monkeypatch.setattr(diagnosis, 'run_interventions', original)
    record = diagnosis_protocol.record(store, CAMPAIGN, counter, diagnostic, run, chain) if flag else None
    return SimpleNamespace(diagnostic=diagnostic, run=run, record=record, provider=provider, ledger=ledger, runner=runner, store=store)


@pytest.mark.anyio
@pytest.mark.parametrize('case,status,source,attempts', [
    ('valid_request', 'VALID_REQUESTED', 'model', 1),
    ('null', 'VALID_NO_REQUEST', 'model', 1),
    ('invalid_output', 'INVALID_OUTPUT', 'code_default', 2),
    ('invalid_then_valid', 'VALID_REQUESTED', 'model', 2),
])
async def test_T5_the_record_says_requested_declined_or_invalid_and_lists_every_attempt(tmp_path, monkeypatch, case, status, source, attempts):
    on = await diagnose(tmp_path, monkeypatch, answers=ANSWERS[case], flag=True, label='on')
    off = await diagnose(tmp_path, monkeypatch, answers=ANSWERS[case], flag=False, label='off')
    record = on.record
    assert on.store.get_record('diagnosis_requests', on.diagnostic.diagnostic_id) == record
    assert record['proposal_status'] == status and record['recorded_proposed_kind_source'] == source
    outputs = on.store.list_records('mechanic_outputs')
    refs = [row[0] for row in on.store.db.execute("SELECT id FROM records WHERE kind='mechanic_outputs' ORDER BY rowid")]
    assert record['output_refs'] == refs and len(refs) == attempts                     # every attempt, in order, by id
    assert [a['output_ref'] for a in record['attempts']] == refs and [a['attempt'] for a in record['attempts']] == list(range(attempts))
    assert len({row['request_id'] for row in outputs}) == 1 and record['request_id'] == outputs[0]['request_id']
    context = json.loads(on.provider.requests[0][1]['content'])
    assert [o['change'] for o in record['options']] == [o['change'] for o in context['interventions']]   # change strings
    assert [o['intervention_id'] for o in record['options']] == context['intervention_ids']
    assert record['first_turn_hash'] == content_hash(on.provider.requests[0])
    if status == 'VALID_REQUESTED':
        assert record['requested_intervention_id'] == context['intervention_ids'][0] and record['intervention_ran']
        assert record['requested_change'] == context['interventions'][0]['change'] == 'remove_primitive:0'
        assert [r['result'] for r in record['interventions']] == ['SUPPORTED'] and record['verdict'] == 'POLICY_GAP'
    else:
        assert record['requested_intervention_id'] is None and not record['intervention_ran'] and record['verdict'] == 'INCONCLUSIVE'
    if case == 'invalid_output':
        assert record['recorded_proposed_kind'] == 'INCONCLUSIVE'                        # the code default, labelled as such
        assert record['last_raw_unvalidated'] == {'validated': False, 'parsed_json_object': True, 'proposed_kind': 'CONTRACT_EVIDENCE_GAP',
                                                  'requested_intervention_id': context['intervention_ids'][0]}
        assert [a['validation_errors'] for a in record['attempts']] == [[{'location': ['hypothesis'], 'type': 'string_too_long',
                                                                        'max_characters': 600, 'your_characters': 614}]] * 2
        assert 'code default' in record['statement'] and '614 of at most 600 characters' in record['statement']
    if case == 'invalid_then_valid':
        assert record['attempts'][0]['validation_errors'][0]['your_characters'] == 743 and record['attempts'][1]['validation_errors'] == []
    # The diagnostic itself is exactly the flag-off one (only its random id differs).
    strip = lambda d: {k: v for k, v in d.model_dump(mode='json').items() if k != 'diagnostic_id'}
    assert strip(on.diagnostic) == strip(off.diagnostic)
    assert off.store.list_records('diagnosis_requests') == []
    with pytest.raises(StoreConflict):                                                   # immutable
        on.store.put_record('diagnosis_requests', on.diagnostic.diagnostic_id, {**record, 'proposal_status': 'VALID_REQUESTED' if status != 'VALID_REQUESTED' else 'INVALID_OUTPUT'}, immutable=True)


def test_T5_a_record_is_never_written_from_state_that_does_not_describe_the_diagnosis():
    wrapper = SimpleNamespace(last=None)
    counter = SimpleNamespace(counterexample_id='counterexample-x', target_invariant='C3')
    diagnostic = SimpleNamespace(diagnostic_id='diagnostic-x', proposed_kind='INCONCLUSIVE', kind='INCONCLUSIVE')
    # The refusal names the diagnosis, so an operator can find it (review finding LOW-4, fixer).
    with pytest.raises(RuntimeError, match='No Mechanic attempt state for diagnosis diagnostic-x'):
        diagnosis_protocol.build_record(CAMPAIGN, counter, diagnostic, SimpleNamespace(experiments=[], trials=[]), wrapper)
    wrapper.last = {'ref': 'mechanic-b', 'proposal': None, 'raws': ['{}'], 'options': [],
                    'attempts': {'request_id': 'r', 'first_turn_hash': 'h', 'output_refs': ['mechanic-a'], 'validation_errors': [[{'x': 1}]]}}
    with pytest.raises(RuntimeError, match='does not match diagnosis diagnostic-x'):
        diagnosis_protocol.build_record(CAMPAIGN, counter, diagnostic, SimpleNamespace(experiments=[], trials=[]), wrapper)
    # Fresh trials without any recorded experiment cannot describe a diagnosis either.
    wrapper.last = {'ref': 'mechanic-a', 'proposal': None, 'raws': ['{}'], 'options': [],
                    'attempts': {'request_id': 'r', 'first_turn_hash': 'h', 'output_refs': ['mechanic-a'], 'validation_errors': [[{'x': 1}]]}}
    with pytest.raises(RuntimeError, match='diagnostic-x'):
        diagnosis_protocol.build_record(CAMPAIGN, counter, diagnostic, SimpleNamespace(experiments=[], trials=[object()]), wrapper)


MATRIX = [(reproduced, case, mode) for reproduced in (True, False) for case in ('null', 'valid_request', 'invalid_output')
          for mode in ('SUPPORTED', 'INCONCLUSIVE', 'CONTRADICTED', 'PREFLIGHT_REJECTED')]


@pytest.mark.anyio
@pytest.mark.parametrize('reproduced,case,mode', MATRIX)
async def test_T6_the_rule_changes_no_kind_intervention_reservation_or_trial(tmp_path, monkeypatch, reproduced, case, mode):
    off = await diagnose(tmp_path, monkeypatch, answers=ANSWERS[case], mode=mode, reproduced=reproduced, flag=False, label='off')
    on = await diagnose(tmp_path, monkeypatch, answers=ANSWERS[case], mode=mode, reproduced=reproduced, flag=True, label='on')
    strip = lambda d: {k: v for k, v in d.model_dump(mode='json').items() if k != 'diagnostic_id'}
    assert strip(on.diagnostic) == strip(off.diagnostic)
    experiments = lambda store: [{k: v for k, v in e.items() if k != 'proposal_ref'} for e in store.list_records('interventions')]
    assert experiments(on.store) == experiments(off.store)
    assert on.ledger.log == off.ledger.log and on.runner.calls == off.runner.calls
    assert [t.model_dump(mode='json') for t in on.run.trials] == [t.model_dump(mode='json') for t in off.run.trials]
    assert on.provider.requests[0] == off.provider.requests[0]            # the first turn never changes
    expected_kind = 'POLICY_GAP' if (reproduced and case == 'valid_request' and mode == 'SUPPORTED') else 'INCONCLUSIVE'
    assert on.diagnostic.kind == expected_kind
    requested = case == 'valid_request'
    # intervention_ran means at least one fresh intervention trial ran (review finding MEDIUM-1/F3, fixer): a requested
    # intervention that preflight rejected ran none. intervention_experiment_recorded says an experiment was saved at all.
    ran = requested and mode != 'PREFLIGHT_REJECTED'
    assert on.record['intervention_ran'] is ran and on.record['intervention_experiment_recorded'] is requested
    assert len(on.runner.calls) == on.record['fresh_intervention_trials'] == (6 if ran else 0)
    if requested and mode == 'PREFLIGHT_REJECTED':
        assert on.record['interventions'][0]['limitations'] == ['PREFLIGHT_REJECTED']
        assert on.record['interventions'][0]['early_end'] == 'PREFLIGHT_REJECTED'
        assert 'no fresh trial ran' in on.record['statement'] and 'preflight rejected' in on.record['statement']
    elif requested:
        assert on.record['interventions'][0]['early_end'] is None and 'after 3 of 3 trial pairs' in on.record['statement']


PINNED_UNCHANGED = {
    'backend/app/referee/diagnostics.py': '5b83fbc84c20a7bd6db236f370093e5adc09c3c5c35e230fca2c07c8c90d45d9',
    'backend/app/referee/reducer.py': 'c775f9cc430f3371f1e6c40dfff471943aba9dab31a96a406b96a36802dfd4d8',
    'backend/app/lab/diagnosis.py': '76d53c108e287156dca692491f391d459cf309d3aecf5a1f6df95b87b2276690',
    'backend/app/agents/prompts/diagnosis.md': '5488c7f5b1736002003d8dff9ba1774bbfd814572daa49de9dd222fea701a4e5',
    'backend/app/contracts/models.py': 'd0e2f5d63991adb744a8c1b14fe1e222bb4f2546cf632cbe21e643de583a318e',
    'backend/app/lab/citation_status.py': 'd1a5bc26bba5b17670ca0426b05809ec1ef2039a09285f85241966ed71d00a54',
}


def test_T6_the_verdict_code_prompt_and_gate_line_are_unchanged():
    from app.referee.diagnostics import PROTOCOL_HASH
    for path, digest in PINNED_UNCHANGED.items():
        assert sha256_file(ROOT / path) == digest, path
    assert PROTOCOL_HASH == 'bfefe69bd6a91e44d24c2ad83d3b42e280df722f1662c84d658826ce38f72287'
    source = (ROOT / 'backend/app/lab/learning.py').read_text()
    gate = "            if diagnostic.kind!='POLICY_GAP': continue\n"
    assert source.count(gate) == 1
    assert source.index('diagnosis_protocol.record(') < source.index(gate)            # the record is written before the gate


# =================================================================================================== T1: plans

from test_discovery_v2_flow import learn_campaign, owner, request  # noqa: E402,F401  (owner is a fixture)
from app.lab.operator_actions import register_agent  # noqa: E402
from app.lab.run_plans import (DiagnosisGuidePlan, MechanicDiagnosisPlan, SavedRunPlan, build_run_options,  # noqa: E402
                               prepare_run_plan, read_run_plan, validate_run_plan)


def test_T1_every_new_learn_plan_freezes_rule_1_and_no_plan_freezes_rule_2(owner):
    options = build_run_options(owner.settings, owner.store)
    assert options['learn']['mechanic_diagnosis'] == diagnosis_protocol.declaration()
    assert 'diagnosis_guide' not in options['learn'] and diagnosis_guide.DIAGNOSIS_GUIDE_OFFERED is False
    for agent in ('reference', 'smolagents', 'smolagents-v2'):
        campaign = learn_campaign(owner, None, agent)
        plan = read_run_plan(owner.store, campaign)['plan']
        assert plan['mechanic_diagnosis'] == diagnosis_protocol.declaration() and 'diagnosis_guide' not in plan
        assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan
        assert diagnosis_protocol.campaign_rule(owner.store, campaign) == diagnosis_protocol.declaration()
        assert diagnosis_guide.campaign_rule(owner.store, campaign) is None
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-5'))
    assert not {'mechanic_diagnosis', 'diagnosis_guide'} & set(baseline.plan)
    saved_baseline = owner.create(baseline.campaign_request, run_plan=baseline)
    assert not {'mechanic_diagnosis', 'diagnosis_guide'} & set(owner.store.get_record('campaign_plans', saved_baseline.campaign_id))


def test_T1_the_declarations_are_exact(owner):
    MechanicDiagnosisPlan.model_validate(diagnosis_protocol.declaration())
    DiagnosisGuidePlan.model_validate(diagnosis_guide.declaration())
    for change in ({'repair_sentence': 'Shorten it.'}, {'repair_instruction': FORMAT_REPAIR_INSTRUCTION}, {'rule': 'Another wording.'},
                   {'proposal_statuses': ['VALID_REQUESTED', 'VALID_NO_REQUEST', 'DECLINED']}, {'kind_sources': ['model', 'default']},
                   {'hypothesis_max_characters': 700}, {'first_turn_changed': True}, {'model_text_edited': True}, {'verdict_code_changed': True},
                   {'record_written_before_gate': False}, {'semantics_hash': '0' * 64}, {'protocol': 'faultlab-mechanic-diagnosis/v2'},
                   {'string_too_long_fields': ['max_characters', 'length']}):
        with pytest.raises(ValidationError):
            MechanicDiagnosisPlan.model_validate({**diagnosis_protocol.declaration(), **change})
    altered_checks = {**PUBLIC_INVARIANTS, 'C6': 'Cite only delivered evidence.'}
    for change in ({'kinds': {**diagnosis_guide.KINDS, 'POLICY_GAP': 'Something else.'}}, {'contract_note': 'x'}, {'use': 'x'},
                   {'hypothesis_length': 'x'}, {'meaning': 'x'}, {'rule': 'x'}, {'checks_hash': '0' * 64},
                   {'checks': altered_checks}, {'interprets_checks': True}, {'reads_scoring': True},
                   {'checks_note': 'C6 is the citation check.'}, {'checks_note': CHECKS_NOTE.replace(' Explain', ' ' + C6_SENTENCE + ' Explain')},
                   {'task_source': 'episode'}):
        with pytest.raises(ValidationError):
            DiagnosisGuidePlan.model_validate({**diagnosis_guide.declaration(), **change})
    with pytest.raises(ValidationError):                                          # the note is part of the declared text
        DiagnosisGuidePlan.model_validate({k: v for k, v in diagnosis_guide.declaration().items() if k != 'checks_note'})
    # A consistent but different C1-C8 text (hash recomputed) is a valid plan block, and Start refuses it (below).
    DiagnosisGuidePlan.model_validate({**diagnosis_guide.declaration(), 'checks': altered_checks, 'checks_hash': content_hash(altered_checks)})


def test_T1_only_learn_plans_may_declare_either_rule(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    for key, value in (('mechanic_diagnosis', diagnosis_protocol.declaration()), ('diagnosis_guide', diagnosis_guide.declaration())):
        baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-1'))
        baseline.plan[key] = value
        with pytest.raises(StoreConflict, match='Only a Learn plan declares the diagnosis repair-and-record rule or the diagnosis guide'):
            owner.create(baseline.campaign_request, run_plan=baseline)


def _create_unchecked(owner, monkeypatch, **plan_changes):
    """A Learn plan as another build might have saved it: created past this build's Start check."""
    from app.lab import run_plans
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan.update(plan_changes)
    with monkeypatch.context() as patch:
        patch.setattr(run_plans, 'validate_run_plan', lambda *args, **kwargs: None)
        return owner.create(prepared.campaign_request, run_plan=prepared)


def test_T1_a_synthetic_plan_declaring_the_guide_starts_only_while_its_frozen_text_and_hash_are_installed(owner, monkeypatch):
    campaign = _create_unchecked(owner, monkeypatch, diagnosis_guide=diagnosis_guide.declaration())
    plan = read_run_plan(owner.store, campaign)['plan']
    assert plan['diagnosis_guide'] == diagnosis_guide.declaration()
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan      # Start accepts it
    assert diagnosis_guide.campaign_rule(owner.store, campaign) == diagnosis_guide.declaration()
    # An edit to PUBLIC_INVARIANTS changes the installed declaration: Start refuses the frozen plan.
    monkeypatch.setattr(diagnosis_guide, 'PUBLIC_INVARIANTS', {**PUBLIC_INVARIANTS, 'C8': 'An edited meaning.'})
    with pytest.raises(StoreConflict, match='installed diagnosis guide'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    monkeypatch.undo()
    altered = {**PUBLIC_INVARIANTS, 'C6': 'Cite only delivered evidence.'}
    other = _create_unchecked(owner, monkeypatch, diagnosis_guide={**diagnosis_guide.declaration(), 'checks': altered, 'checks_hash': content_hash(altered)})
    assert read_run_plan(owner.store, other)['plan']['diagnosis_guide']['checks'] == altered                  # it still reads
    with pytest.raises(StoreConflict, match='installed diagnosis guide'):
        validate_run_plan(owner.store, owner.settings, owner.get(other.campaign_id))


def test_T1_start_refuses_a_plan_whose_rule_1_is_not_the_installed_one(owner, monkeypatch):
    from app.lab import run_plans
    campaign = learn_campaign(owner, None, 'reference')
    installed = diagnosis_protocol.declaration()
    monkeypatch.setattr(run_plans, 'mechanic_diagnosis_declaration', lambda: {**installed, 'rule': 'A later build\'s wording.'})
    with pytest.raises(StoreConflict, match='installed diagnosis repair-and-record rule differs'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    monkeypatch.undo()
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan['mechanic_diagnosis'] = {**installed, 'repair_sentence': 'An altered sentence.'}
    with pytest.raises((ValidationError, StoreConflict)):                               # an altered text never saves
        owner.create(prepared.campaign_request, run_plan=prepared)


def test_T1_a_learn_plan_saved_before_the_rules_keeps_its_bytes_and_todays_behaviour(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan.pop('mechanic_diagnosis')                     # exactly as the runtime before the rule saved it
    older = owner.create(prepared.campaign_request, run_plan=prepared)
    saved_plan = owner.store.get_record('campaign_plans', older.campaign_id)
    assert not {'mechanic_diagnosis', 'diagnosis_guide'} & set(saved_plan)
    assert saved_plan['plan_hash'] == content_hash({k: v for k, v in saved_plan.items() if k != 'plan_hash'})
    assert read_run_plan(owner.store, older)['plan'] == saved_plan                       # no null keys added
    assert SavedRunPlan.model_validate_json(canonical_json(saved_plan)).model_dump(mode='json') == saved_plan
    assert validate_run_plan(owner.store, owner.settings, owner.get(older.campaign_id)) == saved_plan
    assert diagnosis_protocol.campaign_rule(owner.store, older) is None and diagnosis_guide.campaign_rule(owner.store, older) is None


def test_T1_flipping_the_reviewed_constant_is_the_only_way_to_offer_the_guide(owner, monkeypatch):
    from app.lab import run_plans
    monkeypatch.setattr(run_plans, 'DIAGNOSIS_GUIDE_OFFERED', True)
    assert build_run_options(owner.settings, owner.store)['learn']['diagnosis_guide'] == diagnosis_guide.declaration()
    campaign = learn_campaign(owner, None, 'reference')
    assert read_run_plan(owner.store, campaign)['plan']['diagnosis_guide'] == diagnosis_guide.declaration()


SAVED_STORE = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
needs_store = pytest.mark.skipif(not SAVED_STORE.exists(), reason='Needs the saved native-v2b store (live runs v2d-v2g); absent on this machine')
# The store as this round was built and reviewed (its sha256 8aa9aa27..., after live run v2g): its last record row and
# the six plans earlier runtimes saved in it. Live runs keep adding to this store, and a plan this build saves declares
# Rule 1; such a plan gets a higher row number and is not read here, so it cannot change what this test checks.
SAVED_PLANS_CUTOFF = 8583
SAVED_PLAN_CAMPAIGNS = {'campaign-c8063a1166834051b08ae5317ff6f9c2', 'campaign-077b8434e14c4c73a334692223694e63',   # v2b study, v2c
                        'campaign-ea66672d7a904bd8a011d6922790c963', 'campaign-37e66b6c3a544a4d9bde4161db6bf0aa',   # v2d, v2e
                        'campaign-53db74766f4d4635b94a0de89e492577', 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530'}   # v2f, v2g


@needs_store
def test_T1_every_saved_native_v2b_plan_rereads_with_its_plan_hash_and_no_new_keys(tmp_path):
    import citation_status_saved as helpers
    from app.lab.storage import ReadOnlyLabStore
    assert 'Desktop' not in str(tmp_path) and '/FaultLab_Runs/' not in str(tmp_path)
    copy = tmp_path / 'lab' / 'lab.sqlite3'; copy.parent.mkdir()
    helpers.copy_read_only(SAVED_STORE, copy)
    store = ReadOnlyLabStore(copy)
    try:
        plans = [raw for _, raw in store.records_upto('campaign_plans', SAVED_PLANS_CUTOFF)]
        assert {raw['campaign_id'] for raw in plans} == SAVED_PLAN_CAMPAIGNS and len(plans) == 6
        for raw in plans:
            read = read_run_plan(store, raw['campaign_id'])['plan']
            assert read == raw and read['plan_hash'] == content_hash({k: v for k, v in raw.items() if k != 'plan_hash'})
            assert not {'mechanic_diagnosis', 'diagnosis_guide'} & set(read)
    finally:
        store.close(); assert helpers.remove_copy(copy)


# =================================================================================================== T7: export

def _seed_diagnosis(owner, campaign, *, with_record):
    """One diagnosis as the loop saves it: a v2f-style first attempt rejected at 743 characters and a valid repair."""
    store, ident = owner.store, campaign.campaign_id
    store.put_record('counterexamples', 'counterexample-x', {'counterexample_id': 'counterexample-x', 'campaign_id': ident,
                                                             'source_episode_id': 'episode-source'})
    common = {'role': 'mechanic', 'prompt': 'diagnosis.md', 'model_id': MODEL, 'request_id': 'mechanic-request-x', 'campaign_id': ident,
              'episode_id': None, 'usage': {'model_calls': 1, 'input_tokens': 1, 'output_tokens': 1, 'cost_dollars': None}}
    store.put_record('mechanic_outputs', 'mechanic-first', {**common, 'raw': '{"hypothesis":"' + 'h' * 743 + '"}', 'attempt': 0}, immutable=True)
    store.put_record('mechanic_outputs', 'mechanic-repair', {**common, 'raw': '{"hypothesis":"short"}', 'attempt': 1}, immutable=True)
    store.put_record('diagnostics', 'diagnostic-x', {'diagnostic_id': 'diagnostic-x', 'counterexample_id': 'counterexample-x', 'kind': 'POLICY_GAP'})
    store.put_record('interventions', 'intervention-x', {'intervention_id': 'intervention-x', 'counterexample_id': 'counterexample-x',
                                                         'proposal_ref': 'mechanic-repair', 'result': 'SUPPORTED'})
    if with_record:
        store.put_record('diagnosis_requests', 'diagnostic-x', {'protocol': diagnosis_protocol.MECHANIC_DIAGNOSIS_V1, 'campaign_id': ident,
                         'diagnostic_id': 'diagnostic-x', 'output_refs': ['mechanic-first', 'mechanic-repair'],
                         'proposal_status': 'VALID_REQUESTED'}, immutable=True)


def test_T7_the_export_embeds_every_attempt_by_id_only_for_plans_that_declare_rule_1(owner):
    from app.lab.exports import development_recording
    campaign = learn_campaign(owner, None, 'reference')
    _seed_diagnosis(owner, campaign, with_record=True)
    recording = development_recording(owner.store, campaign.campaign_id)
    assert [m.get('proposal_ref') for m in recording['mechanic_outputs']] == ['mechanic-repair']     # today's rule, unchanged
    row, = recording['diagnosis_requests']
    assert [(a['output_ref'], a['attempt']) for a in row['attempt_outputs']] == [('mechanic-first', 0), ('mechanic-repair', 1)]
    assert row['attempt_outputs'][0]['raw'] == '{"hypothesis":"' + 'h' * 743 + '"}'     # the rejected first attempt, verbatim
    # A plan saved before the rule: the recording has exactly today's keys (no diagnosis_requests), and the rule's code never runs.
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan.pop('mechanic_diagnosis')
    older = owner.create(prepared.campaign_request, run_plan=prepared)
    before = development_recording(owner.store, older.campaign_id)
    assert 'diagnosis_requests' not in before
    import app.lab.diagnosis_protocol as module
    original = module.campaign_records
    module.campaign_records = lambda *args: (_ for _ in ()).throw(AssertionError('rule-1 export code ran for an older plan'))
    try:
        assert canonical_json(development_recording(owner.store, older.campaign_id)) == canonical_json(before)
    finally:
        module.campaign_records = original


# =================================================================================================== T9: the prototypes replay

def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_T9_the_minimal_designs_prototype_still_measures_631_tokens_and_its_saved_hashes():
    assert sha256_file(ANALYSIS / 'design-minimal/proposed_diagnosis_guide.py') == 'dde3c9c2abaf503d79e7a1e12c40b28e5165b48354aff1814ac2bf676e3b2f02'
    saved_measurement = json.loads((ANALYSIS / 'design-minimal/guide-measurement.json').read_text())
    prototype = _load(ANALYSIS / 'design-minimal/proposed_diagnosis_guide.py', 'proposed_diagnosis_guide_prototype')
    assert hashlib.sha256(canonical_json(prototype.block(TASK_TEXT)).encode()).hexdigest() == saved_measurement['block_sha256']
    assert hashlib.sha256(canonical_json(prototype.declaration()).encode()).hexdigest() == saved_measurement['declaration_sha256']
    for row in saved_measurement['rows']:
        first = saved(row['diagnosis'])['turns'][0]['messages']
        guided = prototype.attach(json.loads(first[1]['content']), task_text=TASK_TEXT)
        after = input_token_bound([first[0], {'role': 'user', 'content': canonical_json(guided)}], MODEL)
        assert (row['first_turn_tokens_before'], after) == (FIRST_TOKENS[row['diagnosis']], row['first_turn_tokens_after'])
        assert after - row['first_turn_tokens_before'] == 631
    # The product's block is the prototype's with only the C6 sentence taken out of its checks_note (PM decisions), and
    # nothing else changed; that sentence is the whole token difference.
    ours, theirs = diagnosis_guide.block(TASK_TEXT), prototype.block(TASK_TEXT)
    assert C6_SENTENCE in theirs['checks_note'] and theirs['checks_note'].replace(C6_SENTENCE + ' ', '') == ours['checks_note'] == CHECKS_NOTE
    assert {**theirs, 'checks_note': ours['checks_note']} == ours
    assert 631 - GUIDE_TOKENS == 23


@pytest.mark.anyio
async def test_T9_the_integrity_prototypes_statuses_and_repair_messages_are_what_the_product_now_records_and_sends(tmp_path):
    assert sha256_file(ANALYSIS / 'designer-integrity/prototype_declared_semantics.py') == '3b06bfb2928937aa0ef9be24bc30dc950fdee93d671818d8794680a15e5dbdfd'
    results = json.loads((ANALYSIS / 'designer-integrity/prototype-results.json').read_text())['diagnoses']
    assert {name: row['sidecar']['proposal_status'] for name, row in results.items()} == {
        'v2d-dev5': 'VALID_REQUESTED', 'v2e-dev5': 'VALID_NO_REQUEST', 'v2f-dev5': 'VALID_REQUESTED',
        'v2g-dev5': 'INVALID_OUTPUT', 'v2g-dev6': 'VALID_REQUESTED'}
    outputs = saved_outputs()
    for name in NAMES:
        mechanic, provider, _, _ = real_mechanic(tmp_path, saved_raws(name), flag=True, label=name)
        wrapper = diagnosis_protocol.RecordingDiagnosisMechanic(mechanic, mechanic)
        context = context_of(name)
        ref, proposal, raws = await wrapper.diagnose(context)
        recorded = outputs[name]['recorded_diagnostic']
        diagnostic = SimpleNamespace(diagnostic_id=recorded['diagnostic_id'], proposed_kind=recorded['proposed_kind'], kind=recorded['kind'])
        experiments = [SimpleNamespace(intervention_id=e['intervention_id'], result=e['result'], trial_pairs=e['trial_pairs'],
                                       limitations=e['limitations']) for e in outputs[name]['intervention_experiments']]
        counter = SimpleNamespace(counterexample_id=saved(name)['counterexample_id'], target_invariant=context['target_invariant'])
        # Each saved complete trial pair is two fresh trials (the saved export keeps the pairs, not the trial objects).
        trials = [object() for e in experiments for pair in e.trial_pairs for _ in pair]
        record = diagnosis_protocol.build_record(SimpleNamespace(campaign_id=saved(name)['campaign_id']), counter, diagnostic,
                                                 SimpleNamespace(experiments=experiments, trials=trials), wrapper)
        sidecar = results[name]['sidecar']
        assert record['proposal_status'] == sidecar['proposal_status']
        assert record['recorded_proposed_kind_source'] == sidecar['recorded_proposed_kind_source']
        assert [a['validation_errors'] for a in record['attempts']] == [
            [dict(e, **({'max_characters': 600, 'your_characters': REPLAYED_LENGTH[name]} if e['type'] == 'string_too_long' else {}))
             for e in a['validation_errors']] for a in sidecar['attempts']]
        assert {k: record['last_raw_unvalidated'][k] for k in ('proposed_kind', 'requested_intervention_id')} == sidecar['last_raw_unvalidated']
        assert record['intervention_ran'] == bool(outputs[name]['intervention_experiments'])
        if 'repair_turn' in results[name]:
            assert json.loads(provider.requests[1][3]['content']) == results[name]['repair_turn']['proposed']
            assert input_token_bound(provider.requests[1], MODEL) == results[name]['repair_turn']['proposed_turn_tokens_without_block']


# =================================================================================================== fixer: review findings

class FailingRunner(Runner):
    """Every fresh intervention trial fails in the callback (run_interventions records CALLBACK_ERROR:RuntimeError)."""
    async def run(self, *args, **kwargs):
        self.calls.append(('failed',)); raise RuntimeError('offline fixture: the trial could not start')


@pytest.mark.anyio
@pytest.mark.parametrize('ending,trials,pairs,early_end,phrase', [
    ('preflight', 0, 0, 'PREFLIGHT_REJECTED', 'preflight rejected'),
    ('stop_before_any_trial', 0, 0, 'STOPPED', 'stopped'),
    ('callback_error', 0, 0, 'CALLBACK_ERROR:RuntimeError', 'a trial could not run'),
    ('stop_after_one_pair', 2, 1, 'STOPPED', 'stopped'),
    ('full', 6, 3, None, None),
])
async def test_fix_intervention_ran_means_a_fresh_trial_ran_and_the_statement_names_an_early_end(tmp_path, monkeypatch, ending, trials, pairs,
                                                                                                   early_end, phrase):
    """Review finding MEDIUM-1 / F3: a requested intervention that ran no fresh trial (preflight rejection, a Stop before the
    first trial, a callback error) must not be recorded as intervention_ran, and the statement must say why it ended early."""
    runner = FailingRunner('SUPPORTED') if ending == 'callback_error' else Runner('SUPPORTED')
    stop = {'stop_before_any_trial': lambda: True, 'stop_after_one_pair': lambda: len(runner.calls) >= 2}.get(ending)
    on = await diagnose(tmp_path, monkeypatch, answers=ANSWERS['valid_request'], mode='PREFLIGHT_REJECTED' if ending == 'preflight' else 'SUPPORTED',
                        flag=True, label='on', stop=stop, runner=runner)
    record = on.record
    assert record['proposal_status'] == 'VALID_REQUESTED' and record['intervention_experiment_recorded'] is True
    assert record['fresh_intervention_trials'] == len(on.run.trials) == trials
    assert record['intervention_ran'] is (trials > 0)
    row, = record['interventions']
    assert row['trial_pairs'] == pairs and row['early_end'] == early_end
    if early_end is None:
        assert row['result'] == 'SUPPORTED' and record['verdict'] == 'POLICY_GAP'
        assert 'after 3 of 3 trial pairs' in record['statement'] and 'ended early' not in record['statement']
    else:
        assert row['result'] == 'INCONCLUSIVE' and record['verdict'] == 'INCONCLUSIVE'
        assert early_end in record['statement'] and phrase in record['statement']
        assert f'after {pairs} of 3 trial pairs' in record['statement']
        if trials == 0:
            assert 'no fresh trial ran' in record['statement']
    # The rule text and its semantics hash name the definition, so a plan frozen with it says what intervention_ran means.
    assert 'ran any fresh trial' in diagnosis_protocol.RULE
    assert diagnosis_protocol.declaration()['semantics_hash'] == diagnosis_protocol.semantics_hash()
