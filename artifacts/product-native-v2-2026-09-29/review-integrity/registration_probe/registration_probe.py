"""Integrity reviewer: register native adapter v1 (and v2 where it exists) in an in-memory store on ROOT.
Offline: explicit Settings (no .env read; an audit hook refuses any .env open), no provider, no network.

Usage: python registration_probe.py ROOT OUT_JSON
"""
import json
import os
import sys
from pathlib import Path

ROOT, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()


def _refuse_env(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        try:
            path = os.fsdecode(os.fspath(args[0]))
        except TypeError:
            return
        if os.path.basename(path) == '.env':
            raise PermissionError('probe refuses every .env open')


sys.addaudithook(_refuse_env)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['WANDB_ERROR_REPORTING'] = 'false'
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import Settings  # noqa: E402
from app.contracts.models import CampaignBudget, content_hash  # noqa: E402
from app.lab.configuration import frozen_configuration  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from app.integrations import registry as reg  # noqa: E402

assert Path(reg.__file__).resolve().is_relative_to(ROOT)
MODEL = 'openai/gpt-oss-120b'
source = frozen_configuration(Settings(wandb_model=MODEL), CampaignBudget(), 'live-v1')
out = {'registry_file': reg.__file__}
store = LabStore(':memory:')
registry = reg.AgentRegistry(store)
target_v1 = reg.freeze_target_configuration(source, MODEL)
v1 = registry.register_smolagents(target_v1)
out['v1'] = v1.model_dump(mode='json')
out['v1_target_minus_runtime_fingerprints'] = {k: v for k, v in target_v1.items()
                                               if k not in ('runtime_hash', 'algorithm_hash', 'adapter_hash', 'tree_lab')}
if hasattr(reg, 'NATIVE_V2'):
    target_v2 = reg.freeze_target_configuration(source, MODEL, reg.NATIVE_V2)
    v2 = registry.register_smolagents(target_v2, reg.NATIVE_V2)
    out['v2'] = v2.model_dump(mode='json')
    out['v2_target_diff_keys_vs_v1'] = sorted(k for k in set(target_v1) | set(target_v2) if target_v1.get(k) != target_v2.get(k))
    from app.lab.agent_history import target_identity
    i1, i2 = target_identity(v1, target_v1), target_identity(v2, target_v2)
    out['history_identity_v1'] = i1
    out['history_identity_v2'] = i2
    out['history_identity_diff_keys'] = sorted(k for k in set(i1) | set(i2) if i1.get(k) != i2.get(k))
    # Cross-verification must fail: a v2 registration cannot be verified against v1's configuration and vice versa.
    cross = {}
    for label, rid, cfg in (('v2_reg_vs_v1_cfg', v2.registration_id, target_v1), ('v1_reg_vs_v2_cfg', v1.registration_id, target_v2)):
        try:
            registry.verify(rid, cfg)
            cross[label] = 'VERIFIED (unexpected)'
        except Exception as error:
            cross[label] = f'refused: {type(error).__name__}: {error}'
    out['cross_verification'] = cross
    from app.integrations.portability import require_independent_target
    try:
        require_independent_target(v1, v2)
        out['portability_v1_to_v2'] = 'ALLOWED (unexpected)'
    except ValueError as error:
        out['portability_v1_to_v2'] = f'refused: {error}'
OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + '\n')
print('written', OUT)
