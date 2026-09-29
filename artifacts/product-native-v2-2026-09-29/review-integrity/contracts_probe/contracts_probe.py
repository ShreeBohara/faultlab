"""Integrity reviewer: response contracts on ROOT (checkpoint copy or working tree). Offline; imports only
app.providers.runtime and app.contracts.models (no provider object is created, no network, no .env).

Usage: python contracts_probe.py ROOT OUT_JSON
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

import app.providers.runtime as runtime  # noqa: E402
from app.contracts.models import ReportAction, TaskReport, canonical_json, content_hash  # noqa: E402

assert Path(runtime.__file__).resolve().is_relative_to(ROOT)
out = {
    'runtime_file': runtime.__file__,
    'ACTOR_RESPONSE_PROTOCOL_VERSION': runtime.ACTOR_RESPONSE_PROTOCOL_VERSION,
    'ACTOR_FINAL_REPORT_SCHEMA_JSON_sha256': content_hash(runtime.ACTOR_FINAL_REPORT_SCHEMA_JSON),
    'response_format_for_default_actor': runtime.response_format_for(),
    'response_format_for_actor_final_report': runtime.response_format_for(response_contract='actor_final_report'),
    'actor_response_protocol': runtime.actor_response_protocol(),
    'actor_response_protocol_hash': content_hash(runtime.actor_response_protocol()),
    'MODEL_REQUEST_SETTINGS': runtime.MODEL_REQUEST_SETTINGS,
    'ReportAction_schema_hash': content_hash(ReportAction.model_json_schema()),
    'TaskReport_schema_hash': content_hash(TaskReport.model_json_schema()),
    'ResponseContract_args': list(getattr(runtime.ResponseContract, '__args__', ())),
}
# Role-incompatible selections must stay refused.
refusals = {}
for role, contract in (('explorer', 'actor_final_report'), ('mechanic', 'actor_final_report'), ('actor', 'other'),
                       ('explorer', 'native_final_answer'), ('mechanic', 'native_final_answer')):
    try:
        runtime.response_format_for(role=role, response_contract=contract)
        refusals[f'{role}/{contract}'] = 'ALLOWED'
    except runtime.RuntimeProviderError as error:
        refusals[f'{role}/{contract}'] = error.code
out['refusals'] = refusals
if hasattr(runtime, 'native_final_answer_protocol'):
    out['native_final_answer_protocol'] = runtime.native_final_answer_protocol()
    out['native_final_answer_schema'] = json.loads(runtime.NATIVE_FINAL_ANSWER_SCHEMA_JSON)
OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + '\n')
print('written', OUT)
