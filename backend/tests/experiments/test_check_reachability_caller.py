"""The caller-model gate (scripts/experiments/check_reachability_caller.py).

Review finding (MEDIUM, September 28): caller v1 modelled a re-send after UNKNOWN that the
stored DeepSeek-V3.1 Actor almost never makes, and the builder's back-test could not see it
because nearly every stored fault is on attempt 1. The gate checks every modelled attempt,
not just the attempts where stored faults sat. No provider, network or model is used; stored
evidence is opened read-only with ``immutable=1``.
"""
import importlib.util
from pathlib import Path

import pytest

from app.lab import reachability
from app.lab.reachability import caller_model_for, label_recipe

ROOT = Path(__file__).resolve().parents[3]


def _gate():
    spec = importlib.util.spec_from_file_location('check_reachability_caller', ROOT / 'scripts/experiments/check_reachability_caller.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _gate()
SEND_TWICE = [{'kind': 'F4', 'target_tool': 'send_confirmation', 'target_service': 'notifications', 'occurrence': 1,
               'parameters': {'failure_count': 2}}]


def _stored(counts, times):
    return [{'store': 'synthetic', 'episode_id': f'e{i}', 'primitives': SEND_TWICE, 'counts': counts} for i in range(times)]


# What the stored Actor did after a confirmation failed on both attempts: it checked status
# three or four times and never sent the confirmation again.
BEHAVIOUR = (_stored({'get_order:orders': 1, 'update_order:orders': 1, 'send_confirmation:notifications': 2,
                      'get_operation_status:notifications': 4}, 12)
             + _stored({'get_order:orders': 1, 'update_order:orders': 1, 'send_confirmation:notifications': 2,
                        'get_operation_status:notifications': 3}, 6))


def _labeller():
    caller = caller_model_for('reference', [])
    return lambda primitives: label_recipe({'seed': 0, 'primitives': primitives}, caller)


def test_gate_thresholds():
    points = [{'recipe': 'r', 'target': 't', 'attempt': 1, 'episodes': 10, 'reached': 8, 'rate': 0.8},
              {'recipe': 'r', 'target': 't', 'attempt': 2, 'episodes': 9, 'reached': 0, 'rate': 0.0},
              {'recipe': 'r', 'target': 't', 'attempt': 3, 'episodes': 20, 'reached': 15, 'rate': 0.75}]
    result = gate.gate(points)
    assert result['checked_points'] == 2 and not result['passed']
    assert [p['attempt'] for p in result['failing_points']] == [3]  # 9 episodes: reported, not gated
    assert gate.gate(points[:2])['passed']
    assert not gate.gate(points[1:2])['passed']  # nothing checkable never passes


def test_installed_caller_passes_on_no_resend_behaviour():
    result = gate.gate(gate.reach_points(BEHAVIOUR, _labeller()))
    assert result['passed'] and result['checked_points'] == 7  # G1 U1 C1 C2 n1 n2 n3


def test_gate_catches_the_caller_v1_resend_assumption(monkeypatch):
    monkeypatch.setattr(reachability, '_resolve', reachability._resolve_with_resend)
    result = gate.gate(gate.reach_points(BEHAVIOUR, _labeller()))
    assert not result['passed']
    assert [(p['target'], p['attempt'], p['reached']) for p in result['failing_points']] == [
        ('send_confirmation:notifications', 3, 0)]


def test_gate_catches_polling_past_what_the_actor_did(monkeypatch):
    # Without the three-check cap the model would poll until its calls run out (four checks here).
    monkeypatch.setattr(reachability, 'UNKNOWN_STATUS_CHECKS', 99)
    fewer = BEHAVIOUR[12:] + BEHAVIOUR[:6]  # 6 of 12 made a fourth check: 50%
    result = gate.gate(gate.reach_points(fewer, _labeller()))
    assert [(p['target'], p['attempt']) for p in result['failing_points']] == [('get_operation_status:notifications', 4)]


@pytest.mark.parametrize('path', ['/x/heldout2/lab.sqlite3', '/x/audit/promotion.json', '/x/.env', '/x/final-audit/a.sqlite3'])
def test_protected_paths_are_never_opened(path):
    with pytest.raises(ValueError, match='protected'):
        gate.load_rows({'bad': Path(path)}, [])


STORE = gate.DEFAULT_STORES['main']


@pytest.mark.skipif(not STORE.exists(), reason='historical stores are local evidence, not in a source clone')
def test_gate_passes_on_the_stored_deepseek_v31_episodes():
    watched = [p for p in gate.DEFAULT_STORES.values() if p.exists()]
    watched += [Path(str(p) + suffix) for p in watched for suffix in ('-wal', '-shm') if Path(str(p) + suffix).exists()]
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in watched}
    result = gate.run()
    assert result['episodes'] > 3000 and result['checked_points'] >= 100
    assert result['passed'], result['failing_points']
    assert result['caller_model']['caller_id'] == 'reference-actor/policy-v0/v2'
    assert {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in watched} == before  # immutable reads
