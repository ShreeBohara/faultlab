"""Strict, read-safe localhost dashboard API; lazy dependency preserves health."""
from typing import Literal
from pydantic import Field,ValidationError
from fastapi import APIRouter,Query
from fastapi.responses import JSONResponse,Response
from app.config import ConfigurationError
from app.contracts.models import CampaignRequest,StrictModel,Id,Episode,canonical_json,new_id
from app.lab.storage import StoreConflict
from app.lab.budgets import BudgetExhausted

class EmptyRequest(StrictModel): pass
class RetryRequest(StrictModel): episode_ids:list[Id]|None=Field(default=None,max_length=200)
class ResetRequest(StrictModel): fixture_profile_id:Literal['standard-v1']='standard-v1'
class EvaluationRequest(StrictModel):
    campaign_id:Id
    purpose:Literal['comparison','final_audit']
    policy_versions:list[Id]=Field(min_length=1,max_length=3)
class PortabilityRequest(StrictModel):
    agent_registration_id:Id
    policy_version:Id|None=None
    execute_live:Literal[True]

class StudyRequest(StrictModel):
    execute_live:Literal[True]

class ExecutionRequest(StrictModel):
    agent_registration_id:Id
    execution_profile_id:Id
    policy_version:Id
    execute_live:Literal[True]

def error_response(error):
    if isinstance(error,KeyError): status,code,message=404,'NOT_FOUND','Unknown record'
    elif isinstance(error,(StoreConflict,BudgetExhausted)): status,code,message=409,'CONFLICT',str(error)
    elif isinstance(error,ConfigurationError): status,code,message=503,'SERVICE_UNAVAILABLE','Live configuration is not ready: '+', '.join(error.missing_fields)
    elif isinstance(error,ValidationError): status,code,message=422,'INVALID_REQUEST','Record failed the frozen schema'
    elif isinstance(error,ValueError): status,code,message=422,'INVALID_REQUEST',str(error)[:200]
    else: status,code,message=503,'SERVICE_UNAVAILABLE','Required local service unavailable'
    return JSONResponse(status_code=status,content={'error':{'code':code,'message':message,'request_id':new_id('request')}})


