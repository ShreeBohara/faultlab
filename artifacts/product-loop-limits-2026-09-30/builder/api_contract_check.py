"""Real backend API responses carrying both loop-limit rules, validated by the dashboard's own validators ($0, offline).

Why: a unit-test fixture can copy a wrong shape (the discovery v4 builder found one that way). This check builds, in a
scratch store outside the Desktop:
  * a new Learn plan (both rules) and a Learn plan as saved before them (neither), through prepare_run_plan/create;
  * real challenge selection records from the real Explorer + Challenger (scripted provider, FakeRunner), one refused
    pick and its re-plan, on the new campaign;
  * real Mechanic request-size records from loop_limits.fit_request: one COMPACTED, one SEARCH_ENDED;
then saves the real JSON of GET /api/run-options, /plan (both campaigns), /experiments (both) and /recording, and runs a
throw-away vitest spec in a scratch copy of the frontend that validates them with validateRunOptions,
validateCampaignPlan and validateExperiments. Both scratch folders are deleted afterwards.

Run from faultlab/backend:  ../.venv/bin/python ../artifacts/product-loop-limits-2026-09-30/builder/api_contract_check.py
"""
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401  (refuses .env and any non-loopback connection)
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))

SCRATCH = Path('/Users/shree/FaultLab_Scratch/loop-limits-builder/contract')
SPEC = """
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { validateCampaignPlan, validateRunOptions } from '../src/runPlans'
import { validateExperiments } from '../src/experiments'
const dir = process.env.LOOP_LIMITS_CONTRACT_DIR as string
const read = (name: string) => JSON.parse(readFileSync(`${dir}/${name}.json`, 'utf8'))
it('the dashboard accepts the real loop-limit API responses', () => {
  const ids = read('ids')
  const options = validateRunOptions(read('run-options'))
  expect(options.learn.mechanic_context?.protocol).toBe('faultlab-mechanic-context/v2-bounded')
  expect(options.learn.challenge_selection?.protocol).toBe('faultlab-challenge-selection/v2-candidate-reach')
  const plan = validateCampaignPlan(read('plan-new'), ids.new)
  expect(plan.plan?.mechanic_context?.compaction_target_tokens).toBe(28000)
  expect(plan.plan?.challenge_selection?.caller_counted).toBe('actor')
  const older = validateCampaignPlan(read('plan-old'), ids.old)
  expect(older.plan?.mechanic_context).toBeUndefined()
  expect(older.plan?.challenge_selection).toBeUndefined()
  const experiments = validateExperiments(read('experiments-new'))
  expect(experiments.challenge_reach?.map(row => row.status)).toEqual(ids.statuses)
  expect(experiments.mechanic_context?.map(row => row.outcome)).toEqual(['COMPACTED', 'SEARCH_ENDED'])
  const old = validateExperiments(read('experiments-old'))
  expect(old.challenge_reach).toBeUndefined()
  expect(old.mechanic_context).toBeUndefined()
})
"""


