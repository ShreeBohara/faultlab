"""Immutable actual source/configuration identities for comparable executions."""
from pathlib import Path
from hashlib import sha256
from app.contracts.models import content_hash,EpisodeBudget
ROOT=Path(__file__).resolve().parents[3]
def file_hash(path): return sha256(Path(path).read_bytes()).hexdigest()
def tree_hash(path):
    path=Path(path)
    return content_hash({str(p.relative_to(path)):file_hash(p) for p in sorted(path.rglob('*.py')) if '__pycache__' not in str(p)})
def frozen_configuration(settings,caps,profile):
    from app.agents.actor import ACTOR_PROMPT_HASH
    from app.referee.checks import scorer_hash
    schema=ROOT/'contracts'
    service_hash=tree_hash(ROOT/'backend/app/simulator')
    contract=content_hash({'schemas':{p.name:file_hash(p) for p in sorted(schema.glob('*.schema.json'))},'service_hash':service_hash})
    locks=[ROOT/'requirements.txt',ROOT/'backend/requirements.txt',ROOT/'requirements.lock',ROOT/'backend/requirements.lock']
    dependency=content_hash({str(p.relative_to(ROOT)):file_hash(p) for p in locks if p.exists()})
    return {'schema_version':'faultlab/v1','model':settings.wandb_model if profile=='live-v1' else 'deterministic-reference/internal-smoke','pricing':{'model':settings.faultlab_pricing_model,'input_dollars_per_million':settings.faultlab_input_dollars_per_million,'output_dollars_per_million':settings.faultlab_output_dollars_per_million,'per_call_dollar_upper_bound':settings.model_call_dollar_bound},'model_settings':{'max_output_tokens':2000,'timeout_seconds':20,'retries':0},'actor_prompt_hash':ACTOR_PROMPT_HASH,'adapter_hash':tree_hash(ROOT/'backend/app/adapters'),'interpreter_hash':content_hash({name:file_hash(Path(__file__).with_name(name)) for name in ('policy_interpreter.py','policy_state.py','budgets.py')}),'scorer_hash':scorer_hash(),'contract_hash':contract,'service_hash':service_hash,'capability_hash':content_hash({'scope':'orders.upgrade_then_confirm/v1','tools':['get_order','update_order','get_operation_status','send_confirmation'],'hooks':['after_upgrade_response','before_confirmation','after_notification_response','before_final_report']}),'dependency_lock_hash':dependency,'source_hash':tree_hash(ROOT/'backend/app/agents'),'episode_budget':EpisodeBudget().model_dump(mode='json'),'campaign_budget':caps.model_dump(mode='json'),'profile_id':profile}
