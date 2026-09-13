"""Safe phase spans receive explicit public scalars, never coordinator objects."""
from contextlib import asynccontextmanager
from contextvars import Context
import asyncio
from app.contracts.models import Provenance

def trace_metadata(campaign,episode_id,policy,configuration,*,purpose='discovery',role='actor'):
    provenance=Provenance(campaign_id=campaign.campaign_id,episode_id=episode_id,origin='prototype' if purpose=='discovery' else 'faultlab_evaluation',split='development',arm='B0' if policy.version=='policy-v0' else 'L',source_mode='live',experiment_purpose=purpose,trial_index=0,study_id=campaign.campaign_id,evidence_context_id=campaign.campaign_id,execution_epoch=campaign.execution_epoch)
    model_id=(configuration.get('models') or {}).get(role,campaign.model)
    lab_model=(configuration.get('lab_model') or (configuration.get('models') or {}).get('explorer') or campaign.model)
    return {**provenance.model_dump(mode='json'),'model_id':model_id,'lab_model_id':lab_model,'policy_hash':policy.policy_hash,'contract_hash':configuration['contract_hash'],'scorer_hash':configuration['scorer_hash']}

@asynccontextmanager
async def phase_span(trace,name,metadata,inputs):
    if trace is None or metadata is None:
        yield None
        return
    manager=trace.span(name,metadata,inputs)
    try: span=await manager.__aenter__()
    except Exception:
        yield None
        return
    try:
        yield span
    except BaseException as error:
        try: await manager.__aexit__(type(error),error,error.__traceback__)
        except BaseException: pass
        raise
    else:
        try: await manager.__aexit__(None,None,None)
        except Exception: pass

async def execute_phase(trace,name,metadata,inputs,operation):
    async with phase_span(trace,name,metadata,inputs) as span:
        # Each episode is a trace root. The phase is a correlated sibling;
        # its ContextVar parent must not leak into fresh actor execution.
        result=await asyncio.create_task(operation(),context=Context())
        if span:
            span.set_output({'completed':True,'result_reference':getattr(result,'challenge_id',None) or getattr(result,'diagnostic_id',None) or getattr(result,'batch_id',None)})
        return result

async def execute_sync_phase(trace,name,metadata,inputs,operation):
    async def run(): return operation()
    return await execute_phase(trace,name,metadata,inputs,run)