async def build():
    import httpx
    from app.config import Settings
    from app.lab.budgets import CampaignLedger
    from app.lab.challenge import Challenger
    from app.lab.coordinator import LabCoordinator
    from app.lab.diagnosis import summarize_evidence
    from app.lab.evaluation import PairedEvaluator
    from app.lab import loop_limits
    from app.agents.explorer import Explorer
    from app.contracts.models import CandidatePolicy, Counterexample, canonical_json, content_hash
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import prepare_run_plan
    from app.main import create_app
    from test_discovery_v2_flow import EXPLORER_MODEL, request
    from test_evaluation import FakeRunner, cases
    from test_loop_limits_challenge_reach import STATUS_ORDERS, Scripted, delayed, pick, source_validation
    from test_loop_limits_mechanic_context import bundle, trial

    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH / 'store'), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model=EXPLORER_MODEL))
    try:
        registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
        prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
        new = owner.create(prepared.campaign_request, run_plan=prepared)
        older_plan = prepare_run_plan(owner.store, owner.settings, request(owner, registration, order_id='order-older'))
        older_plan.plan.pop('mechanic_context'); older_plan.plan.pop('challenge_selection')
        old = owner.create(older_plan.campaign_request, run_plan=older_plan)
        # Real challenge selection records (the real Explorer and Challenger; scripted answers; FakeRunner episodes).
        campaign = owner.get(new.campaign_id); ledger = CampaignLedger(owner.store, campaign.campaign_id)
        candidate = owner.policies.proposal(CandidatePolicy.model_validate_json(canonical_json({'parent_version': 'policy-v0', 'rules': [
            {'hook': 'before_confirmation', 'when': 'always', 'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]})),
            parent='policy-v0', raw='contract-check fixture', episode_ids=[], author='manual')
        runner = FakeRunner(); evaluator = PairedEvaluator(owner.store, runner, ledger)
        source = await evaluator.run(campaign, cases(1), owner.policies.baseline(), candidate, purpose='source_validation')
        source_validation(owner, campaign, candidate, agent_calls=('get_order', 'update_order'), policy_calls=('get_operation_status',))
        ledger.reserve('candidate', 528)
        explorer = Explorer(Scripted([pick(STATUS_ORDERS), pick(delayed(1)), pick(delayed(2)), pick(delayed(3)), pick(delayed(4))]), owner.store, ledger)
        explorer.challenge_reach = loop_limits.challenge_selection_declaration()
        result = await Challenger(owner.store, explorer, evaluator).run(campaign, owner.policies.baseline(), candidate, source, reservation='candidate')
        owner.store.put_record('challenge_campaigns', result.challenge_id, {'campaign_id': campaign.campaign_id, 'challenge_id': result.challenge_id})
        # Real Mechanic request-size records (loop_limits.fit_request with the real admission count).
        counter = Counterexample(counterexample_id='counterexample-contract', campaign_id=campaign.campaign_id, agent_registration_id=registration.registration_id,
                                 source_episode_id='source', target_invariant='C3', scenario_hash=content_hash('r'), configuration_hash=campaign.configuration_hash,
                                 report_ref='source', verdict_ref='verdict-contract', reproduction_trial_ids=['repro-0'], reproduced=True)
        owner.store.put_record('counterexamples', counter.counterexample_id, counter)
        # Fourteen clean episodes whose rows all differ (distinct results and event lists), about 40,000 tokens in full.
        clean = [bundle(f'clean-{i}', ['SUCCEEDED', 'PENDING'] * 6, events=60 + 2 * i, note=f'clean-{i}-' + 'y' * 60) for i in range(14)]
        for index, item in enumerate(clean): trial(owner.store, item.episode_id, f'recipe-{index % 3}', 'L')
        failing = [bundle('source', ['PENDING'], failed=('C3',)), bundle('repro-0', ['PENDING'], failed=('C3',))]
        for item in failing: trial(owner.store, item.episode_id, 'source-recipe', 'B0', failed=('C3',))
        mechanic = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: 'deepseek-ai/DeepSeek-V4-Pro-0813'), metadata=None)
        context = {'campaign_id': campaign.campaign_id, 'development_evidence': summarize_evidence(failing + clean), 'candidate_history': [],
                   'challenge_counterexamples': [], 'source_validation_feedback': []}
        _, compacted_ref = loop_limits.fit_request(owner.store, mechanic, context, request_kind='mechanic_proposal', campaign_id=campaign.campaign_id,
                                                   counterexample=counter, extra={'source_context_id': 'context-contract', 'candidate_index': 1})
        # Twelve distinct failing episodes (always kept in full), so no stage can omit anything.
        big = {'observations': summarize_evidence([bundle(f'fail-{i}', ['PENDING'] * 18, failed=('C3',), events=60 + 3 * i, note=f'distinct-{i}-' + 'x' * 60)
                                                   for i in range(12)])}
        try:
            loop_limits.fit_request(owner.store, mechanic, big, request_kind='mechanic_diagnosis', campaign_id=campaign.campaign_id, counterexample=counter)
            raise SystemExit('expected the oversized diagnosis request not to fit')
        except loop_limits.MechanicContextUnfit:
            pass
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            responses = {'run-options': (await api.get('/api/run-options')).json(),
                         'plan-new': (await api.get(f'/api/campaigns/{new.campaign_id}/plan')).json(),
                         'plan-old': (await api.get(f'/api/campaigns/{old.campaign_id}/plan')).json(),
                         'experiments-new': (await api.get(f'/api/campaigns/{new.campaign_id}/experiments')).json(),
                         'experiments-old': (await api.get(f'/api/campaigns/{old.campaign_id}/experiments')).json(),
                         'recording-new': (await api.get(f'/api/campaigns/{new.campaign_id}/recording')).json()}
        statuses = [row['status'] for row in responses['experiments-new'].get('challenge_reach', [])]
        responses['ids'] = {'new': new.campaign_id, 'old': old.campaign_id, 'statuses': statuses}
        return responses, {'challenge_status': result.status, 'challenge_pairs': len(result.trial_pairs), 'statuses': statuses,
                           'compacted_record': owner.store.get_record('mechanic_context_records', compacted_ref)}
    finally:
        await owner.close()


def main():
    if SCRATCH.exists(): shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    try:
        responses, summary = asyncio.run(build())
        out = SCRATCH / 'responses'; out.mkdir()
        for name, value in responses.items(): (out / f'{name}.json').write_text(json.dumps(value))
        recording = responses['recording-new']
        print('challenge', summary['challenge_status'], summary['challenge_pairs'], 'pairs | pick statuses', summary['statuses'])
        record = summary['compacted_record']
        print('compacted record', record['full_request_tokens'], '->', record['compacted_request_tokens'], 'stages', record['stages_applied'])
        print('recording keys present:', sorted(k for k in ('mechanic_context_records', 'challenge_selection_rule') if k in recording),
              '| refused selections', recording['challenge_selection_rule']['refused_selection_ids'])
        print('experiments-old keys:', sorted(responses['experiments-old']))
        # A scratch copy of the frontend (node_modules linked) runs the throw-away spec against the saved responses.
        front = SCRATCH / 'frontend'
        shutil.copytree(ROOT / 'frontend', front, ignore=shutil.ignore_patterns('node_modules', 'dist', '.results', 'tests'))
        (front / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
        shutil.copytree(ROOT / 'contracts', SCRATCH / 'contracts')
        (front / 'tests').mkdir(); (front / 'tests' / 'contract.test.ts').write_text(SPEC)
        run = subprocess.run(['npx', 'vitest', 'run', 'tests/contract.test.ts'], cwd=front, capture_output=True, text=True,
                             env={**__import__('os').environ, 'LOOP_LIMITS_CONTRACT_DIR': str(out)})
        print(run.stdout[-900:]); print(run.stderr[-600:])
        print('vitest exit', run.returncode)
        return run.returncode
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        print('scratch removed:', not SCRATCH.exists())


if __name__ == '__main__':
    sys.exit(main())
