"""Integrity review ($0, offline, scripted): can the candidate-reach rule turn a challenge that finds a counterexample
into one that passes?

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-loop-limits-2026-09-30/review-integrity/demo_rule2_hides_counterexample.py

It reuses the builder's own offline challenge harness (tests/lab/test_loop_limits_challenge_reach.py and
tests/lab/test_evaluation.py): a scripted Explorer, a fake runner and the real, unchanged app/lab/challenge.py and
app/agents/explorer.py. The candidate's agent called only get_order and update_order in source validation (as v2d's
candidate did). The fake runner makes the CANDIDATE arm fail check C4 whenever a schedule has a fault on
send_confirmation (a stand-in for "the candidate mishandles a confirmation failure after a healthy upgrade"); every
other schedule passes for the candidate. The same five scripted Explorer answers are replayed twice: with the rule
declared, and without it (a plan saved before it). Stores live in a scratch folder outside the Desktop, deleted at the end.
"""
import asyncio
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2] / 'backend'
sys.path[:0] = [str(HERE), str(BACKEND / 'tests' / 'lab')]
import guard  # noqa: E402,F401  (refuses the real .env and every non-loopback connection)

from app.contracts.models import TrialResult, Usage, content_hash, new_id  # noqa: E402
from app.lab.challenge import Challenger  # noqa: E402
from app.lab.evaluation import PairedEvaluator  # noqa: E402
from app.agents.explorer import Explorer  # noqa: E402
from app.lab.loop_limits import challenge_selection_declaration  # noqa: E402
import test_evaluation  # noqa: E402
from test_loop_limits_challenge_reach import CONFIRMATION, Scripted, delayed, pick, source_validation  # noqa: E402

SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-integrity/demo-rule2')


class ConfirmationSensitiveRunner(test_evaluation.FakeRunner):
    """Incumbent fails C3 everywhere (as FakeRunner); the candidate fails C4 only when send_confirmation is faulted."""
    async def run(self, campaign, recipe, policy, **kwargs):
        self.calls.append((campaign, recipe, policy, kwargs))
        candidate = kwargs['arm'] == 'L'
        confirmation_fault = any(p.target_tool == 'send_confirmation' for p in recipe.primitives)
        failed = (['C4'] if confirmation_fault else []) if candidate else ['C3']
        return TrialResult(episode_id=kwargs.get('episode_id') or new_id('e'), world_id=new_id('world'),
                           scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash, arm=kwargs['arm'],
                           trial_index=kwargs.get('trial_index', 0), lifecycle='COMPLETED',
                           outcome='VIOLATION' if failed else 'COMPLETED', failed_checks=failed,
                           fault_scheduled=bool(recipe.primitives), fault_triggered=bool(recipe.primitives),
                           usage=Usage(http_attempts=3 if candidate else 4))


async def run(tmp, declared):
    c, campaign, ledger, candidate, _ = test_evaluation.setup(tmp)
    runner = ConfirmationSensitiveRunner()
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, test_evaluation.cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    source_validation(c, campaign, candidate, agent_calls=('get_order', 'update_order'), policy_calls=('get_operation_status',))
    ledger.reserve('candidate', 528)
    answers = [pick(CONFIRMATION)] + [pick(delayed(n), seed=n) for n in range(1, 5)]
    explorer = Explorer(Scripted(answers), c.store, ledger)
    explorer.challenge_reach = challenge_selection_declaration() if declared else None
    before = len(runner.calls)
    result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    selections = [c.store.get_record('selections', ref) for ref in result.selection_refs]
    return {'declared': declared, 'status': result.status, 'reason': result.stopping_reason, 'failed_checks': result.failed_checks,
            'schedules_run': len(result.schedule_hashes), 'episodes_run': len(runner.calls) - before,
            'pick_statuses': [(s.get('challenge_reach') or {}).get('status', 'no rule') for s in selections]}


async def main():
    shutil.rmtree(SCRATCH, ignore_errors=True)
    try:
        for declared in (False, True):
            tmp = SCRATCH / ('declared' if declared else 'before'); tmp.mkdir(parents=True)
            print(await run(tmp, declared))
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        print('scratch removed:', not SCRATCH.exists())


asyncio.run(main())
