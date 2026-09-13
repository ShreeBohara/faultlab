"""Immutable actual source/configuration identities for comparable executions."""
from pathlib import Path
from hashlib import sha256
from app.contracts.models import content_hash,EpisodeBudget
from app.providers.runtime import model_request_settings
ROOT=Path(__file__).resolve().parents[3]
def file_hash(path): return sha256(Path(path).read_bytes()).hexdigest()
def tree_hash(path):
    path=Path(path)
    return content_hash({str(p.relative_to(path)):file_hash(p) for p in sorted(path.rglob('*')) if p.is_file() and p.suffix in ('.py','.md') and '__pycache__' not in str(p)})
def frozen_configuration(settings,caps,profile):
    from app.agents.actor import ACTOR_PROMPT_HASH
    from app.referee.checks import scorer_hash
    schema=ROOT/'contracts'
    service_hash=tree_hash(ROOT/'backend/app/simulator')
    contract=content_hash({'schemas':{p.name:file_hash(p) for p in sorted(schema.glob('*.schema.json'))},'service_hash':service_hash})
    locks=[ROOT/'requirements.txt',ROOT/'backend/requirements.txt',ROOT/'requirements.lock',ROOT/'backend/requirements.lock']
    dependency=content_hash({str(p.relative_to(ROOT)):file_hash(p) for p in locks if p.exists()})
    if profile=='live-v1':
        models=settings.role_models
        bounds=settings.model_call_dollar_bounds or {role:None for role in models}
        pricing={
            'actor':{'model':models['actor'],'input_dollars_per_million':settings.faultlab_input_dollars_per_million,'output_dollars_per_million':settings.faultlab_output_dollars_per_million,'per_call_dollar_upper_bound':bounds['actor']},
            'explorer':{'model':models['explorer'],'input_dollars_per_million':settings.faultlab_reasoning_input_dollars_per_million if models['explorer']!=models['actor'] else settings.faultlab_input_dollars_per_million,'output_dollars_per_million':settings.faultlab_reasoning_output_dollars_per_million if models['explorer']!=models['actor'] else settings.faultlab_output_dollars_per_million,'per_call_dollar_upper_bound':bounds['explorer']},
            'mechanic':{'model':models['mechanic'],'input_dollars_per_million':settings.faultlab_reasoning_input_dollars_per_million if models['mechanic']!=models['actor'] else settings.faultlab_input_dollars_per_million,'output_dollars_per_million':settings.faultlab_reasoning_output_dollars_per_million if models['mechanic']!=models['actor'] else settings.faultlab_output_dollars_per_million,'per_call_dollar_upper_bound':bounds['mechanic']},
            'per_call_dollar_upper_bound':settings.model_call_dollar_bound,
        }
        lab_model=models['explorer']
        lab_input=settings.faultlab_lab_input_dollars_per_million if settings.faultlab_lab_input_dollars_per_million>=0 else settings.faultlab_reasoning_input_dollars_per_million
        lab_output=settings.faultlab_lab_output_dollars_per_million if settings.faultlab_lab_output_dollars_per_million>=0 else settings.faultlab_reasoning_output_dollars_per_million
        lab_pricing={'model':settings.faultlab_lab_pricing_model or settings.faultlab_reasoning_pricing_model,'input_dollars_per_million':lab_input,'output_dollars_per_million':lab_output}
    else:
        models={role:'deterministic-reference/internal-smoke' for role in ('actor','explorer','mechanic')}
        pricing={'actor':{'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0,'per_call_dollar_upper_bound':None},'explorer':{'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0,'per_call_dollar_upper_bound':None},'mechanic':{'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0,'per_call_dollar_upper_bound':None},'per_call_dollar_upper_bound':None}
        lab_model='deterministic-reference/internal-smoke'
        lab_pricing={'model':'','input_dollars_per_million':-1.0,'output_dollars_per_million':-1.0}
    return {'schema_version':'faultlab/v1','model':models['actor'],'models':models,'pricing':pricing,'model_settings':model_request_settings(models['actor']),'model_settings_by_role':{role:model_request_settings(model) for role,model in models.items()},'lab_model':lab_model,'lab_model_settings':model_request_settings(lab_model),'lab_pricing':lab_pricing,'actor_prompt_hash':ACTOR_PROMPT_HASH,'adapter_hash':tree_hash(ROOT/'backend/app/adapters'),'interpreter_hash':content_hash({name:file_hash(Path(__file__).with_name(name)) for name in ('policy_interpreter.py','policy_state.py','budgets.py')}),'scorer_hash':scorer_hash(),'contract_hash':contract,'service_hash':service_hash,'capability_hash':content_hash({'scope':'orders.upgrade_then_confirm/v1','tools':['get_order','update_order','get_operation_status','send_confirmation'],'hooks':['after_upgrade_response','before_confirmation','after_notification_response','before_final_report']}),'dependency_lock_hash':dependency,'source_hash':tree_hash(ROOT/'backend/app/agents'),'episode_budget':EpisodeBudget().model_dump(mode='json'),'campaign_budget':caps.model_dump(mode='json'),'profile_id':profile}