def create_router(get_coordinator):
    router=APIRouter(prefix='/api')
    def c(): return get_coordinator() if callable(get_coordinator) else get_coordinator
    def record(kind,id):
        found=c().store.get_record(kind,id)
        if found is None: raise KeyError(id)
        return found
    def records(kind,campaign_id=None):
        data=c().store.list_records(kind)
        return [v for v in data if campaign_id is None or v.get('campaign_id')==campaign_id]
    def safe_episode(id):
        value=record('episodes',id)
        if value['split']!='development':
            value={**value,'verdict':None,'report':None}
        return value
    def guarded(fn):
        from functools import wraps
        @wraps(fn)
        async def wrapped(*args,**kwargs):
            try: return await fn(*args,**kwargs)
            except Exception as error: return error_response(error)
        return wrapped

    @router.get('/config/status')
    @guarded
    async def config_status(): return c().config_status()
    @router.post('/campaigns',status_code=201)
    @guarded
    async def create(request:CampaignRequest): return c().create(request)
    @router.post('/campaigns/{id}/start',status_code=202)
    @guarded
    async def start(id:str,request:EmptyRequest): return await c().start(id)
    @router.post('/campaigns/{id}/stop',status_code=202)
    @guarded
    async def stop(id:str,request:EmptyRequest): return await c().stop(id)
    @router.get('/campaigns/{id}')
    @guarded
    async def detail(id:str): return c().get(id)
    @router.get('/episodes/{id}')
    @guarded
    async def episode(id:str): return safe_episode(id)
    @router.get('/episodes/{id}/events')
    @guarded
    async def events(id:str,after:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=200)):
        episode=record('episodes',id)
        page=c().store.events(id,after=after,limit=limit)
        if episode['split']!='development': page['events']=[]
        return page
    @router.get('/policies')
    @guarded
    async def policies(): return c().policies.list()
    @router.get('/policies/{version}')
    @guarded
    async def policy(version:str): return record('policies',version)
    @router.get('/policies/{version}/proposal')
    @guarded
    async def policy_proposal(version:str):
        policy=record('policies',version)
        proposal=c().store.get_record('proposals',policy['raw_proposal_ref']) if policy['raw_proposal_ref'] else None
        return {'policy_version':version,'proposal_ref':policy['raw_proposal_ref'],'raw':proposal.get('raw') if proposal else None,'author':policy['author'],'parent_version':policy['parent_version']}
    @router.get('/campaigns/{id}/configuration')
    @guarded
    async def configuration(id:str):
        campaign=c().get(id)
        return record('configurations',campaign.configuration_hash)
    @router.get('/campaigns/{id}/matrix')
    @guarded
    async def matrix(id:str):
        c().get(id); episodes=records('episodes',id)
        cells=[]; counts={'valid_attempted':0,'completed':0,'violations':0,'safe_unresolved':0,'correctly_rejected':0,'lab_errors':0,'interrupted':0,'scheduled':0,'triggered':0,'untriggered':0}
        for episode in episodes:
            if episode['experiment_purpose'] in ('diagnostic_profile','selection_comparison','portability') or episode['study_id']!=id: continue
            verdict=episode.get('verdict') or {}; faults=verdict.get('fault_executions',[])
            outcome=verdict.get('outcome'); scheduled=bool(faults); triggered=scheduled and all(f['triggered'] for f in faults)
            if episode['lifecycle']=='INTERRUPTED': counts['interrupted']+=1
            elif episode['lifecycle']=='LAB_ERROR': counts['lab_errors']+=1
            elif episode['lifecycle']=='COMPLETED':
                counts['valid_attempted']+=1
                key={'COMPLETED':'completed','VIOLATION':'violations','SAFE_UNRESOLVED':'safe_unresolved','CORRECTLY_REJECTED':'correctly_rejected'}.get(outcome)
                if key: counts[key]+=1
            counts['scheduled']+=int(scheduled); counts['triggered']+=int(triggered); counts['untriggered']+=int(scheduled and not triggered)
            cells.append({'episode_id':episode['episode_id'],'scenario_alias':episode['scenario_hash'][:10],'arm':episode['arm'],'policy_hash':episode['policy_hash'],'outcome':outcome,'lifecycle':episode['lifecycle'],'fault_scheduled':scheduled,'fault_triggered':triggered,'source_mode':episode['source_mode'],'telemetry_provenance':(c().store.get_record('evidence',episode['episode_id']) or {}).get('source','local_only'),'usage':episode['usage']})
        return {'campaign_id':id,'cells':cells,'counts':counts}
    @router.get('/evidence-retries/{id}')
    @guarded
    async def evidence_retry_status(id:str):
        result=c().store.get_record('evidence_retries',id)
        if result is None: raise KeyError(id)
        return result

    @router.post('/campaigns/{id}/retry-evidence',status_code=202)
    @guarded
    async def retry(id:str,request:RetryRequest): return await c().retry_evidence(id,request.episode_ids)
    @router.get('/campaigns/{id}/experiments')
    @guarded
    async def experiments(id:str):
        c().get(id)
        counters=records('counterexamples',id); joined=[]
        for counter in counters:
            key=counter['counterexample_id']; recipe=c().store.get_record('counterexample_recipes',key) or {}
            retained=c().store.get_record('retained_recipes',key) or {}
            diagnostics=[d for d in records('diagnostics') if d.get('counterexample_id')==key]
            interventions=[d for d in records('interventions') if d.get('counterexample_id')==key]
            campaign_challenges={d['challenge_id'] for d in records('challenge_campaigns',id)}
            challenges=[d for d in records('challenges') if d['challenge_id'] in campaign_challenges]
            joined.append({'counterexample':counter,'source_recipe':recipe.get('source_recipe'),'retained_recipe':retained.get('retained_recipe'),'reduction':c().store.get_record('reductions',key),'diagnostics':diagnostics,'interventions':interventions,'challenges':challenges})
        episodes={e['episode_id'] for e in records('episodes',id) if e['split']=='development' and e['experiment_purpose'] not in ('selection_comparison','diagnostic_profile')}
        evidence=[{**{k:d[k] for k in ('episode_id','source','root_call_id','child_call_ids','source_project')},'root_call_url':'https://wandb.ai/'+d['source_project']+'/weave/calls/'+d['root_call_id'] if d['source']=='weave_verified' and d['root_call_id'] and d['source_project'] else None} for d in records('evidence') if d['episode_id'] in episodes]
        return {'counterexamples':joined,'evidence':evidence,'ingestions':[d for d in records('ingestions') if d['episode_id'] in episodes],'portability_ids':[d['portability_id'] for d in records('portability_campaigns',id)]}
    @router.get('/campaigns/{id}/regressions')
    @guarded
    async def regressions(id:str): c().get(id); return records('regressions',id)
    @router.get('/campaigns/{id}/counterexamples')
    @guarded
    async def counterexamples(id:str): c().get(id); return records('counterexamples',id)
    @router.get('/counterexamples/{id}')
    @guarded
    async def counterexample(id:str): return record('counterexamples',id)
    @router.get('/diagnostics/{id}')
    @guarded
    async def diagnostic(id:str): return record('diagnostics',id)
    @router.get('/challenges/{id}')
    @guarded
    async def challenge(id:str): return record('challenges',id)
    @router.get('/evaluations/{id}')
    @guarded
    async def evaluation(id:str):
        raw=record('evaluations',id)
        if raw['split']!='development': raw={**raw,'trials':[]}
        return raw
    @router.post('/evaluations',status_code=202)
    @guarded
    async def evaluate(request:EvaluationRequest):
        from app.lab.evaluation import queue_evaluation
        return await queue_evaluation(c(),request)
    @router.get('/regressions/{id}/bundle')
    @guarded
    async def bundle(id:str):
        regression=record('regressions',id)
        return record('bundles',regression['bundle_id'])
    @router.get('/regressions/{id}/download')
    @guarded
    async def download(id:str):
        import io,zipfile
        from app.contracts.models import RegressionBundle
        from app.lab.regressions import validate_bundle
        regression=record('regressions',id)
        bundle=c().store.get_model('bundles',regression['bundle_id'],RegressionBundle)
        payloads=c().store.get_record('bundle_files',bundle.bundle_id)
        validate_bundle(bundle,payloads)
        target=io.BytesIO()
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',bundle.model_dump_json(indent=2))
            for entry in bundle.files: archive.writestr(entry.path,payloads[entry.path])
        return Response(target.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{bundle.bundle_id}.zip"'})
    @router.post('/reset-demo',status_code=201)
    @guarded
    async def reset(request:ResetRequest):
        if c().active_id: raise StoreConflict('Cannot reset during active execution')
        record={'reset_id':new_id('reset'),'fixture_profile_id':request.fixture_profile_id,'status':'READY_FOR_FRESH_RUN'}
        c().store.put_record('resets',record['reset_id'],record,immutable=True)
        return record
    @router.post('/campaigns/{id}/baseline-study',status_code=202)
    @guarded
    async def baseline_study_start(id:str,request:StudyRequest):
        from app.lab.baseline_study import queue_baseline_study
        return await queue_baseline_study(c(),id)
    @router.get('/baseline-studies/{id}')
    @guarded
    async def baseline_study_status(id:str): return record('baseline_studies',id)

    @router.post('/campaigns/{id}/search-comparison',status_code=202)
    @guarded
    async def search_comparison(id:str,request:StudyRequest):
        from app.lab.search_benchmark import queue_search
        return await queue_search(c(),id)
    @router.get('/search-requests/{id}')
    @guarded
    async def search_request(id:str): return record('search_requests',id)
    @router.get('/search-comparisons/{id}/results')
    @guarded
    async def search_results(id:str): return record('search_results',id)
    @router.get('/evaluation-requests/{id}')
    @guarded
    async def evaluation_request(id:str): return record('evaluation_requests',id)
    @router.get('/audit-results/{id}')
    @guarded
    async def audit_result(id:str): return record('audit_results',id)
    @router.get('/search-comparisons/{id}')
    @guarded
    async def search_detail(id:str): return record('search_comparisons',id)
    @router.get('/campaigns/{id}/budget')
    @guarded
    async def budget(id:str): c().get(id); return c().store.get_record('budgets',id) or {'usage_metadata_known':True,'measured_input_tokens':0,'measured_output_tokens':0,'reservations':{}}
    @router.get('/agent-registrations')
    @guarded
    async def registrations(): return records('agent_registrations')
    @router.post('/campaigns/{id}/portability',status_code=202)
    @guarded
    async def portability_start(id:str,request:PortabilityRequest):
        from app.lab.portability import queue_portability
        return await queue_portability(c(),id,request)
    @router.get('/portability-requests/{id}')
    @guarded
    async def portability_request(id:str): return record('portability_requests',id)
    @router.get('/portability/{id}/metrics')
    @guarded
    async def portability_metrics(id:str): return record('portability_metrics',id)
    @router.get('/portability/{id}')
    @guarded
    async def portability(id:str): return record('portability',id)
    @router.get('/regression-executions/{id}')
    @guarded
    async def execution(id:str): return record('regression_executions',id)
    @router.post('/regressions/{id}/execute',status_code=202)
    @guarded
    async def execute(id:str,request:ExecutionRequest):
        from app.lab.regression_executions import execute_regression
        return await execute_regression(c(),id,request)
    @router.get('/campaigns/{id}/aria-evidence')
    @guarded
    async def aria_get(id:str): c().get(id); return records('aria',id)
    from app.lab.aria_evidence import AriaEvidenceRequest,save_aria_evidence
    @router.post('/campaigns/{id}/aria-evidence',status_code=201)
    @guarded
    async def aria_post(id:str,request:AriaEvidenceRequest): return save_aria_evidence(c(),id,request)
    return router
