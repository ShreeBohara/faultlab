"""Review check 4 ($0, offline): the probe harness, beyond the builder's tests.

* every planned request is the saved bytes or exactly one declared change, re-derived here from the pinned inputs;
* the Rule 1 repair request equals the one the real Mechanic sent in review check 2's replay (same saved answer);
* a scripted "live" run (main(provider_factory=...), valid declaration, pytest temporary folder) sends exactly the planned
  messages in schedule order, charges every call on the ledger before sending, writes only under --out;
* a provider that answers with another model stops the run after one call; a cap of $6.98 still admits the 140 planned
  calls but no retry;
* the scoring shows how many DISTINCT answers each request/arm cell got (review finding: at temperature 0 the ten repeats
  may be identical, and scoring.json does not report it).
"""
import hashlib
import importlib.util
import json
import pathlib
from collections import Counter

import pytest

from app.contracts.models import canonical_json, content_hash
from app.providers.runtime import RuntimeGeneration

ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'scripts/experiments/diagnosis_probe.py'
INPUTS = ROOT / 'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'


def load():
    spec = importlib.util.spec_from_file_location('diagnosis_probe_review', SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


probe = load()


@pytest.fixture(scope='module')
def built():
    return probe.build_plan()


class Scripted:
    """Deterministic answers (the same bytes for every repeat, as temperature 0 might give)."""
    def __init__(self, model=MODEL): self.sent = []; self.model = model; self.closed = False
    async def complete(self, messages, *, role, max_output_tokens, timeout_seconds):
        self.sent.append((messages, role, max_output_tokens, timeout_seconds))
        context = json.loads(messages[1]['content'])
        guided = 'diagnosis_guide' in context
        hypothesis = ('The report cites evidence labels that were never shown.' if not guided
                      else 'The agent confirmed after a FAILED upgrade receipt (C3).')
        answer = {'proposed_kind': 'CONTRACT_EVIDENCE_GAP', 'hypothesis': hypothesis, 'evidence_ids': context['evidence_ids'][:1],
                  'requested_intervention_id': context['intervention_ids'][0]}
        return RuntimeGeneration(canonical_json(answer), self.model, input_tokens=9000, output_tokens=100)
    async def close(self): self.closed = True


def declaration(tmp_path, plan, out, **changes):
    value = probe.declaration_template(plan, str(pathlib.Path(out).resolve()))
    value.update(approved_by='Review test only (not an approval)',
                 preconditions={'ledger_checked': True, 'dashboard_closed': True, 'no_other_paid_run': True}, **changes)
    path = tmp_path / 'DECLARATION.json'; path.write_text(json.dumps(value, indent=1))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_request_is_the_saved_bytes_or_one_declared_change(built):
    plan, messages = built
    assert len(messages) == 14 and plan['counts']['total_calls'] == 140
    for key, value in messages.items():
        name, arm = key.split('/')
        saved = json.loads((INPUTS / f'{name}-diagnosis-request.json').read_text())
        first = saved['turns'][0]['messages']
        if arm == 'CONTROL':
            assert value == first
        elif arm == 'GUIDE':
            assert value[0] == first[0]
            a, b = json.loads(first[1]['content']), json.loads(value[1]['content'])
            assert set(b) - set(a) == {'diagnosis_guide'} and all(canonical_json(a[k]) == canonical_json(b[k]) for k in a)
        elif arm == 'REPAIR_TODAY':
            assert value == saved['turns'][1]['messages']
        else:
            assert value[:3] == saved['turns'][1]['messages'][:3]
            assert value[3]['role'] == 'user' and value[3]['content'] != saved['turns'][1]['messages'][3]['content']
        assert plan['requests'][key]['messages_sha256'] == content_hash(value)


def test_the_rule_1_repair_request_equals_the_replayed_real_mechanics(built):
    _, messages = built
    replay = json.loads((ROOT / 'artifacts/product-diagnosis-rules-2026-09-30/review-product/replay-saved-diagnoses.json').read_text())
    for name in ('v2f-dev5', 'v2g-dev5'):
        assert json.loads(messages[f'{name}/REPAIR_RULE1'][3]['content']) == replay['diagnoses'][name]['rule_on_repair_message']


def test_a_scripted_live_run_sends_the_planned_messages_in_order_and_writes_only_under_out(built, tmp_path):
    plan, messages = built
    out = tmp_path / 'live'
    path, digest = declaration(tmp_path, plan, out)
    provider = Scripted()
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=lambda: provider) == 0
    assert [m for m, *_ in provider.sent] == [messages[c['request_key']] for c in plan['schedule']]
    assert {tuple(rest) for _, *rest in provider.sent} == {('mechanic', 2000, 20)} and provider.closed
    assert sorted(p.name for p in tmp_path.iterdir()) == ['DECLARATION.json', 'live']
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['ledger']['charged_calls'] == 140 and manifest['ledger']['charged_dollar_upper_bound'] == pytest.approx(6.9776)
    scoring = json.loads((out / 'scoring.json').read_text())
    distinct = Counter()
    for row in scoring['rows']:
        if row.get('delivered'): distinct[row['request_key']] += 0
    per_cell = {}
    for row in scoring['rows']:
        per_cell.setdefault(row['request_key'], set()).add(row.get('hypothesis'))
    # With deterministic answers every cell has ONE distinct hypothesis, yet P1/P2/P4 read as 40-of-40 / 10-of-10 counts.
    assert {k: len(v) for k, v in per_cell.items()} == {k: 1 for k in per_cell}
    assert not any('distinct' in key for key in json.dumps({k: scoring[k] for k in ('P1', 'P2', 'P3', 'P4')}).split('"'))
    assert scoring['P2']['status'] == 'PASS' and scoring['P4']['status'] == 'PASS'


def test_a_different_served_model_stops_after_one_call(built, tmp_path):
    plan, messages = built
    out = tmp_path / 'live'
    path, digest = declaration(tmp_path, plan, out)
    provider = Scripted(model='deepseek-ai/DeepSeek-V3.1')
    assert probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=lambda: provider) == 1
    manifest = json.loads((out / 'manifest.json').read_text())
    assert len(provider.sent) == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'SERVED_MODEL_DIFFERS'


@pytest.mark.anyio
async def test_a_cap_just_above_the_planned_calls_admits_them_and_no_retry(built, tmp_path):
    plan, messages = built
    manifest = await probe.execute(plan, messages, tmp_path / 'live', Scripted(), spend_cap=6.98)
    assert manifest['status'] == 'COMPLETED' and manifest['retry_calls_allowed_by_cap'] == 0
    assert manifest['ledger']['charged_calls'] == 140 and manifest['ledger']['charged_dollar_upper_bound'] <= 6.98


@pytest.fixture
def anyio_backend(): return 'asyncio'
