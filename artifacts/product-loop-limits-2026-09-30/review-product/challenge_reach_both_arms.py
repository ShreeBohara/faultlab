"""Product reviewer, $0, read-only scratch copies: the challenge-pick rule on the two saved live challenges, through the
product's own code (app.lab.loop_limits.candidate_reach / decide / _call_targets), plus what each ARM actually called.

Why both arms: a challenge pair is complete only when its faults fire in BOTH arms (incumbent B0 and candidate L). The
rule looks only at the candidate arm's agent calls in source validation. This script shows, per saved challenge pick:
the rule's decision, which callers reached the target in each arm during source validation, and whether the fault fired
in each arm of the challenge itself.

Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-loop-limits-2026-09-30/review-product/challenge_reach_both_arms.py <v2d-copy> <v3-copy> <out.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rguard  # noqa: E402,F401

from app.contracts.models import ExplorerOutput  # noqa: E402
from app.lab import loop_limits  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402

CAMPAIGNS = {'v2d': 'campaign-ea66672d7a904bd8a011d6922790c963', 'v3': 'campaign-a2fbffe307f9434b9a753516cdb0afa8'}


def arm_calls(store, campaign_id, purpose, arm, policy_hash=None):
    episodes = [e['episode_id'] for e in store.list_records('episodes') if e.get('campaign_id') == campaign_id
                and e.get('experiment_purpose') == purpose and e.get('arm') == arm and (policy_hash is None or e.get('policy_hash') == policy_hash)]
    calls = {}
    for c in store.list_records('tool_calls'):
        if c.get('episode_id') in episodes: calls.setdefault(c['episode_id'], []).append(c)
    per = {}
    for e in episodes:
        per[e] = sorted({f'{caller}:{target}' for caller, target in loop_limits._call_targets(store, e, calls.get(e, []))})
    return per


def main():
    v2d, v3, out = sys.argv[1:4]
    for p in (v2d, v3):
        if 'Desktop' in p or '/FaultLab_Runs/' in p: raise SystemExit('scratch copies only')
    report = {}
    for label, path in (('v2d', v2d), ('v3', v3)):
        store = ReadOnlyLabStore(path); cid = CAMPAIGNS[label]
        challenge = next(c for c in store.list_records('challenges')
                         if any(x['challenge_id'] == c['challenge_id'] and x['campaign_id'] == cid for x in store.list_records('challenge_campaigns')))
        reach = loop_limits.candidate_reach(store, cid, challenge['candidate_hash'])
        sv_b0 = arm_calls(store, cid, 'source_validation', 'B0', challenge['incumbent_hash'])
        sv_l = arm_calls(store, cid, 'source_validation', 'L', challenge['candidate_hash'])
        session = loop_limits.ChallengeReachSession((cid, challenge['candidate_hash'], challenge['incumbent_hash']))
        picks = []
        trials = {t['episode_id']: t for t in store.list_records('trials')}
        pairs = challenge['trial_pairs']
        evals = [b for b in store.list_records('evaluations') if b['purpose'] == 'challenge' and b['candidate_hash'] == challenge['candidate_hash']]
        for index, ref in enumerate(challenge['selection_refs']):
            selection = store.get_record('selections', ref)
            output = ExplorerOutput.model_validate(selection['output'])
            decision, kept = loop_limits.decide(reach, session, {'proposal_index': index, 'slot_request': 1}, output, None)
            batch = evals[index] if index < len(evals) else None
            fired = None
            if batch:
                fired = {arm: [t['fault_triggered'] for t in batch['trials'] if t['arm'] == arm] for arm in ('B0', 'L')}
                calls = {}
                for c in store.list_records('tool_calls'):
                    if c.get('episode_id') in {t['episode_id'] for t in batch['trials']}: calls.setdefault(c['episode_id'], []).append(c)
                challenge_calls = {t['arm'] + ':' + t['episode_id'][-6:]: sorted({f'{a}:{b}' for a, b in loop_limits._call_targets(store, t['episode_id'], calls.get(t['episode_id'], []))}) for t in batch['trials']}
            else:
                challenge_calls = None
            picks.append({'selection': ref, 'targets': decision['targets'], 'rule_decision': decision['status'], 'unreached': decision['unreached'],
                          'fault_fired_in_challenge_by_arm': fired, 'challenge_calls': challenge_calls})
        report[label] = {'campaign_id': cid, 'challenge_status': challenge['status'], 'stopping_reason': challenge['stopping_reason'],
                         'rule_basis': reach, 'source_validation_calls_B0_incumbent': sv_b0, 'source_validation_calls_L_candidate': sv_l, 'picks': picks}
        store.close()
    Path(out).write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1)[:9000])


if __name__ == '__main__':
    main()
