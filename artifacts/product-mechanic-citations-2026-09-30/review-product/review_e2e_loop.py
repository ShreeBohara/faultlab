"""Reviewer check (2) ($0, offline): a scripted Learn campaign on a REAL saved plan.

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/review-product/review_e2e_loop.py OUT.json

Unlike the builder's loop tests, nothing about the rule is monkeypatched: the campaign is created from a real plan
(register_agent -> prepare_run_plan with discovery v4 history replay -> create), so citation_status.campaign_rule and
diagnosis.runtime_contract are the product's own. The REAL Explorer and REAL Mechanic build every request; only the
provider is scripted (it keeps every message list; no network). Episodes come from the suite's FakeRunner, the
reproducer is the suite's stub, and an evidence double writes a native adapter v2.1 report_submitted event per episode
(the first discovery source cites one token it was never shown, 'obs-9', to show an undecoded token end to end).

Scenarios:
  v2-diagnosis : real Diagnostician (Mechanic answers INCONCLUSIVE)          -> diagnosis requests
  v2-candidate : Diagnosis double (POLICY_GAP), challenge finds a violation  -> candidate x2 + challenge Explorer requests
  v1-candidate / reference-candidate : the same with native v1 / reference Actor plans -> no block anywhere (control)
Scratch stores live under /Users/shree/FaultLab_Scratch/review-product/e2e and are deleted.
"""
import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rguard  # noqa: E402,F401

import pytest  # noqa: E402
from app.contracts.models import canonical_json  # noqa: E402

SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-product/e2e')
MECH = 'deepseek-ai/DeepSeek-V4-Pro-0813'
V4 = 'faultlab-discovery/v4-history-replay'


