#!/usr/bin/env python3
"""Phase 28 freeze step F6: the backend builder's 'upgrade-v1' manifest hash, and the upgrade-3 fault spec.

$0; imports only app.lab.completion_study and app.contracts.models; loads no settings and no .env,
contacts nothing. Prints content_hash(build_case_manifest('upgrade-v1')), the default manifest's hash
(must stay 7ab9368e...), and the upgrade-3 fault spec that Phase 28a's requests must have used.

Usage (from the repository root): ./.venv/bin/python artifacts/phase28-<date>/prep/manifest_hash.py [--root DIR]
"""
import argparse
import json
import pathlib
import sys

sys.dont_write_bytecode = True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[3]))
    root = pathlib.Path(parser.parse_args(argv).root)
    sys.path.insert(0, str(root / 'backend'))
    from app.contracts.models import content_hash
    from app.lab.completion_study import build_case_manifest, case_manifest
    manifest = build_case_manifest('upgrade-v1')
    source = next(c for c in manifest['cases'] if c['case_id'] == manifest['source_case_id'])
    print(json.dumps({'upgrade_v1_manifest_hash': content_hash(manifest),
                      'default_manifest_hash': content_hash(case_manifest()),
                      'cases': [c['case_id'] for c in manifest['cases']],
                      'source_case_id': manifest['source_case_id'], 'control_case_id': manifest['control_case_id'],
                      'upgrade_3_fault_spec': source['fault_spec']}, indent=1, sort_keys=True))
    return 0 if content_hash(case_manifest()) == '7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483' else 1


if __name__ == '__main__':
    sys.exit(main())
