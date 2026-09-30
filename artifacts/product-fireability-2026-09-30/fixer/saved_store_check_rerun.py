"""Fixer rerun (the builder's script, only the scratch path changed) of history fireability on the saved native-v2b store ($0, offline): exact counts and every saved Explorer pick checked.

Run from faultlab/backend:
    ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/builder/saved_store_check.py <out.json>

The saved store /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 is read ONLY through SQLite's backup API from a
`mode=ro&immutable=1` connection into a scratch copy outside the synced Desktop (/Users/shree/FaultLab_Scratch/builder/
saved-check/); its sha256 and the -shm/-wal files' sha256 are recorded before and after. In the copy, native adapter v2 is
registered under the current runtime (same agent identity), and a new discovery v4 and a new v3-history Learn plan are
created through the product path (prepare_run_plan / create). Reported:
  * the frozen table of the new v4 plan (and that v3-history freezes the same table);
  * the verified history episodes behind the orders get_operation_status F4 row (ids, campaigns, recipes, fired flags);
  * for comparison, the same target over EVERY stored episode by policy and purpose (the rule never reads the
    candidate, challenge, reproduction or other rows; they are listed only to reconcile with the task statement's
    "2 of 14 starting-policy episodes and 1 of 9 candidate episodes");
  * every Explorer pick saved in the store (discovery and challenge), checked against the new table.
The scratch copy is deleted at the end. No provider, W&B, model or network call (guard.py refuses non-loopback sockets).
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))

SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer/saved-check/lab')
TARGET = ('F4', 'orders', 'get_operation_status')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def saved_hashes():
    return {name: sha(SAVED.with_name(name)) for name in ('lab.sqlite3', 'lab.sqlite3-shm', 'lab.sqlite3-wal')}


def main(out):
    from citation_status_saved import copy_read_only, remove_copy
    from app.config import Settings
    from app.contracts.models import ExplorerOutput, FaultSpec, canonical_json, content_hash
    from app.lab import agent_history, fireability
    from app.lab.coordinator import LabCoordinator
    from app.lab.operator_actions import register_agent
    from app.lab.reachability import readable_recipe
    from app.lab.run_plans import prepare_run_plan, read_run_plan
    from app.referee.manifests import load_manifest
    from test_agent_history import plan_request
    before = saved_hashes()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / 'lab.sqlite3'
    copy_read_only(str(SAVED), str(target))
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813'))
    report = {'saved_store': str(SAVED), 'saved_store_sha256_before': before}
    try:
        store = owner.store
        old_plans = {p['campaign_id'] for p in store.list_records('campaign_plans')}
        registration = register_agent(store, owner.settings, 'smolagents-v2')
        plans = {}
        for protocol in ('faultlab-discovery/v4-history-replay', 'faultlab-discovery/v3-history'):
            prepared = prepare_run_plan(store, owner.settings, plan_request(owner, registration, discovery_protocol=protocol))
            campaign = owner.create(prepared.campaign_request, run_plan=prepared)
            plans[protocol] = read_run_plan(store, campaign)['plan']
        v4 = plans['faultlab-discovery/v4-history-replay']
        history, block = v4['discovery']['history'], v4['explorer_selection']
        report['v4_plan'] = {'history_status': history['status'], 'verified_episodes': history['summary']['verified_episodes'],
                             'composition': history['summary']['composition'], 'record_cutoff': history['record_cutoff'],
                             'summary_hash': history['summary_hash'], 'table_hash': block['table_hash'], 'table': block['table'],
                             'replay_rows': [(r['history_row'], r['development_case_id'], r['violation_share']) for r in v4['discovery']['replay']['rows']]}
        report['v3_history_plan_same_table'] = plans['faultlab-discovery/v3-history']['explorer_selection']['table']['rows'] == block['table']['rows']
        report['old_plans_without_block'] = sorted(old_plans)
        report['old_plans_have_block'] = any('explorer_selection' in p for p in store.list_records('campaign_plans') if p['campaign_id'] in old_plans)
        # The verified history episodes behind the refused row.
        used = agent_history.used_episodes(store, identity=history['agent_identity'], policy_hash=history['policy_hash'], cutoff=history['record_cutoff'])
        behind = []
        for episode, recipe in used:
            for index, p in enumerate(recipe.primitives):
                if (p.kind, p.target_service, p.target_tool) == TARGET:
                    execution = ((episode.get('verdict') or {}).get('fault_executions') or [{}] * (index + 1))[index]
                    behind.append({'episode_id': episode['episode_id'], 'campaign_id': episode['campaign_id'], 'study_id': episode.get('study_id'),
                                   'recipe': readable_recipe(recipe.model_dump(mode='json')), 'triggered': execution.get('triggered'),
                                   'reason': execution.get('reason'), 'outcome': (episode.get('verdict') or {}).get('outcome')})
        report['history_episodes_behind_refused_row'] = behind
        # Reconciliation only (the rule never reads these): the same target over every stored episode by policy and purpose.
        recipes = {}
        for case in load_manifest('development')['cases']:
            recipes[content_hash(FaultSpec.model_validate_json(canonical_json(case['fault_spec'])))] = FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
        for selection in store.list_records('selections'):
            for key in ('output', 'selected_output'):
                spec = (selection.get(key) or {}).get('fault_spec')
                if spec:
                    recipe = FaultSpec.model_validate_json(canonical_json(spec)); recipes[content_hash(recipe)] = recipe
        for row in store.list_records('retained_recipes'):
            if row.get('retained_recipe'):
                recipe = FaultSpec.model_validate_json(canonical_json(row['retained_recipe'])); recipes[content_hash(recipe)] = recipe
        tally = {}
        for episode in store.list_records('episodes'):
            if episode['campaign_id'] not in old_plans:
                continue
            recipe = recipes.get(episode.get('scenario_hash'))
            if recipe is None or episode.get('lifecycle') != 'COMPLETED':
                continue
            executions = (episode.get('verdict') or {}).get('fault_executions') or []
            flags = [i < len(executions) and executions[i].get('triggered') is True for i, p in enumerate(recipe.primitives)
                     if (p.kind, p.target_service, p.target_tool) == TARGET]
            if not flags:
                continue
            key = f"{'policy-v0' if episode.get('policy_version') == 'policy-v0' else 'candidate'}/{episode['experiment_purpose']}/{episode.get('arm')}"
            item = tally.setdefault(key, {'episodes': 0, 'fired': 0})
            item['episodes'] += 1; item['fired'] += all(flags)
        report['every_stored_completed_episode_with_the_target_by_policy_purpose_arm'] = dict(sorted(tally.items()))
        report['totals'] = {'policy_v0_all_purposes': {'episodes': sum(v['episodes'] for k, v in tally.items() if k.startswith('policy-v0')),
                                                       'fired': sum(v['fired'] for k, v in tally.items() if k.startswith('policy-v0'))},
                            'candidate': {'episodes': sum(v['episodes'] for k, v in tally.items() if k.startswith('candidate')),
                                          'fired': sum(v['fired'] for k, v in tally.items() if k.startswith('candidate'))}}
        # Every saved Explorer pick, checked against the new plan's table.
        session = fireability.Session(block, discovery_requests_max=8)
        picks = []
        for selection in store.list_records('selections'):
            spec = (selection.get('output') or {}).get('fault_spec')
            if spec is None or selection.get('provenance') == 'history_replay' or selection['context'].get('campaign_id') not in old_plans:
                continue
            output = ExplorerOutput.model_validate({'fault_spec': spec, 'hypothesis': 'saved pick'})
            decision, kept = fireability.decide(session, {'selection_index': 0, 'proposal_index': 0, 'slot_request': 1}, output, None,
                                                challenge=bool(selection['challenge']), provenance='model')
            picks.append({'selection_id': selection['selection_id'], 'campaign_id': selection['context']['campaign_id'],
                          'challenge': bool(selection['challenge']), 'recipe': readable_recipe(spec), 'decision': decision['status'],
                          'recorded_status': (selection.get('search_decision') or {}).get('status') if not selection['challenge'] else None})
        report['saved_picks'] = picks
        report['saved_picks_summary'] = {
            'challenge_checked': sum(p['challenge'] for p in picks), 'challenge_refused': sum(p['challenge'] and p['decision'] != 'ALLOWED' for p in picks),
            'discovery_checked': sum(not p['challenge'] for p in picks), 'discovery_refused': sum((not p['challenge']) and p['decision'] != 'ALLOWED' for p in picks)}
    finally:
        asyncio.run(owner.close())
        report['scratch_copy_removed'] = remove_copy(str(target))
    report['saved_store_sha256_after'] = saved_hashes()
    report['saved_store_unchanged'] = report['saved_store_sha256_before'] == report['saved_store_sha256_after']
    Path(out).write_text(json.dumps(report, indent=2, sort_keys=True))
    print('table rows:')
    for row in report['v4_plan']['table']['rows']:
        print('  ', row['kind'], row['target_service'], row['target_tool'], row['fired_share'], row['status'])
    print('behind refused row:', [(b['campaign_id'][:17], b['recipe'], b['triggered'], b['reason']) for b in behind])
    print('all stored episodes with target:', report['every_stored_completed_episode_with_the_target_by_policy_purpose_arm'], report['totals'])
    print('saved picks:', report['saved_picks_summary'])
    print('refused saved picks:', [(p['campaign_id'][:17], 'challenge' if p['challenge'] else 'discovery', p['recipe']) for p in picks if p['decision'] != 'ALLOWED'])
    print('v3 same table:', report['v3_history_plan_same_table'], '| old plans have block:', report['old_plans_have_block'],
          '| saved store unchanged:', report['saved_store_unchanged'], '| scratch removed:', report['scratch_copy_removed'])


if __name__ == '__main__':
    main(sys.argv[1])
