"""Registered development evidence authorization before any remote query."""
from dataclasses import dataclass
from app.contracts.models import Episode,EvidenceBundle,PublicObservation,canonical_json,content_hash,new_id,utc_now
from app.telemetry.weave_reader import TraceRegistration,WeaveReader

class EvidenceDenied(ValueError): pass
class WaitingEvidence(RuntimeError): pass

@dataclass(frozen=True)
class EvidenceContext:
    campaign_id:str
    study_id:str
    evidence_context_id:str
    selector_id:str|None=None
    diagnostic_only:bool=False

class EvidenceGateway:
    def __init__(self,store,project,*,reader=None,trace=None,worker=None):
        self.store,self.project,self.trace=store,project,trace
        self.reader=reader or (WeaveReader(worker,project,self.authorize_registration) if worker else None)

    def authorize(self,episode_id,context):
        e=self.store.get_model('episodes',episode_id,Episode)
        if e is None or e.split!='development' or e.arm=='B1': raise EvidenceDenied('Episode is not eligible optimizer evidence')
        if (e.campaign_id,e.study_id,e.evidence_context_id,e.selector_id)!=(context.campaign_id,context.study_id,context.evidence_context_id,context.selector_id): raise EvidenceDenied('Cross-context evidence denied')
        if e.experiment_purpose=='diagnostic_profile' and not context.diagnostic_only: raise EvidenceDenied('Diagnostic fixture is excluded from learning')
        if context.diagnostic_only and e.experiment_purpose!='diagnostic_profile': raise EvidenceDenied('Wrong diagnostic context')
        if context.selector_id is None and e.experiment_purpose in ('selection_comparison','portability'): raise EvidenceDenied('Study evidence cannot enter ordinary optimization')
        if e.lifecycle!='COMPLETED': raise EvidenceDenied('Incomplete episode is not normal learning evidence')
        return e

    def authorize_registration(self,registration):
        raw=self.store.get_record('trace_registrations',registration.metadata.get('episode_id',''))
        if not raw: return False
        return raw['project']==registration.project and raw['root_call_id']==registration.root_call_id and raw['metadata']==registration.metadata and raw['child_call_ids']==list(registration.child_call_ids)

    def register_trace(self,episode_id):
        e=self.store.get_model('episodes',episode_id,Episode)
        calls=self.trace.episode_calls(episode_id) if self.trace else []
        roots=[c for c in calls if c['name']=='run_episode']
        if len(roots)!=1: raise WaitingEvidence('Registered root trace is unavailable')
        root=roots[0]; children=[c for c in calls if c.get('parent_id')==root['call_id']]
        registration=TraceRegistration(self.project,root['metadata'],root['call_id'],tuple(c['call_id'] for c in children),{})
        raw={'project':registration.project,'metadata':registration.metadata,'root_call_id':registration.root_call_id,'child_call_ids':list(registration.child_call_ids),'child_identities':{}}
        self.store.put_record('trace_registrations',episode_id,raw,immutable=True)
        self.store.associate_ingestion(self.project,root['call_id'],episode_id)
        return registration

    async def get(self,episode_id,context,*,require_remote=True,stopped=lambda:False):
        e=self.authorize(episode_id,context)
        existing=self.store.get_record('evidence',episode_id)
        if existing and (not require_remote or existing['source']=='weave_verified'):
            return EvidenceBundle.model_validate_json(canonical_json(existing))
        observations=[PublicObservation.model_validate_json(canonical_json(o)) for o in self.store.list_records('observations') if o['episode_id']==episode_id]
        source='local_only'; root=None; children=[]; retrieved=None
        if require_remote:
            if e.source_mode!='live' or not self.reader: raise WaitingEvidence('Verified remote development evidence is required')
            registration=self.register_trace(episode_id)
            result=await self.reader.read(registration,stopped=stopped)
            self.store.put_record('ingestions',episode_id,{'episode_id':episode_id,'state':result.ingestion_state,'status':result.status,'execution_epoch':e.execution_epoch,'error_code':result.error_code})
            if result.snapshot is None: raise WaitingEvidence(result.error_code or 'Evidence pending')
            # Compare exact delivered observations/report, not merely remote tags.
            snapshot=result.snapshot
            remote_obs=[call['output']['observation'] for call in snapshot['calls'][1:]]
            if [o.model_dump(mode='json') for o in observations]!=remote_obs or snapshot['calls'][0]['output']['report']!=(e.report.model_dump(mode='json') if e.report else None): raise EvidenceDenied('Remote delivered evidence differs from local authority')
            self.authorize(episode_id,context)
            source='weave_verified'; root=registration.root_call_id; children=list(registration.child_call_ids); retrieved=utc_now()
        config=self.store.get_record('configurations',e.configuration_hash)
        fields={'episode_id':episode_id,'policy_hash':e.policy_hash,'contract_hash':config['contract_hash'],'scorer_hash':config['scorer_hash'],'source':source,'root_call_id':root,'child_call_ids':children,'observations':observations,'report':e.report,'findings':e.verdict.checks if e.verdict else [],'retrieved_at':retrieved,'source_project':self.project if source=='weave_verified' else None}
        bundle=EvidenceBundle(**fields,digest='0'*64)
        bundle.digest=content_hash({k:v for k,v in bundle.model_dump(mode='json').items() if k!='digest'})
        self.store.put_record('evidence',episode_id,bundle)
        return bundle

    async def retry(self,episode_id):
        e=self.store.get_model('episodes',episode_id,Episode)
        if e is None: raise EvidenceDenied('Unknown episode')
        context=EvidenceContext(e.campaign_id,e.study_id,e.evidence_context_id,e.selector_id,e.experiment_purpose=='diagnostic_profile')
        self.authorize(episode_id,context)
        if self.trace: await self.trace.retry_episode_upload(episode_id)
        return await self.get(episode_id,context)

    @staticmethod
    def format(bundles):
        from app.lab.diagnosis import summarize_evidence
        return canonical_json(summarize_evidence(bundles))
