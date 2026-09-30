"""Integrity review ($0, offline, scripted): can the history fireability rule turn a challenge that finds a counterexample
into one that passes, and for which candidates?

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/review-integrity/demo_fireability_hides_counterexample.py

It reuses the builder's own offline challenge harness (tests/lab/test_history_fireability.py and tests/lab/test_evaluation.py):
a scripted Explorer, a fake runner, the real app/agents/explorer.py (with the rule) and the real, unchanged
app/lab/challenge.py. The rule's table is the REAL table a new v4 plan freezes on the saved native-v2b store
(builder/saved-store-check.json, v4_plan.table): F4 on orders get_operation_status is REFUSED (0 of 4).

Every generated guardrail in native-v2b adds the policy step read_current_operation = get_operation_status on orders
(policy_interpreter.py), run after an uncertain upgrade and before confirmation. The fake runner models one plausible
weak guardrail: when that status read is faulted while the upgrade is still pending (an F2 delay on update_order plus an
F4 on the orders status read), the CANDIDATE arm fails check C4; every other schedule passes for the candidate. Both
arms fire every scheduled fault (the saved store shows the starting-policy agent reads the orders status in 19 of 19
F2-delay discovery episodes, so this pick is fireable for the incumbent too). The incumbent fails C3 everywhere, as in
FakeRunner.

Scenario A: the Explorer's first pick is the COMBINED recipe (F2 delay 3 + F4 status read, failure_count 1).
Scenario B: the Explorer's first pick is the v2d/v2f LONE status read (F4 only); the fake runner then fires nothing in
            either arm (target_not_reached), as in the saved store.
Each is run with the rule (a new plan) and without it (a plan saved before it), same scripted answers.
Stores live in a scratch folder outside the Desktop and are deleted at the end.
"""
import asyncio
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2] / 'backend'
sys.path[:0] = [str(HERE), str(BACKEND / 'tests' / 'lab')]
import guard  # noqa: E402,F401  (refuses the real .env and every non-loopback connection)

from app.contracts.models import TrialResult, Usage, content_hash, new_id  # noqa: E402
from app.lab import fireability  # noqa: E402
from app.lab.challenge import Challenger  # noqa: E402
from app.lab.evaluation import PairedEvaluator  # noqa: E402
from app.agents.explorer import Explorer  # noqa: E402
import test_evaluation  # noqa: E402
from test_history_fireability import DELAYED, STATUS, CONFIRM, P, Scripted, raw  # noqa: E402

SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-integrity-fireability/demo')
SAVED = json.loads((HERE.parent / 'builder' / 'saved-store-check.json').read_text())
TABLE = SAVED['v4_plan']['table']
BLOCK = {**fireability.declaration(), 'table': TABLE, 'table_hash': content_hash(TABLE)}
assert BLOCK['table_hash'] == SAVED['v4_plan']['table_hash'], 'the table is not the one the builder froze'


def is_status(p):
    return p.kind == 'F4' and p.target_tool == 'get_operation_status' and p.target_service == 'orders'


def is_pending_upgrade(p):
    return p.kind == 'F2' and p.target_tool == 'update_order'


class StatusSensitiveRunner(test_evaluation.FakeRunner):
    """Candidate fails C4 only when its guardrail's status read is faulted during a pending upgrade."""
    async def run(self, campaign, recipe, policy, **kwargs):
        self.calls.append((campaign, recipe, policy, kwargs))
        candidate = kwargs['arm'] == 'L'
        prims = recipe.primitives
        lone_status = bool(prims) and all(is_status(p) for p in prims)
        triggered = bool(prims) and not lone_status          # a lone status read is never reached (healthy upgrade)
        weak_path = any(is_status(p) for p in prims) and any(is_pending_upgrade(p) for p in prims)
        failed = (['C4'] if weak_path else []) if candidate else ['C3']
        return TrialResult(episode_id=kwargs.get('episode_id') or new_id('e'), world_id=new_id('world'),
                           scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash, arm=kwargs['arm'],
                           trial_index=kwargs.get('trial_index', 0), lifecycle='COMPLETED',
                           outcome='VIOLATION' if failed else 'COMPLETED', failed_checks=failed,
                           fault_scheduled=bool(prims), fault_triggered=triggered,
                           usage=Usage(http_attempts=3 if candidate else 4))


COMBINED = [DELAYED(3), STATUS]
OTHERS = [raw(DELAYED(1), seed=11), raw(CONFIRM, seed=12), raw(DELAYED(2), seed=13),
          raw(P('F1', 'update_order', 'orders', 1, response_delay_ms=2000), seed=14), raw(DELAYED(4), seed=15)]


async def run(tmp, first, declared):
    c, campaign, ledger, candidate, _ = test_evaluation.setup(tmp)
    runner = StatusSensitiveRunner()
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, test_evaluation.cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    ledger.reserve('candidate', 528)
    answers = [first] + list(OTHERS)
    provider = Scripted(answers)
    explorer = Explorer(provider, c.store, ledger)
    explorer.fireability = fireability.Session(BLOCK, discovery_requests_max=8) if declared else None
    before = len(runner.calls)
    result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    selections = [c.store.get_record('selections', ref) for ref in result.selection_refs]
    return {'rule_declared': declared, 'status': result.status, 'reason': result.stopping_reason,
            'failed_checks': result.failed_checks, 'schedules_run': len(result.schedule_hashes),
            'episodes_run': len(runner.calls) - before, 'explorer_requests': len(provider.contexts),
            'pick_statuses': [(s.get('fireability') or {}).get('status', 'no rule') for s in selections]}


async def main():
    shutil.rmtree(SCRATCH, ignore_errors=True)
    out = {'table_rows': TABLE['rows'], 'table_hash': BLOCK['table_hash']}
    try:
        for name, first in (('A_combined_pending_upgrade_plus_status_read', raw(*COMBINED, seed=1)),
                            ('B_lone_status_read', raw(STATUS, seed=1))):
            out[name] = []
            for declared in (False, True):
                tmp = SCRATCH / name / ('rule' if declared else 'before'); tmp.mkdir(parents=True)
                out[name].append(await run(tmp, first, declared))
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        out['scratch_removed'] = not SCRATCH.exists()
    print(json.dumps(out, indent=1))


asyncio.run(main())
