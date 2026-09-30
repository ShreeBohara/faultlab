"""Verifier-only pytest plugin for SCRATCH runs: serve a synthetic stand-in for the protected promotion manifest.

The verifier may not read audit/promotion.json (and the scratch tree does not contain it). run_plans._manifests() needs
only its scope, partition, hash, case count and trials per case to freeze a plan's compare section, so this stand-in
answers load_manifest('promotion') without touching any file. Every other manifest is loaded normally. Never used in the
product tree or in scripts/test.sh.
"""
import app.referee.manifests as manifests

_real = manifests.load_manifest
STAND_IN = {'scope': 'orders.upgrade_then_confirm/v1', 'partition': 'promotion', 'manifest_hash': 'verifier-stand-in-not-the-real-manifest',
            'cases': [], 'trials_per_case': 3}


def load_manifest(name, *, directory=None):
    if name == 'promotion':
        return dict(STAND_IN, cases=[])
    return _real(name, directory=directory)


manifests.load_manifest = load_manifest
