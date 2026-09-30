"""Product review, history fireability ($0, offline): the saved native-v2b store, new plans, scripted campaigns.

Run from faultlab/backend:
    ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/review-product/review_scripted_campaigns.py OUT_DIR

Independent of the builder's scripts. What it does, on ONE scratch copy of
/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (read only through SQLite's backup API from a
mode=ro&immutable=1 connection; sha256 of the saved files recorded before and after):

  A. Plans. Registers native adapter v2 under the current runtime and creates, through the product path
     (prepare_run_plan + coordinator.create), new Learn plans with discovery v4, v3-history and v1. Records each plan's
     explorer_selection block (or its absence), the frozen table, and the Start plan check (validate_run_plan, which
     recomputes the history and the table). Every earlier saved plan must still read byte for byte, without the block.
  B. Scripted campaigns through the REAL learning loop (coordinator._execute -> run_learning_cycle) with the REAL Explorer
     (scripted provider), the real fireability Session, the real Challenger and PairedEvaluator. Doubles: the Actor
     runner (test_evaluation.FakeRunner; a lone status-read fault is made NOT to fire, like live), Weave evidence,
     reproduction, reduction, diagnosis (POLICY_GAP) and the Mechanic (one fixed candidate). The promotion stage is
     BLOCKED before it loads any case (review_harness.block_promotion), so no protected case is read.
       A1  new v4 plan: the challenge Explorer first picks the lone status read.
       A0  the same answers under a v4 plan saved without the rule (simulated with FIREABILITY_PROTOCOLS=() at creation).
       B1  new v4 plan, discovery only: refusals, re-plans, a refused re-plan, a duplicate, a mixed recipe, fine targets.
       B0  the same discovery answers under a v4 plan saved without the rule.
  The API (plan, search-attempts, experiments, evidence-wait) and the recording of every campaign are saved as JSON for
  the dashboard check. The scratch copy is KEPT (for the dashboard check) at SCRATCH and deleted by the caller later.
No provider, W&B, model or network call (review_guard refuses non-loopback sockets and counts them).
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402  (first)

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests' / 'lab'), str(BACKEND / 'tests')]

SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-product-fireability/lab')
EXPLORER_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
V4, V3, V1 = 'faultlab-discovery/v4-history-replay', 'faultlab-discovery/v3-history', 'faultlab-discovery/v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def saved_hashes():
    return {name: sha(SAVED.with_name(name)) for name in ('lab.sqlite3', 'lab.sqlite3-shm', 'lab.sqlite3-wal')}


def copy_read_only(source, target):
    import sqlite3
    src = sqlite3.connect(f'file:{source}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(str(target))
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()


def P(kind, tool, service, occurrence, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': parameters}


STATUS = lambda count=1: P('F4', 'get_operation_status', 'orders', 1, failure_count=count)   # the v2d/v2f lone pick
DELAYED = lambda ticks: P('F2', 'update_order', 'orders', 1, completion_delay_ticks=ticks, terminal_status='SUCCEEDED', failure_code=None)
CONFIRM = P('F4', 'send_confirmation', 'notifications', 1, failure_count=1)
SLOW = P('F1', 'update_order', 'orders', 1, response_delay_ms=2000)


def raw(*primitives, seed=1):
    from app.contracts.models import canonical_json
    return canonical_json({'fault_spec': {'seed': seed, 'primitives': list(primitives)}, 'hypothesis': 'Offline scripted review pick'})


def is_status(p):
    return (p.kind, p.target_service, p.target_tool) == ('F4', 'orders', 'get_operation_status')


class Scripted:
    """The Explorer's provider: answers from answer(context); keeps every context and system prompt."""
    def __init__(self, answer):
        self.answer = answer; self.contexts = []; self.systems = []
    def role_model(self, role): return EXPLORER_MODEL
    async def complete(self, messages, **kwargs):
        from app.providers.runtime import RuntimeGeneration
        context = json.loads(messages[-1]['content'])
        self.contexts.append(context); self.systems.append(messages[0]['content'])
        return RuntimeGeneration(self.answer(context), EXPLORER_MODEL, input_tokens=100, output_tokens=20)


class PromotionBlocked(Exception):
    """Raised instead of loading the protected promotion cases (the review never reads them)."""


