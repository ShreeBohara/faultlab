"""Integrity review ($0, offline, read-only): the builder's challenge reach rule against what the candidate's agent
actually called inside the saved live challenges.

Run from faultlab/backend with the project .venv, on SCRATCH COPIES outside the Desktop (never the saved stores):
  ../.venv/bin/python -B <this file> /Users/shree/FaultLab_Scratch/review-integrity/v2b.sqlite3 [more copies]

For each saved challenge it uses the repo's own app.lab.loop_limits.candidate_reach (the rule's basis) and
app.lab.loop_limits._call_targets (same service resolution), then lists, per pick:
  - the pick's fault targets and what loop_limits.decide would do (SELECTED / REFUSED_UNREACHED);
  - per arm, how often each fault target was called by the agent in that pick's own challenge episodes;
and, per challenge, the targets the candidate's agent called in ANY challenge episode but not in source validation
(targets the rule would refuse although the candidate's agent demonstrably reached them in this same challenge).
Nothing is written to any store; the copies are opened with ReadOnlyLabStore.
"""
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard  # noqa: E402,F401  (refuses .env and non-loopback sockets)

from app.contracts.models import FaultSpec, canonical_json  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402
from app.lab import loop_limits  # noqa: E402


def analyse(path):
    if '/FaultLab_Runs/' in path or 'Desktop' in path:
        raise SystemExit('Refusing: pass a scratch copy outside the saved run stores and outside the Desktop')
    store = ReadOnlyLabStore(path)
    calls_by_episode = {}
    for call in store.list_records('tool_calls'):
        calls_by_episode.setdefault(call.get('episode_id'), []).append(call)
    out = []
    for challenge in store.list_records('challenges'):
        campaign_id = store.get_record('challenge_campaigns', challenge['challenge_id'])['campaign_id']
        candidate = challenge['candidate_hash']
        reach = loop_limits.candidate_reach(store, campaign_id, candidate)
        session = loop_limits.ChallengeReachSession((campaign_id, candidate, challenge['incumbent_hash']))
        candidate_called_in_challenge = Counter()
        candidate_episodes = 0
        picks = []; ran = 0
        evaluations = [b for b in store.list_records('evaluations') if b['purpose'] == 'challenge'
                       and (b['candidate_hash'], b['incumbent_hash']) == (candidate, challenge['incumbent_hash'])]
        for index, ref in enumerate(challenge['selection_refs']):
            selection = store.get_record('selections', ref) or {}
            spec = (selection.get('output') or {}).get('fault_spec')
            if spec is None:
                picks.append({'selection_ref': ref, 'output': None}); continue
            recipe = FaultSpec.model_validate_json(canonical_json(spec))
            context = {'proposal_index': index, 'slot_request': 1}
            decision, kept = loop_limits.decide(reach, session, context, SimpleNamespace(fault_spec=recipe), None)
            targets = decision['targets']
            # Challenge batches are saved in the order their picks ran (challenge.py runs one batch per accepted pick).
            batch = evaluations[ran] if ran < len(evaluations) else None
            ran += 1
            per_arm = {}
            if batch is not None:
                for trial in batch['trials']:
                    episode_id = trial['episode_id']
                    intent_targets = loop_limits._call_targets(store, episode_id, calls_by_episode.get(episode_id, []))
                    agent_targets = Counter(t for caller, t in intent_targets if caller == 'actor')
                    arm = per_arm.setdefault(trial['arm'], {'episodes': 0, 'fault_triggered': 0, 'agent_called_each_target_in_episodes': Counter()})
                    arm['episodes'] += 1; arm['fault_triggered'] += bool(trial['fault_triggered'])
                    for target in targets:
                        if agent_targets.get(target): arm['agent_called_each_target_in_episodes'][target] += 1
                    if trial['arm'] == 'L' and trial['policy_hash'] == candidate:
                        candidate_episodes += 1
                        for target in set(agent_targets): candidate_called_in_challenge[target] += 1
            picks.append({'selection_ref': ref, 'kinds': [p.kind for p in recipe.primitives], 'targets': targets,
                          'rule_decision': decision['status'], 'unreached': decision['unreached'],
                          'per_arm': {k: {**v, 'agent_called_each_target_in_episodes': dict(v['agent_called_each_target_in_episodes'])} for k, v in per_arm.items()}})
        refused_but_reached = sorted(t for t in candidate_called_in_challenge if t not in reach['agent'])
        out.append({'store_copy': path, 'campaign_id': campaign_id, 'challenge_id': challenge['challenge_id'],
                    'status': challenge['status'], 'stopping_reason': challenge['stopping_reason'],
                    'rule_basis_agent_targets': reach['agent'], 'rule_basis_policy_only': reach['policy_only'],
                    'rule_basis_episode_count': len(reach['episode_ids']),
                    'candidate_arm_challenge_episodes': candidate_episodes,
                    'candidate_agent_targets_in_challenge_episode_counts': dict(candidate_called_in_challenge),
                    'targets_rule_would_refuse_but_candidate_agent_called_in_this_challenge': refused_but_reached,
                    'picks': picks})
    store.close()
    return out


if __name__ == '__main__':
    print(json.dumps([row for path in sys.argv[1:] for row in analyse(path)], indent=1, sort_keys=True))
