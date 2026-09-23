#!/usr/bin/env python3
"""Phase 20 prep (c), $0 and read-only: distinct occurrence-1 schedule identities per fault kind.

Counts only. It prints no schedule, parameter value or identity digest from the store, so the
output cannot be used to pick heldout-2 parameters by looking at them. The heldout-2 generator
(Phase 22) does its own exclusion in code.

Sources:
  development   every stored development-split episode's recipe (records 'private_episode_inputs'
                joined on an episode whose split is 'development'; no other split's recipe is
                ever loaded, so no promotion, final-audit or portability content is read).
  7ab9368e      the completion manifest, rebuilt by app.lab.completion_study.case_manifest() and
                checked against its declared hash. It reads only the public development manifest.

Identity is app.lab.challenge.schedule_identity: scope plus the sorted primitives, seed ignored.
An "occurrence-1 schedule" is one whose every primitive has occurrence 1. Kind keys:
F1:<tool>, F2:<tool>:<terminal_status>, F3:<tool>, F4:<tool>; two-primitive schedules are keyed
by their sorted pair of kind keys; a schedule with no primitive is 'healthy'.

The heldout-2 section sizes each draw space named by the program's construction rule
(occurrence 1) and counts how many identities of that space already occur in the development
store and in 7ab9368e. The promotion partition is not read, so the count remaining after the
rule's promotion exclusion is not computed here.

Usage: python scripts/experiments/phase20_prep_schedule_identities.py [--store PATH] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from collections import defaultdict

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.contracts.models import FaultSpec, content_hash  # noqa: E402
from app.lab.challenge import schedule_identity  # noqa: E402

COMPLETION_MANIFEST_HASH = '7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483'
SERVICE = {'send_confirmation': 'notifications', 'update_order': 'orders', 'get_order': 'orders'}


def kind_key(primitive):
    key = f"{primitive['kind']}:{primitive['target_tool']}"
    if primitive['kind'] == 'F2':
        key += ':' + primitive['parameters']['terminal_status']
    return key


def schedule_key(spec):
    primitives = spec.model_dump(mode='json')['primitives']
    if not primitives:
        return 'healthy'
    return ' + '.join(sorted(kind_key(p) for p in primitives))


def occurrence_one(spec):
    return all(p.occurrence == 1 for p in spec.primitives)


def primitive(kind, tool, parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': SERVICE[tool], 'occurrence': 1,
            'parameters': parameters}


def heldout2_spaces():
    """The draw spaces named by the program's heldout-2 construction rule, occurrence 1.
    'Delayed refusal ... within reach' is not defined by the program; two readings are sized."""
    spaces = {
        'no_fault': [[]],
        'delayed_confirmation_response F1 send_confirmation 1500..3000 ms': [
            [primitive('F1', 'send_confirmation', {'response_delay_ms': ms})] for ms in range(1500, 3001)],
        'delayed_upgrade_success F2 SUCCEEDED d 1..4': [
            [primitive('F2', 'update_order', {'completion_delay_ticks': d, 'terminal_status': 'SUCCEEDED',
                                              'failure_code': None})] for d in range(1, 5)],
        'delayed_refusal F2 FAILED d 1..4 (one reading of "within reach")': [
            [primitive('F2', 'update_order', {'completion_delay_ticks': d, 'terminal_status': 'FAILED',
                                              'failure_code': 'UPGRADE_REJECTED'})] for d in range(1, 5)],
        'delayed_refusal F2 FAILED d 1..20 (FaultSpec range)': [
            [primitive('F2', 'update_order', {'completion_delay_ticks': d, 'terminal_status': 'FAILED',
                                              'failure_code': 'UPGRADE_REJECTED'})] for d in range(1, 21)],
        'stale_history F3 get_order versions_back 1..3': [
            [primitive('F3', 'get_order', {'versions_back': v})] for v in range(1, 4)],
        'transient_upgrade_failures F4 update_order count 2..4': [
            [primitive('F4', 'update_order', {'failure_count': c})] for c in range(2, 5)],
    }
    return {name: {schedule_identity(FaultSpec.model_validate({'seed': 0, 'primitives': p})) for p in items}
            for name, items in spaces.items()}


def development_specs(store):
    connection = sqlite3.connect(f'file:{store}?mode=ro', uri=True)
    try:
        query = ("SELECT p.payload FROM records e JOIN records p ON p.kind='private_episode_inputs' AND p.id=e.id "
                 "WHERE e.kind='episodes' AND json_extract(e.payload,'$.split')='development'")
        specs = [FaultSpec.model_validate(json.loads(payload)['recipe']) for (payload,) in connection.execute(query)]
        episodes = connection.execute("SELECT count(*) FROM records WHERE kind='episodes' AND "
                                      "json_extract(payload,'$.split')='development'").fetchone()[0]
    finally:
        connection.close()
    return specs, episodes


def manifest_specs():
    from app.lab.completion_study import case_manifest
    manifest = case_manifest()
    if content_hash(manifest) != COMPLETION_MANIFEST_HASH:
        raise SystemExit('case_manifest() no longer hashes to 7ab9368e...; refusing to count')
    return [FaultSpec.model_validate(case['fault_spec']) for case in manifest['cases']]


def count(specs):
    identities, occ1, episodes, episodes_occ1 = (defaultdict(set), defaultdict(set), defaultdict(int), defaultdict(int))
    for spec in specs:
        key = schedule_key(spec)
        identity = schedule_identity(spec)
        identities[key].add(identity)
        episodes[key] += 1
        if occurrence_one(spec):
            occ1[key].add(identity)
            episodes_occ1[key] += 1
    single = {k: {'distinct_identities': len(identities[k]), 'distinct_occurrence_1_identities': len(occ1[k]),
                  'records': episodes[k], 'records_occurrence_1': episodes_occ1[k]}
              for k in sorted(identities) if '+' not in k}
    pairs = {k: {'distinct_identities': len(identities[k]), 'distinct_occurrence_1_identities': len(occ1[k]),
                 'records': episodes[k], 'records_occurrence_1': episodes_occ1[k]}
             for k in sorted(identities) if '+' in k}
    by_kind = defaultdict(lambda: {'distinct_occurrence_1_identities': 0, 'distinct_identities': 0})
    for k, v in single.items():
        kind = k.split(':')[0]
        by_kind[kind]['distinct_occurrence_1_identities'] += v['distinct_occurrence_1_identities']
        by_kind[kind]['distinct_identities'] += v['distinct_identities']
    all_occ1 = set().union(*occ1.values()) if occ1 else set()
    return ({'single_primitive_by_kind': dict(sorted(by_kind.items())), 'single_primitive_by_kind_and_target': single,
             'two_primitive_by_kind_pair': pairs,
             'totals': {'records': len(specs), 'distinct_identities': len(set().union(*identities.values())),
                        'distinct_occurrence_1_identities': len(all_occ1)}},
            all_occ1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', type=pathlib.Path, default=ROOT / 'artifacts/lab.sqlite3')
    parser.add_argument('--out', type=pathlib.Path, help='also write the JSON result here')
    args = parser.parse_args(argv)
    dev_specs, dev_episodes = development_specs(args.store)
    development, dev_occ1 = count(dev_specs)
    manifest, manifest_occ1 = count(manifest_specs())
    heldout = {}
    for name, space in heldout2_spaces().items():
        exempt = name == 'no_fault'   # the rule exempts the no-fault case from novelty
        heldout[name] = {'space_size': len(space),
                         'in_development_store': len(space & dev_occ1),
                         'in_completion_manifest_7ab9368e': len(space & manifest_occ1),
                         'novelty_exempt': exempt,
                         'remaining_after_7ab9368e_exclusion': len(space) if exempt else len(space - manifest_occ1),
                         'remaining_after_promotion_exclusion': ('exempt' if exempt else
                                                                 'not computed (promotion partition not read)')}
    result = {'schema_version': 'faultlab-phase20-prep-identities/v1', 'counts_only': True,
              'identity': 'app.lab.challenge.schedule_identity (scope + sorted primitives; seed ignored)',
              'development_store': {'development_episodes': dev_episodes, 'with_recipe': len(dev_specs),
                                    **development},
              'completion_manifest_7ab9368e': manifest,
              'heldout2_draw_spaces_occurrence_1': heldout}
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
