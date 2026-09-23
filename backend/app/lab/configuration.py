"""Immutable actual source/configuration identities for comparable executions."""
from pathlib import Path
from hashlib import sha256
import re
import subprocess
from app.contracts.models import content_hash,EpisodeBudget
from app.providers.runtime import model_request_settings, actor_response_protocol
ROOT=Path(__file__).resolve().parents[3]
# Provenance is recorded once per campaign, outside the semantic configuration.
# In particular, a docs-only commit must not invalidate a frozen experiment.
SOURCE_PATHS = (
    ':(glob)backend/app/**/*.py', ':(glob)backend/app/**/*.md',
    ':(glob)contracts/*.schema.json', 'requirements.txt', 'backend/requirements.txt',
    'requirements.lock', 'backend/requirements.lock',
)

def source_provenance():
    """Return safe checkout metadata; never read diffs, secrets, or remote URLs."""
    try:
        revision = subprocess.run(
            ['git', '-C', str(ROOT), 'rev-parse', '--verify', 'HEAD'],
            check=True, capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        if not re.fullmatch(r'[a-f0-9]{40,64}', revision):
            return {'git_revision': None, 'runtime_dirty': None}
        status = subprocess.run(
            ['git', '-C', str(ROOT), 'status', '--porcelain=v1', '--untracked-files=all', '--', *SOURCE_PATHS],
            check=True, capture_output=True, timeout=2,
        )
        return {'git_revision': revision, 'runtime_dirty': bool(status.stdout)}
    except (OSError, subprocess.SubprocessError):
        return {'git_revision': None, 'runtime_dirty': None}

def file_hash(path): return sha256(Path(path).read_bytes()).hexdigest()
def tree_hash(path):
    path=Path(path)
    return content_hash({str(p.relative_to(path)):file_hash(p) for p in sorted(path.rglob('*')) if p.is_file() and p.suffix in ('.py','.md') and '__pycache__' not in str(p)})

def runtime_fingerprints():
    """Fingerprint executable source, including experiment and acceptance logic."""
    app = ROOT / 'backend/app'
    return {
        'algorithm_hash': content_hash({name: tree_hash(app / name) for name in ('lab', 'referee')}),
        'runtime_hash': tree_hash(app),
        'trace_contract_version': 2,
    }

def frozen_configuration(settings,caps,profile):
    from app.agents.actor import ACTOR_PROMPT_HASH
    from app.agents.progress import actor_context_protocols
    from app.referee.checks import scorer_hash
    schema=ROOT/'contracts'
    service_hash=tree_hash(ROOT/'backend/app/simulator')
    contract=content_hash({'schemas':{p.name:file_hash(p) for p in sorted(schema.glob('*.schema.json'))},'service_hash':service_hash})
    locks=[ROOT/'requirements.txt',ROOT/'backend/requirements.txt',ROOT/'requirements.lock',ROOT/'backend/requirements.lock']
    dependency=content_hash({str(p.relative_to(ROOT)):file_hash(p) for p in locks if p.exists()})
    if profile=='live-v1':
        models=settings.role_models
        bounds=settings.model_call_dollar_bounds or {role:None for role in models}
        pricing={}
        for role,model in models.items():
            input_rate,output_rate=settings.model_rates_for_role(role) or (-1.0,-1.0)
            pricing[role]={'model':model,'input_dollars_per_million':input_rate,'output_dollars_per_million':output_rate,'per_call_dollar_upper_bound':bounds[role]}
        pricing['per_call_dollar_upper_bound']=settings.model_call_dollar_bound
        lab_model=models['explorer']
        lab_pricing={key:value for key,value in pricing['explorer'].items() if key!='per_call_dollar_upper_bound'}
    else:
        models={role:'deterministic-reference/internal-smoke' for role in ('actor','explorer','mechanic')}
        pricing={'actor':{'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0,'per_call_dollar_upper_bound':None},'explorer':{'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0,'per_call_dollar_upper_bound':None},'mechanic':{'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0,'per_call_dollar_upper_bound':None},'per_call_dollar_upper_bound':None}
        lab_model='deterministic-reference/internal-smoke'
        lab_pricing={'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0}
    return {**runtime_fingerprints(),'schema_version':'faultlab/v1','model':models['actor'],'models':models,'pricing':pricing,'model_settings':model_request_settings(models['actor']),'model_settings_by_role':{role:model_request_settings(model) for role,model in models.items()},'actor_response_protocol':actor_response_protocol(),'actor_context_protocols':actor_context_protocols(),'lab_model':lab_model,'lab_model_settings':model_request_settings(lab_model),'lab_pricing':lab_pricing,'actor_prompt_hash':ACTOR_PROMPT_HASH,'adapter_hash':tree_hash(ROOT/'backend/app/adapters'),'interpreter_hash':content_hash({name:file_hash(Path(__file__).with_name(name)) for name in ('policy_interpreter.py','policy_state.py','budgets.py')}),'scorer_hash':scorer_hash(),'contract_hash':contract,'service_hash':service_hash,'capability_hash':content_hash({'scope':'orders.upgrade_then_confirm/v1','tools':['get_order','update_order','get_operation_status','send_confirmation'],'hooks':['after_upgrade_response','before_confirmation','after_notification_response','before_final_report']}),'dependency_lock_hash':dependency,'source_hash':tree_hash(ROOT/'backend/app/agents'),'episode_budget':EpisodeBudget().model_dump(mode='json'),'campaign_budget':caps.model_dump(mode='json'),'profile_id':profile}
