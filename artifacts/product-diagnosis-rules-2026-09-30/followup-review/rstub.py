"""Reviewer scratch-only pytest plugin (-p rstub): lets plan-building tests run WITHOUT opening audit/promotion.json.

run_plans._manifests() loads the development manifest (read normally) and, from the promotion manifest, only three
facts for the Compare mode's options block: its manifest_hash, case count and trials_per_case. Learn plans do not
record that block, and none of the reviewed assertions reads it. This plugin replaces only the promotion half with a
fixed dummy block; everything else is the product's own code. Used ONLY in the reviewer's scratch copy, never in the
real tree. An unmutated baseline with the stub must pass the same tests as the real-tree suite before any mutation
result is trusted.
"""


def pytest_configure(config):
    from app.lab import run_plans
    from app.lab.run_plans import StoreConflict, TASK, CASE_LABELS
    from app.referee.manifests import load_manifest
    from app.contracts.models import FaultSpec, canonical_json

    original = run_plans._manifests

    def _manifests():
        development = load_manifest('development')
        if (development.get('scope') != TASK or development.get('partition') != 'development'
                or development.get('access') != 'DEVELOPMENT_DIAGNOSTIC'
                or [case.get('case_id') for case in development['cases']] != list(CASE_LABELS)):
            raise StoreConflict('The reviewed development catalog is unavailable')
        for case in development['cases']:
            FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
        comparison = {'partition': 'promotion', 'manifest_hash': '0' * 64, 'case_count': 1, 'trials_per_case': 1}
        return development, comparison

    _manifests.__wrapped_original__ = original
    run_plans._manifests = _manifests