class Provider:
    def __init__(self, explorer_model):
        self.requests = []; self.explorer_model = explorer_model; self.candidates = 0; self.challenges = 0
    def role_model(self, role): return MECH if role == 'mechanic' else self.explorer_model
    async def complete(self, messages, role=None, **kwargs):
        from app.providers.runtime import RuntimeGeneration
        from app.agents.explorer import CHALLENGER
        from app.agents.mechanic import PROMPTS
        self.requests.append({'role': role, 'messages': json.loads(canonical_json(messages))})
        system, context = messages[0]['content'], json.loads(messages[-1]['content'])
        if role == 'mechanic':
            if system == (PROMPTS / 'diagnosis.md').read_text():
                out = {'proposed_kind': 'INCONCLUSIVE', 'hypothesis': 'Offline reviewer fixture', 'evidence_ids': context['evidence_ids'][:1],
                       'requested_intervention_id': None}
            else:
                self.candidates += 1
                out = ({'candidate': {'parent_version': 'policy-v0', 'rules': [{'hook': 'before_confirmation', 'when': 'always',
                        'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]}, 'explanation': 'Offline reviewer fixture'}
                       if self.candidates == 1 else {'no_change_reason': 'No further supported repair'})
            return RuntimeGeneration(canonical_json(out), MECH, input_tokens=100, output_tokens=20)
        challenge = CHALLENGER in system
        if challenge: self.challenges += 1
        delay = 3 + self.challenges if challenge else 3
        seed = 100 + self.challenges if challenge else 1 + int(context.get('selection_index', 0))
        out = {'fault_spec': {'seed': seed, 'primitives': [{'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders',
               'occurrence': 1, 'parameters': {'completion_delay_ticks': delay, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}]},
               'hypothesis': 'Offline reviewer selection'}
        return RuntimeGeneration(canonical_json(out), self.explorer_model, input_tokens=100, output_tokens=20)


async def scenario(tmp, agent, part):
    import app.lab.learning as learning
    from app.config import Settings
    from app.contracts.models import Counterexample, content_hash
    from app.lab.budgets import CampaignLedger
    from app.lab.coordinator import LabCoordinator
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import prepare_run_plan, read_run_plan
    from app.lab import citation_status
    from test_discovery_v2_flow import EXPLORER_MODEL, request
    from test_evaluation import FakeRunner
    from test_counterexample_loop import RECIPE
    from test_loop_limits_mechanic_context import bundle
    from test_citation_status import report_event
    monkeypatch = pytest.MonkeyPatch()
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model=EXPLORER_MODEL, wandb_mechanic_model=MECH))
    try:
        registration = register_agent(owner.store, owner.settings, agent)
        prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration, discovery_protocol=V4))
        campaign = owner.create(prepared.campaign_request, run_plan=prepared)
        cid = campaign.campaign_id
        plan = read_run_plan(owner.store, campaign)['plan']
        owner.ledgers[cid] = CampaignLedger(owner.store, cid, owner.get(cid).caps)
        provider = Provider(EXPLORER_MODEL)
        runner = FakeRunner('gain'); runner.provider = provider; original = runner.run
        async def run(current, recipe, policy, **kwargs):
            trial = await original(current, recipe, policy, **kwargs)
            if kwargs.get('arm') == 'L' and kwargs.get('purpose') == 'challenge':
                trial.failed_checks = ['C3']; trial.outcome = 'VIOLATION'
            owner.store.put_record('trials', trial.episode_id, trial)
            if kwargs.get('purpose') == 'discovery':
                # As tests/lab/test_discovery_v2_flow.run does: the discovery search ledger reads these records.
                owner.store.put_record('episodes', trial.episode_id, {'campaign_id': current.campaign_id,
                    'configuration_hash': current.configuration_hash, 'policy_hash': policy.policy_hash, 'scenario_hash': trial.scenario_hash,
                    'split': 'development', 'experiment_purpose': 'discovery', 'study_id': current.campaign_id,
                    'evidence_context_id': current.campaign_id, 'selector_id': None,
                    'verdict': {'fault_executions': [{'triggered': True, 'reason': None} for _ in recipe.primitives]}})
            return trial
        runner.run = run
        first = {}
        class Evidence:
            async def get(self, episode_id, context, **kwargs):
                if not owner.store.events(episode_id)['events']:
                    if not first:
                        first['episode'] = episode_id
                        report_event(owner.store, episode_id, ['obs-1', 'obs-9'], ['obs-1', 'obs-2'], campaign_id=cid)
                    else:
                        report_event(owner.store, episode_id, ['obs-1', 'obs-2'], ['obs-1', 'obs-2'], campaign_id=cid)
                trial = owner.store.get_record('trials', episode_id) or {}
                return bundle(episode_id, ['SUCCEEDED', 'PENDING'], failed=tuple(trial.get('failed_checks') or ()))
        owner.evidence_gateway = Evidence()
        class Reproducer:
            def __init__(self, *args): pass
            async def source(self, campaign, source, recipe, policy, **kwargs):
                return Counterexample(counterexample_id='counter-' + source.episode_id[-12:], campaign_id=campaign.campaign_id,
                                      agent_registration_id=registration.registration_id, source_episode_id=source.episode_id,
                                      target_invariant='C3', scenario_hash=content_hash(recipe), configuration_hash=campaign.configuration_hash,
                                      report_ref=source.episode_id, verdict_ref='verdict-fixture', reproduced=True,
                                      target_violation_count=3, valid_count=3, attempted_count=3), [source]
            async def reduce(self, *args, **kwargs):
                return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION', model_dump=lambda **_: {'status': 'NO_REDUCTION'}),
                                       retained_recipe=RECIPE, trials=[])
        class Diagnosis:
            def __init__(self, *args): pass
            async def run(self, *args, **kwargs):
                return (SimpleNamespace(kind='POLICY_GAP', model_dump=lambda **_: {'kind': 'POLICY_GAP', 'provenance': 'offline_double'}),
                        SimpleNamespace(trials=[]))
        async def export(*args, **kwargs): return None
        monkeypatch.setattr(learning, 'Reproducer', Reproducer)
        monkeypatch.setattr(learning, 'export_incident', export)
        if part == 'candidate':
            monkeypatch.setattr(learning, 'Diagnostician', Diagnosis)
        error = None
        try:
            await learning.run_learning_cycle(owner, campaign, runner)
        except Exception as exc:  # recorded, not hidden
            error = f'{type(exc).__name__}: {exc}'
        state = owner.get(cid).state
        from app.agents.mechanic import PROMPTS
        from app.agents.explorer import CHALLENGER
        out = {'agent': agent, 'part': part, 'plan_agent': plan['agent'], 'plan_discovery': plan['discovery']['protocol'],
               'plan_declares_rule': 'mechanic_evidence' in plan, 'campaign_rule_real': citation_status.campaign_rule(owner.store, campaign) is not None,
               'final_state': state, 'error': error, 'undecoded_episode': first.get('episode'), 'requests': []}
        for r in provider.requests:
            system = r['messages'][0]['content']; ctx = json.loads(r['messages'][-1]['content'])
            if r['role'] == 'mechanic':
                kind = 'mechanic_diagnosis' if system == (PROMPTS / 'diagnosis.md').read_text() else 'mechanic_proposal'
            else:
                kind = 'explorer_challenge' if CHALLENGER in system else 'explorer_discovery'
            block = ctx.get(citation_status.BLOCK)
            listed = []
            for key in ('observations', 'development_evidence'):
                v = ctx.get(key)
                if isinstance(v, dict): listed += [row['episode_id'] for row in v.get('episodes', [])]
            for item in ctx.get('challenge_counterexamples') or []:
                listed += [row['episode_id'] for row in item['evidence']['episodes']]
            memory = ((ctx.get('runtime_contract') or {}).get('actor_contract') or {})
            memory = memory.get('memory') if isinstance(memory, dict) else None
            out['requests'].append({
                'kind': kind, 'has_block': block is not None,
                'block_episode_ids_equal_first_listing_order': (block is not None and [row['episode_id'] for row in block['episodes']] == list(dict.fromkeys(listed))),
                'block_rows': [(row['episode_id'] == first.get('episode'), row['cited'], row['decoded'], row['undecoded']) for row in (block or {}).get('episodes', [])],
                'memory_has_pointer': memory == citation_status.V2_MEMORY_WITH_CITATION_STATUS if memory else None,
                'memory_is_plain_v2': memory == citation_status.V2_MEMORY if memory else None,
                'memory_kind': None if memory is None else ('v2+pointer' if memory == citation_status.V2_MEMORY_WITH_CITATION_STATUS else
                                                             'v2' if memory == citation_status.V2_MEMORY else 'other'),
                'episodes_listed': len(dict.fromkeys(listed))})
        # The Explorer's own persisted selection record (the recording of a challenge request) carries the block too.
        sel = [row for row in owner.store.list_records('selections') if row.get('challenge')]
        out['challenge_selection_records_with_block'] = sum(1 for row in sel if citation_status.BLOCK in (row.get('context') or {}))
        out['challenge_selection_records'] = len(sel)
        return out
    finally:
        monkeypatch.undo()
        await owner.close()


