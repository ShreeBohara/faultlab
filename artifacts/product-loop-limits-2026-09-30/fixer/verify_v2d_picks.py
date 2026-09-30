"""Fixer ($0, offline, read-only): independent check of the review claims about live run v2d's challenge picks.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-loop-limits-2026-09-30/fixer/verify_v2d_picks.py

Copies the saved native-v2b store (opened file:...?mode=ro&immutable=1) to a scratch folder outside the Desktop, reads
campaign ea66672d's challenge picks and, for every challenge episode, whether the fault fired and which tool/service
pairs the agent itself (caller "actor") and the candidate policy (other callers) called. Also prints the candidate
policy's rules and what the build's candidate-reach rule allowed. Deletes the copy at the end. Prints JSON.
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

from app.lab.storage import ReadOnlyLabStore  # noqa: E402
from app.lab import loop_limits  # noqa: E402
from app.lab.reachability import readable_recipe  # noqa: E402

SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer-loop-limits/verify-v2d')
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'


def main():
    shutil.rmtree(SCRATCH, ignore_errors=True); SCRATCH.mkdir(parents=True)
    copy = SCRATCH / 'v2d.sqlite3'
    source = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); target = sqlite3.connect(copy)
    try:
        source.backup(target); target.execute('PRAGMA journal_mode=DELETE')
    finally:
        target.close(); source.close()
    out = {}
    try:
        store = ReadOnlyLabStore(copy)
        try:
            qualification = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == V2D)
            candidate_hash = qualification['candidate_hash']
            out['candidate_rules'] = qualification['candidate'].get('rules')
            challenge = store.get_record('challenges', qualification['challenge_ref'])
            out['challenge'] = {k: challenge.get(k) for k in ('status', 'stopping_reason', 'failed_checks')}
            trials = {}
            for batch in store.list_records('evaluations'):
                if batch['purpose'] == 'challenge' and batch['candidate_hash'] == candidate_hash:
                    for t in batch['trials']:
                        trials[t['episode_id']] = t
            calls_by_episode = {}
            for call in store.list_records('tool_calls'):
                if call.get('episode_id') in trials:
                    calls_by_episode.setdefault(call['episode_id'], []).append(call)
            reach = loop_limits.candidate_reach(store, V2D, candidate_hash)
            out['build_rule_basis'] = reach
            picks = []
            for number, ref in enumerate(challenge['selection_refs'], 1):
                selection = store.get_record('selections', ref)
                spec = (selection.get('output') or {}).get('fault_spec')
                scenario = None
                episodes = []
                for episode_id, t in trials.items():
                    # Match a trial to its pick by the recorded scenario hash of the pick's batch.
                    episodes.append((episode_id, t))
                picks.append({'selection_id': ref, 'recipe': readable_recipe(spec) if spec else None, 'fault_spec': spec})
            # Group trials by scenario hash, in the order their batches were saved.
            by_scenario = {}
            for episode_id, t in trials.items():
                by_scenario.setdefault(t['scenario_hash'], []).append((episode_id, t))
            groups = []
            for scenario_hash, rows in by_scenario.items():
                arms = {}
                for episode_id, t in rows:
                    targets = loop_limits._call_targets(store, episode_id, calls_by_episode.get(episode_id, []))
                    agent = sorted({target for caller, target in targets if caller == 'actor'})
                    policy = sorted({target for caller, target in targets if caller != 'actor'})
                    status_polls = sum(1 for caller, target in targets if caller == 'actor' and target.startswith('get_operation_status:orders'))
                    arms.setdefault(t['arm'], []).append({'episode_id': episode_id, 'fault_triggered': t['fault_triggered'],
                                                          'failed_checks': t['failed_checks'], 'agent_targets': agent,
                                                          'policy_targets': policy, 'agent_orders_status_attempts': status_polls})
                groups.append({'scenario_hash': scenario_hash, 'arms': arms})
            out['picks'] = picks
            out['episodes_by_scenario'] = groups
            # Which of the grammar's targets the build's rule would refuse for this candidate.
            grammar = ['get_order:orders', 'update_order:orders', 'get_operation_status:orders', 'send_confirmation:notifications',
                       'get_operation_status:notifications']
            out['targets_refused_by_build_rule'] = [g for g in grammar if g not in reach['agent']]
        finally:
            store.close()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        out['scratch_removed'] = not SCRATCH.exists()
    print(json.dumps(out, indent=1, sort_keys=True))


main()
