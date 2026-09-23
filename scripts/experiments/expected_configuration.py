"""Compute the frozen configuration hash a backend launched with SETTINGS will report.

Uses the backend's own code (frozen_configuration and the same caps coordinator.create
builds), so the value is exactly what POST /api/campaigns returns for a live-v1 campaign
when the backend runs this checkout with this environment. Prints only non-secret fields:
the frozen configuration itself holds no credentials (it is stored in the lab database).

Usage: python scripts/experiments/expected_configuration.py SETTINGS.json
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    overrides = json.loads(pathlib.Path(sys.argv[1]).read_text())
    # Non-empty values only, exactly as the Phase 17 launch and the runner apply them.
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    from app.config import Settings
    from app.contracts.models import CampaignBudget, content_hash
    from app.lab.configuration import frozen_configuration
    settings = Settings.from_env()
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap, tokens=settings.faultlab_token_cap,
                          dollars=float(settings.faultlab_dollar_cap))
    frozen = frozen_configuration(settings, caps, 'live-v1')
    print(json.dumps({'configuration_hash': content_hash(frozen),
                      'models': frozen['models'],
                      'per_call_dollar_upper_bound': {r: frozen['pricing'][r]['per_call_dollar_upper_bound']
                                                      for r in ('actor', 'explorer', 'mechanic')},
                      'campaign_budget': frozen['campaign_budget'],
                      'mechanic_temperature': frozen['model_settings_by_role']['mechanic'].get('temperature'),
                      'algorithm_hash': frozen['algorithm_hash'], 'runtime_hash': frozen['runtime_hash']}, indent=1))


if __name__ == '__main__':
    main()
