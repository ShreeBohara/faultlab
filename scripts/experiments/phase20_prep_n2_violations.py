#!/usr/bin/env python3
"""Phase 20 prep (e), $0 and read-only: v4 baseline violations in the notification-2 family.

The program (docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md, Phase 20 step (e)) notes that the
notification-2 family "has 247 v4 baseline episodes with 16 violations, so it cannot supply a
3 of 3 source". This script recounts that from the store, under stated definitions, and also
checks it empirically: did any 3-trial baseline group of this schedule ever fail the same
invariant 3 of 3?

Definitions (all declared here, none tuned):
  family    development-split episodes whose recipe is exactly the notification-2 schedule:
            one primitive, F4 send_confirmation/notifications, occurrence 1, failure_count 2
            (identity by app.lab.challenge.schedule_identity, so the seed is ignored).
  baseline  trial policy_hash == bafdc14f... (the empty policy-v0), whatever the arm label.
  v4        at least one actor_output event of the episode carries
            actor_context_protocol == faultlab-actor-context/v4-indexed-evidence.
  violation trial outcome VIOLATION; failed checks are tallied separately.

Only development-split private inputs are read (the join filters on the episode's split), so
no promotion, final-audit or portability recipe is ever loaded. The store is opened read-only.

Usage: python scripts/experiments/phase20_prep_n2_violations.py [--store PATH] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sqlite3
import sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.contracts.models import FaultSpec  # noqa: E402
from app.lab.challenge import schedule_identity  # noqa: E402

BASELINE_POLICY_HASH = 'bafdc14f280cd47441baf69006e8ca55885ca0349667f2695f57e40b3b8926fb'
V4 = 'faultlab-actor-context/v4-indexed-evidence'
NOTIFICATION_2 = FaultSpec.model_validate({'seed': 0, 'primitives': [{
    'kind': 'F4', 'target_tool': 'send_confirmation', 'target_service': 'notifications', 'occurrence': 1,
    'parameters': {'failure_count': 2}}]})
FAMILY_IDENTITY = schedule_identity(NOTIFICATION_2)
PROGRAM_CLAIM = {'v4_baseline_episodes': 247, 'violations': 16}


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return None
    p = k / n
    denominator = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, (centre - half) / denominator), 6), round(min(1.0, (centre + half) / denominator), 6)]


def rows(store):
    connection = sqlite3.connect(f'file:{store}?mode=ro', uri=True)
    try:
        query = ("SELECT e.id, e.payload, t.payload, p.payload FROM records e "
                 "JOIN records t ON t.kind='trials' AND t.id=e.id "
                 "JOIN records p ON p.kind='private_episode_inputs' AND p.id=e.id "
                 "WHERE e.kind='episodes' AND json_extract(e.payload,'$.split')='development'")
        family = []
        for episode_id, episode, trial, inputs in connection.execute(query):
            recipe = FaultSpec.model_validate(json.loads(inputs)['recipe'])
            if schedule_identity(recipe) != FAMILY_IDENTITY:
                continue
            family.append((episode_id, json.loads(episode), json.loads(trial)))
        protocols = defaultdict(set)
        for episode_id, _, _ in family:
            for (value,) in connection.execute(
                    "SELECT json_extract(payload,'$.payload.actor_context_protocol') FROM events "
                    "WHERE episode_id=? AND json_extract(payload,'$.type')='actor_output'", (episode_id,)):
                protocols[episode_id].add(value or 'none-recorded')
        studies = {}
        for (payload,) in connection.execute("SELECT payload FROM records WHERE kind='completion_studies'"):
            study = json.loads(payload)
            for slot in study.get('slots') or []:
                if slot.get('episode_id'):
                    studies[slot['episode_id']] = (study.get('study_id'), slot.get('stage'), slot.get('case_id'),
                                                   study.get('actor_context_protocol'))
    finally:
        connection.close()
    return family, protocols, studies


def summarise(family, protocols, studies):
    baseline = [(eid, e, t) for eid, e, t in family if t.get('policy_hash') == BASELINE_POLICY_HASH]
    v4 = [(eid, e, t) for eid, e, t in baseline if V4 in protocols.get(eid, ())]
    mixed = sum(1 for eid, _, _ in baseline if V4 in protocols.get(eid, ()) and len(protocols[eid]) > 1)

    def block(items):
        lifecycle = Counter(t.get('lifecycle') for _, _, t in items)
        outcome = Counter(t.get('outcome') for _, _, t in items)
        checks = Counter(c for _, _, t in items for c in t.get('failed_checks') or [])
        untriggered = sum(1 for _, _, t in items if t.get('fault_scheduled') and not t.get('fault_triggered'))
        valid = [t for _, _, t in items if t.get('lifecycle') == 'COMPLETED' and t.get('outcome') not in (None, 'LAB_ERROR')
                 and (not t.get('fault_scheduled') or t.get('fault_triggered'))]
        valid_violations = sum(t.get('outcome') == 'VIOLATION' for t in valid)
        return {'episodes': len(items), 'violations': outcome.get('VIOLATION', 0), 'by_lifecycle': dict(lifecycle),
                'by_outcome': dict(outcome), 'failed_check_tally': dict(sorted(checks.items())),
                'untriggered': untriggered, 'valid_triggered_completed_lifecycle': len(valid),
                'violations_among_valid': valid_violations,
                'violation_rate_valid': round(valid_violations / len(valid), 6) if valid else None,
                'violation_rate_valid_wilson95': wilson(valid_violations, len(valid)),
                'by_model': dict(Counter(e.get('model') for _, e, _ in items)),
                'by_day': dict(sorted(Counter((e.get('started_at') or '')[:10] for _, e, _ in items).items()))}

    # Empirical source check: every 3-trial baseline group of this schedule inside one study stage.
    groups = defaultdict(list)
    for eid, e, t in v4:
        key = studies.get(eid)
        if key is not None:
            groups[key[:3]].append(t)
    triples = [g for g in groups.values() if len(g) == 3]
    shared = []
    for g in triples:
        valid = [t for t in g if t.get('lifecycle') == 'COMPLETED' and t.get('fault_triggered')]
        common = set.intersection(*(set(t.get('failed_checks') or []) for t in g)) if len(valid) == 3 else set()
        shared.append(len(common) > 0)
    max_in_group = max((sum(t.get('outcome') == 'VIOLATION' for t in g) for g in groups.values()), default=0)
    upper = wilson(block(v4)['violations_among_valid'], block(v4)['valid_triggered_completed_lifecycle'])
    return {
        'family_schedule_identity': FAMILY_IDENTITY,
        'definitions': {'family': 'development episodes whose recipe identity equals notification-2 (seed ignored)',
                        'baseline': f'trial policy_hash == {BASELINE_POLICY_HASH}',
                        'v4': f'an actor_output event carries {V4}', 'violation': 'trial outcome VIOLATION'},
        'family_all_policies_episodes': len(family),
        'baseline_all_contexts': block(baseline),
        'baseline_v4': block(v4),
        'baseline_v4_episodes_with_mixed_context_labels': mixed,
        'baseline_v4_in_completion_studies': sum(1 for eid, _, _ in v4 if eid in studies),
        'baseline_v4_not_in_completion_studies': sum(1 for eid, _, _ in v4 if eid not in studies),
        'empirical_source_check': {
            'three_trial_baseline_groups': len(triples),
            'groups_with_any_size': len(groups),
            'max_violations_in_one_group': max_in_group,
            'groups_failing_one_invariant_3_of_3': sum(shared)},
        'chance_of_3_of_3_if_independent': {
            'at_point_rate': (round(block(v4)['violation_rate_valid'] ** 3, 8)
                              if block(v4)['violation_rate_valid'] is not None else None),
            'at_wilson_upper': round(upper[1] ** 3, 8) if upper else None},
        'program_claim': PROGRAM_CLAIM,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', type=pathlib.Path, default=ROOT / 'artifacts/lab.sqlite3')
    parser.add_argument('--out', type=pathlib.Path, help='also write the JSON result here')
    args = parser.parse_args(argv)
    result = summarise(*rows(args.store))
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
