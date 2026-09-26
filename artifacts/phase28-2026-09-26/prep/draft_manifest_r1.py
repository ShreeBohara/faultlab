#!/usr/bin/env python3
"""Phase 28 freeze step F6: an independent stdlib mirror of the declared 'upgrade-v1' manifest (design section 4.1).

Stdlib only; never imports the app; reads only audit/development.json (the public development split).
First reproduces the reviewed default manifest (7ab9368e...) from the same file by the method of
case_manifest(), which proves the hashing method, then builds the upgrade-v1 mirror and prints its hash.
The design's illustrative value is cafe5757...; the pin is the backend builder's (manifest_hash.py), and
the two must be equal or the difference is explained and re-reviewed before the freeze is accepted.
Exit 0 only if the method check passes.

Usage (from the repository root): ./.venv/bin/python artifacts/phase28-<date>/prep/draft_manifest_r1.py [--root DIR]
(Stdlib JSON hashing gives the same value under any Python 3; the venv is named so that every prep step uses
one interpreter, review round 1.)
"""
import argparse
import copy
import hashlib
import json
import pathlib
import sys

OLD = '7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483'
DESIGN_VALUE = 'cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3'


def ch(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def spec(seed, primitives):
    return {'schema_version': 'faultlab/v1', 'scope': 'orders.upgrade_then_confirm/v1', 'seed': seed,
            'primitives': primitives}


def prim(kind, tool, service, parameters):
    return [{'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': 1, 'parameters': parameters}]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[3]))
    root = pathlib.Path(parser.parse_args(argv).root)
    dev = json.loads((root / 'audit/development.json').read_text(encoding='utf-8'))
    by = {c['case_id']: c for c in dev['cases']}
    healthy = copy.deepcopy(by['dev-1']); healthy.update(case_id='healthy', expected_outcome='COMPLETED')
    rejection = copy.deepcopy(by['dev-5'])
    rejection.update(case_id='terminal-upgrade-rejection', expected_outcome='CORRECTLY_REJECTED')

    # 1. Method check: the default manifest, rebuilt as case_manifest() builds it.
    source = copy.deepcopy(by['dev-6']); source.update(case_id='notification-2', expected_outcome='COMPLETED')
    old_cases = [healthy, source]
    for count in (1, 3, 18):
        case = copy.deepcopy(source)
        case.update(case_id=f'notification-{count}', name=f'notification_transient_{count}',
                    expected_outcome='SAFE_UNRESOLVED' if count == 18 else 'COMPLETED')
        case['fault_spec']['seed'] = 600 + count
        case['fault_spec']['primitives'][0]['parameters']['failure_count'] = count
        old_cases.append(case)
    lost_n = copy.deepcopy(source)
    lost_n.update(case_id='lost-notification-response', name='lost_notification_response',
                  fault_spec=spec(620, prim('F1', 'send_confirmation', 'notifications', {'response_delay_ms': 1500})))
    old_cases += [lost_n, rejection]
    old = {'schema_version': 'faultlab-completion-study/v1', 'source_manifest_hash': dev['manifest_hash'],
           'cases': old_cases, 'source_case_id': 'notification-2', 'control_case_id': 'healthy', 'repeats': 3,
           'validation_feedback_forbidden': True, 'ordinary_policy_accepted': False}
    method_ok = ch(old) == OLD

    # 2. The declared upgrade-v1 mirror.
    def transient(count, expected):
        case = copy.deepcopy(by['dev-6'])
        case.update(case_id=f'upgrade-{count}', name=f'upgrade_transient_{count}', expected_outcome=expected,
                    fault_spec=spec(700 + count, prim('F4', 'update_order', 'orders', {'failure_count': count})))
        return case
    delayed = copy.deepcopy(by['dev-3']); delayed.update(case_id='delayed-upgrade', expected_outcome='COMPLETED')
    lost_u = copy.deepcopy(by['dev-2']); lost_u.update(case_id='lost-upgrade-response', expected_outcome='COMPLETED')
    cases = [healthy, transient(3, 'COMPLETED'), transient(2, 'COMPLETED'), delayed, transient(18, 'SAFE_UNRESOLVED'),
             lost_u, rejection]
    manifest = {'schema_version': 'faultlab-completion-study/v1', 'source_manifest_hash': dev['manifest_hash'],
                'cases': cases, 'source_case_id': 'upgrade-3', 'control_case_id': 'healthy', 'repeats': 3,
                'validation_feedback_forbidden': True, 'ordinary_policy_accepted': False}
    print(json.dumps({'method_reproduces_7ab9368e': method_ok, 'upgrade_v1_mirror_hash': ch(manifest),
                      'equals_design_value': ch(manifest) == DESIGN_VALUE,
                      'cases': [c['case_id'] for c in cases]}, indent=1))
    return 0 if method_ok else 1


if __name__ == '__main__':
    sys.exit(main())