def install_doubles(owner, monkeypatch_list, *, mechanic_candidate):
    import app.lab.learning as learning
    from app.contracts.models import CandidatePolicy, Counterexample, MechanicCandidate, MechanicNoChange, canonical_json, content_hash
    calls = {'mechanic': 0}
    real_load_cases = learning.load_cases
    def load_cases(name, *args, **kwargs):
        if name != 'development':
            raise PromotionBlocked(f'review harness: the {name} stage is blocked; no protected case is loaded')
        return real_load_cases(name, *args, **kwargs)
    class Reproducer:
        def __init__(self, *args): pass
        async def source(self, campaign, source, recipe, policy, **kwargs):
            return Counterexample(counterexample_id='counter-' + source.episode_id[-8:], campaign_id=campaign.campaign_id,
                                  agent_registration_id='orders-v1', source_episode_id=source.episode_id, target_invariant='C3',
                                  scenario_hash=content_hash(recipe), configuration_hash=campaign.configuration_hash,
                                  report_ref=source.episode_id, verdict_ref='verdict-fixture', reproduced=True,
                                  target_violation_count=3, valid_count=3, attempted_count=3), [source]
        async def reduce(self, campaign, counter, recipe, policy, **kwargs):
            return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION', model_dump=lambda **_: {'status': 'NO_REDUCTION'}),
                                   retained_recipe=recipe, trials=[])
    class Diagnosis:
        def __init__(self, *args): pass
        async def run(self, *args, **kwargs):
            return (SimpleNamespace(kind='POLICY_GAP', model_dump=lambda **_: {'kind': 'POLICY_GAP', 'provenance': 'offline_double'}),
                    SimpleNamespace(trials=[]))
    class Mechanic:
        def __init__(self, *args): self.lab_retry = None; self.metadata = None; self.trace = None
        async def propose(self, context, **kwargs):
            calls['mechanic'] += 1
            if mechanic_candidate and calls['mechanic'] == 1:
                candidate = CandidatePolicy.model_validate_json(canonical_json({'parent_version': 'policy-v0', 'rules': [
                    {'hook': 'before_confirmation', 'when': 'always', 'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]}))
                proposal = MechanicCandidate(candidate=candidate, explanation='Offline review fixture proposal')
            else:
                proposal = MechanicNoChange(no_change_reason='No further supported repair (offline review double)')
            from app.contracts.models import new_id
            return new_id('mechanic-review'), proposal, [proposal.model_dump_json()]   # unique per campaign (immutable records)
    async def export(*args, **kwargs): pass
    for name, value in [('Reproducer', Reproducer), ('Diagnostician', Diagnosis), ('Mechanic', Mechanic),
                        ('export_incident', export), ('load_cases', load_cases)]:
        monkeypatch_list.append((learning, name, getattr(learning, name)))
        setattr(learning, name, value)
    return calls


def restore(monkeypatch_list):
    while monkeypatch_list:
        module, name, value = monkeypatch_list.pop()
        setattr(module, name, value)


def run_campaign(owner, campaign, answer, *, mode, mechanic_candidate):
    """The real learning loop through coordinator._execute, with the doubles above; returns what it observed."""
    from app.lab.budgets import CampaignLedger
    from app.lab.run_plans import validate_run_plan
    from test_evaluation import FakeRunner
    ident = campaign.campaign_id
    start_check = validate_run_plan(owner.store, owner.settings, owner.get(ident))   # Start's plan check (history + table)
    ledger = CampaignLedger(owner.store, ident, owner.get(ident).caps)
    owner.ledgers[ident] = ledger
    class Evidence:
        async def get(self, episode_id, context, **kwargs):
            return SimpleNamespace(episode_id=episode_id, source='weave_verified', report=None, findings=[], observations=[])
    owner.evidence_gateway = Evidence()
    runner = FakeRunner(mode); provider = Scripted(answer); runner.provider = provider; original = runner.run
    async def persisted(current, recipe, policy, **kwargs):
        trial = await original(current, recipe, policy, **kwargs)
        purpose = kwargs.get('purpose') or 'discovery'
        # Like live runs v2d/v2f: a lone status-read fault does not fire (a healthy upgrade needs no status read).
        if recipe.primitives and all(is_status(p) for p in recipe.primitives):
            trial.fault_triggered = False
            if trial.outcome == 'VIOLATION': trial.outcome = 'COMPLETED'; trial.failed_checks = []
        owner.store.put_record('trials', trial.episode_id, trial)
        owner.store.put_record('episodes', trial.episode_id, {
            'episode_id': trial.episode_id, 'campaign_id': current.campaign_id, 'configuration_hash': current.configuration_hash,
            'policy_hash': policy.policy_hash, 'policy_version': policy.version, 'scenario_hash': trial.scenario_hash,
            'split': 'development', 'source_mode': 'live', 'lifecycle': trial.lifecycle, 'arm': kwargs['arm'],
            'experiment_purpose': purpose, 'study_id': current.campaign_id, 'evidence_context_id': current.campaign_id,
            'selector_id': None,
            'verdict': {'fault_executions': [{'triggered': trial.fault_triggered, 'reason': None if trial.fault_triggered else 'target_not_reached'}
                                             for _ in recipe.primitives]}})
        return trial
    runner.run = persisted
    patched = []
    calls = install_doubles(owner, patched, mechanic_candidate=mechanic_candidate)
    owner.runner = runner; owner.active_id = ident
    try:
        asyncio.run(owner._execute(ident, True))
    finally:
        restore(patched); owner.runner = None; owner.active_id = None
    return {'start_check_plan_hash': start_check['plan_hash'], 'provider': provider, 'runner': runner, 'ledger': ledger,
            'mechanic_calls': calls['mechanic']}


def selections_of(store, ident):
    rows = [r for r in store.list_records('selections') if (r.get('context') or {}).get('campaign_id') == ident]
    return rows


def api(owner, ident):
    import httpx
    from app.main import create_app
    async def fetch():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as client:
            out = {}
            for name, path in (('plan', f'/api/campaigns/{ident}/plan'), ('search_attempts', f'/api/campaigns/{ident}/search-attempts'),
                               ('experiments', f'/api/campaigns/{ident}/experiments'), ('evidence_wait', f'/api/campaigns/{ident}/evidence-wait'),
                               ('campaign', f'/api/campaigns/{ident}')):
                response = await client.get(path)
                out[name] = {'status': response.status_code, 'body': response.json()}
            return out
    return asyncio.run(fetch())


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    from app.config import Settings
    from app.contracts.models import content_hash
    from app.lab import fireability
    from app.lab.coordinator import LabCoordinator
    from app.lab.exports import development_recording
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import SavedRunPlan, prepare_run_plan, read_run_plan
    import app.lab.run_plans as run_plans
    from test_agent_history import plan_request
    report = {'saved_store': str(SAVED), 'saved_store_sha256_before': saved_hashes()}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / 'lab.sqlite3'
    for leftover in SCRATCH.glob('lab.sqlite3*'): leftover.unlink()
    copy_read_only(str(SAVED), target)
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model=EXPLORER_MODEL))
    try:
        store = owner.store
        old_plans = {p['campaign_id']: p for p in store.list_records('campaign_plans')}
        registration = register_agent(store, owner.settings, 'smolagents-v2')
        def new_plan(protocol, *, without_rule=False):
            saved = run_plans.FIREABILITY_PROTOCOLS
            if without_rule: run_plans.FIREABILITY_PROTOCOLS = ()
            try:
                prepared = prepare_run_plan(store, owner.settings, plan_request(owner, registration, discovery_protocol=protocol))
                campaign = owner.create(prepared.campaign_request, run_plan=prepared)
            finally:
                run_plans.FIREABILITY_PROTOCOLS = saved
            return campaign, read_run_plan(store, campaign)['plan']

        # ---------------------------------------------------------------- A. plans
        plans = {}
        for name, protocol in (('v4', V4), ('v3_history', V3), ('v1', V1)):
            campaign, plan = new_plan(protocol)
            plans[name] = {'campaign_id': campaign.campaign_id, 'discovery_protocol': plan['discovery']['protocol'],
                           'has_explorer_selection': 'explorer_selection' in plan,
                           'evidence_retry': {k: plan['evidence_retry'][k] for k in ('protocol', 'automatic_retries_per_wait', 'automatic_retries_per_campaign')},
                           'table': (plan.get('explorer_selection') or {}).get('table'),
                           'table_hash': (plan.get('explorer_selection') or {}).get('table_hash'),
                           'history_summary_hash': ((plan['discovery'].get('history') or {}).get('summary_hash')),
                           'history_verified_episodes': ((plan['discovery'].get('history') or {}).get('summary') or {}).get('verified_episodes')}
        v4 = plans['v4']
        report['A_plans'] = plans
        report['A_v3_and_v4_same_table'] = plans['v3_history']['table'] == plans['v4']['table']
        report['A_table_rows_v4'] = [(r['kind'], r['target_service'], r['target_tool'], r['verified_episodes'], r['fired_episodes'], r['status'])
                                     for r in v4['table']['rows']]
        report['A_refused_targets_v4'] = v4['table']['refused_targets']
        report['A_table_hash_recomputes'] = content_hash(v4['table']) == v4['table_hash']
        old_check = {}
        for ident, saved in old_plans.items():
            now = store.get_record('campaign_plans', ident)
            old_check[ident] = {'same_record': now == saved, 'has_block': 'explorer_selection' in now,
                                'model_roundtrip_identical': SavedRunPlan.model_validate(now).model_dump(mode='json') == now,
                                'read_status': read_run_plan(store, ident)['status'],
                                'evidence_retry_protocol': (now.get('evidence_retry') or {}).get('protocol'),
                                'discovery_protocol': (now.get('discovery') or {}).get('protocol'), 'mode': now.get('mode')}
        report['A_old_plans'] = old_check

        # ---------------------------------------------------------------- B. scripted campaigns
        # A1 / A0: challenge. The Explorer's challenge answers by proposal index; discovery answers are fine targets.
        challenge_answers = [raw(STATUS()), raw(DELAYED(1)), raw(CONFIRM), raw(SLOW), raw(DELAYED(3)), raw(DELAYED(4)), raw(DELAYED(5)), raw(DELAYED(6))]
        discovery_fine = [raw(DELAYED(2), seed=n) for n in range(20)]
        def challenge_answer(context):
            if context.get('purpose') == 'challenge':
                return challenge_answers[context['proposal_index']]
            return discovery_fine[context['selection_index']]
        results = {}
        for name, without_rule in (('A1_new_plan', False), ('A0_plan_without_rule', True)):
            campaign, plan = new_plan(V4, without_rule=without_rule)
            observed = run_campaign(owner, campaign, challenge_answer, mode='gain', mechanic_candidate=True)
            ident = campaign.campaign_id
            challenges = [store.get_record('challenges', r['challenge_id']) for r in store.list_records('challenge_campaigns') if r['campaign_id'] == ident]
            challenge_rows = []
            for challenge in challenges:
                for ref in challenge['selection_refs']:
                    selection = store.get_record('selections', ref)
                    spec = (selection.get('output') or {}).get('fault_spec') or {}
                    challenge_rows.append({'proposal_index': selection['context'].get('proposal_index'),
                                           'slot_request': selection['context'].get('slot_request'),
                                           'recipe': [f"{p['kind']} {p['target_service']}.{p['target_tool']}" for p in spec.get('primitives', [])],
                                           'fireability': (selection.get('fireability') or {}).get('status'),
                                           'ran': selection.get('selected_output') is not None})
            challenge_contexts = [c for c in observed['provider'].contexts if c.get('purpose') == 'challenge']
            results[name] = {
                'campaign_id': ident, 'plan_has_rule': 'explorer_selection' in plan, 'state': owner.get(ident).state,
                'terminal_reason': owner.get(ident).terminal_reason,
                'challenges': [{'status': c['status'], 'stopping_reason': c['stopping_reason'], 'schedules': len(c['schedule_hashes']),
                                'pairs': len(c['trial_pairs']), 'failed_checks': c['failed_checks'], 'selection_requests': len(c['selection_refs'])}
                               for c in challenges],
                'challenge_picks': challenge_rows,
                'challenge_requests_with_rule_keys': sum('history_fireability' in c for c in challenge_contexts),
                'challenge_requests': len(challenge_contexts),
                'challenge_replan_context': [{k: c.get(k) for k in ('proposal_index', 'slot_request', 'replan_of')} | {'has_slot_feedback': 'slot_feedback' in c}
                                             for c in challenge_contexts],
                'native_citation_status_in_challenge_requests': sum('native_citation_status' in c for c in challenge_contexts),
                'challenge_system_prompts_identical': len({s for s, c in zip(observed['provider'].systems, observed['provider'].contexts) if c.get('purpose') == 'challenge'}) <= 1,
                'ledger_used_calls': observed['ledger'].used_calls, 'mechanic_calls': observed['mechanic_calls'],
                'start_check_ok': observed['start_check_plan_hash'] == plan['plan_hash']}
            (out / f'{name}-api.json').write_text(json.dumps(api(owner, ident), indent=1, sort_keys=True, default=str))
            (out / f'{name}-recording.json').write_text(json.dumps(development_recording(store, ident), indent=1, sort_keys=True, default=str))

        # B1 / B0: discovery only (tie: no violation, so no candidate stage).
        B = {(2, 1): raw(STATUS()), (2, 2): raw(DELAYED(2)),
             (3, 1): raw(CONFIRM),
             (4, 1): raw(STATUS(2)), (4, 2): raw(STATUS(), seed=5),
             (5, 1): raw(DELAYED(2)),                                  # a duplicate of slot 2's re-plan (new plan)
             (6, 1): raw(DELAYED(3), STATUS()), (6, 2): raw(SLOW),     # a mixed recipe (per-target limit), then a fine re-plan
             (7, 1): raw(DELAYED(7))}
        def discovery_answer(context):
            return B[(context['selection_index'], context.get('slot_request', 1))]
        for name, without_rule in (('B1_new_plan', False), ('B0_plan_without_rule', True)):
            campaign, plan = new_plan(V4, without_rule=without_rule)
            observed = run_campaign(owner, campaign, discovery_answer, mode='tie', mechanic_candidate=False)
            ident = campaign.campaign_id
            rows = sorted(selections_of(store, ident), key=lambda r: (r['context']['selection_index'], r['context'].get('slot_request', 1)))
            episodes = [e for e in store.list_records('episodes') if e.get('campaign_id') == ident and e.get('experiment_purpose') == 'discovery']
            results[name] = {
                'campaign_id': ident, 'plan_has_rule': 'explorer_selection' in plan, 'state': owner.get(ident).state,
                'terminal_reason': owner.get(ident).terminal_reason,
                'slots': [{'slot': r['context']['selection_index'], 'slot_request': r['context'].get('slot_request'),
                           'provenance': r.get('provenance'), 'search_decision': (r.get('search_decision') or {}).get('status'),
                           'reason': (r.get('search_decision') or {}).get('reason'),
                           'fireability': (r.get('fireability') or {}).get('status'),
                           'refused_rows': [f"{t['kind']} {t['target_service']}.{t['target_tool']} {t['fired_share']}" for t in (r.get('fireability') or {}).get('refused_targets', [])],
                           'ran': r.get('selected_output') is not None} for r in rows],
                'unrequested_slots': [(s['selection_index'], s['status'], s['explorer_requests_used'], s['explorer_requests_max'])
                                      for s in store.list_records('explorer_selection_slots') if s['campaign_id'] == ident],
                'explorer_requests': len(observed['provider'].contexts), 'ledger_used_calls': observed['ledger'].used_calls,
                'actor_discovery_episodes': len(episodes),
                'requests_with_rule_keys': sum('history_fireability' in c for c in observed['provider'].contexts),
                'requests_with_slot_request_key': sum('slot_request' in c for c in observed['provider'].contexts),
                'start_check_ok': observed['start_check_plan_hash'] == plan['plan_hash']}
            if not without_rule:
                first = observed['provider'].contexts[0]
                results[name]['first_request_rule_text_is_RULE'] = first['history_fireability']['rule'] == fireability.RULE
                results[name]['first_request_rows_equal_plan_table'] = first['history_fireability']['rows'] == plan['explorer_selection']['table']['rows']
                results[name]['replan_contexts'] = [{'slot': c['selection_index'], 'replan_of_set': bool(c.get('replan_of')),
                                                     'slot_feedback_status': (c.get('slot_feedback') or {}).get('status')}
                                                    for c in observed['provider'].contexts if c.get('slot_request') == 2]
            (out / f'{name}-api.json').write_text(json.dumps(api(owner, ident), indent=1, sort_keys=True, default=str))
            (out / f'{name}-recording.json').write_text(json.dumps(development_recording(store, ident), indent=1, sort_keys=True, default=str))
        report['B_campaigns'] = results
        # Old campaigns: API reads still succeed on this store copy (the byte comparison with the backup code is separate).
        report['old_campaign_api_status'] = {ident: {k: v['status'] for k, v in api(owner, ident).items()} for ident in old_plans}
    finally:
        asyncio.run(owner.close())
    report['saved_store_sha256_after'] = saved_hashes()
    report['saved_store_unchanged'] = report['saved_store_sha256_before'] == report['saved_store_sha256_after']
    report['scratch_copy_kept_for_dashboard_check'] = str(target)
    report['guard'] = review_guard.counts()
    (out / 'scripted-campaigns.json').write_text(json.dumps(report, indent=1, sort_keys=True, default=str))
    print(json.dumps(report, indent=1, sort_keys=True, default=str)[:20000])


if __name__ == '__main__':
    main(sys.argv[1])
