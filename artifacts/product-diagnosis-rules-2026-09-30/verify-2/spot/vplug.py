"""Verifier-2 scratch-only pytest plugin (-p vplug). (1) Imports the verifier guard first (refuses non-loopback network,
.env, audit/promotion.json, audit/final-audit*.json and heldout2 opens). (2) Lets plan-building tests run WITHOUT the
promotion manifest (absent from the scratch trees): run_plans._manifests keeps every development-manifest check and
replaces only the promotion half with a fixed dummy comparison block (manifest hash, case count, trials per case), which
Learn plans do not record. Written independently of the reviewer's rstub.py (same idea). Never used in the real tree."""
import vguard  # noqa: F401


def pytest_configure(config):
    from app.lab import run_plans
    from app.lab.run_plans import StoreConflict, TASK, CASE_LABELS
    from app.referee.manifests import load_manifest
    from app.contracts.models import FaultSpec, canonical_json

    def _manifests():
        development = load_manifest('development')
        if (development.get('scope') != TASK or development.get('partition') != 'development'
                or development.get('access') != 'DEVELOPMENT_DIAGNOSTIC'
                or [case.get('case_id') for case in development['cases']] != list(CASE_LABELS)):
            raise StoreConflict('The reviewed development catalog is unavailable')
        for case in development['cases']:
            expected = {'standard-v1': 1, 'history-v1': 4}.get(case.get('fixture_id'))
            recipe = FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
            if expected is None or case.get('expected_version') != expected:
                raise StoreConflict('Development case fixture identity is inconsistent')
            if any(p.kind == 'F3' and p.parameters.versions_back >= expected for p in recipe.primitives):
                raise StoreConflict('Development case requires unavailable order history')
        return development, {'partition': 'promotion', 'manifest_hash': '0' * 64, 'case_count': 1, 'trials_per_case': 1}

    run_plans._manifests = _manifests