async def main(out):
    if SCRATCH.exists(): shutil.rmtree(SCRATCH)
    results = []
    try:
        for agent, part in (('smolagents-v2', 'diagnosis'), ('smolagents-v2', 'candidate'), ('smolagents', 'candidate'),
                            ('reference', 'candidate'), ('smolagents', 'diagnosis')):
            tmp = SCRATCH / f'{agent}-{part}'; tmp.mkdir(parents=True)
            results.append(await scenario(tmp, agent, part))
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    summary = []
    for r in results:
        kinds = {}
        for q in r['requests']:
            k = kinds.setdefault(q['kind'], {'n': 0, 'with_block': 0, 'order_ok': 0, 'memory': {}})
            k['n'] += 1; k['with_block'] += q['has_block']; k['order_ok'] += q['block_episode_ids_equal_first_listing_order']
            k['memory'][str(q['memory_kind'])] = k['memory'].get(str(q['memory_kind']), 0) + 1
        undecoded_rows = sorted({(tuple(row[3]) if row[3] is not None else None, row[1], row[2]) for q in r['requests'] for row in q['block_rows'] if row[0]}, key=str)
        other_rows = sorted({(tuple(row[3]) if row[3] is not None else None, row[1], row[2]) for q in r['requests'] for row in q['block_rows'] if not row[0]}, key=str)
        summary.append({'agent': r['agent'], 'part': r['part'], 'plan_declares_rule': r['plan_declares_rule'], 'final_state': r['final_state'],
                        'error': r['error'], 'by_kind': kinds, 'undecoded_episode_rows(undecoded,cited,decoded)': undecoded_rows,
                        'other_rows(undecoded,cited,decoded)': other_rows,
                        'challenge_selection_records': r['challenge_selection_records'],
                        'challenge_selection_records_with_block': r['challenge_selection_records_with_block']})
    Path(out).write_text(json.dumps({'summary': summary, 'scratch_deleted': not SCRATCH.exists(), 'detail': results}, indent=1, default=str) + '\n')
    print(json.dumps({'summary': summary, 'scratch_deleted': not SCRATCH.exists()}, indent=1, default=str))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
