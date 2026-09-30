"""Verifier-only stand-in for the protected promotion manifest, shaped for the dashboard's run-options validator
(64-hex manifest hash, positive case count). Used only by spot/api_contract_check_verifier.py in the scratch tree.
No file is read; the values are synthetic and say so."""
import hashlib
import app.referee.manifests as manifests

_real = manifests.load_manifest
STAND_IN_HASH = hashlib.sha256(b'verifier stand-in, not the real promotion manifest').hexdigest()


def load_manifest(name, *, directory=None):
    if name == 'promotion':
        return {'scope': 'orders.upgrade_then_confirm/v1', 'partition': 'promotion', 'manifest_hash': STAND_IN_HASH,
                'cases': [{'case_id': f'stand-in-{i}'} for i in range(8)], 'trials_per_case': 3}
    return _real(name, directory=directory)


manifests.load_manifest = load_manifest
