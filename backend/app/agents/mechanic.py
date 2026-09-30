"""Genuine model proposals retained verbatim; format repair never supplies a policy."""
from pathlib import Path
from app.providers.runtime import RuntimeProviderError
from app.lab.provider_failures import record_provider_failure,record_transport_retry
from app.agents.transport_retry import charge_ledger_retry,complete_with_backoff,complete_with_one_retry,ledger_retry_fits,request_usage
from app.contracts.tokens import validate_model_input
from pydantic import TypeAdapter,ValidationError
from app.contracts.models import MechanicOutput,DiagnosticProposal,canonical_json,new_id
PROMPTS=Path(__file__).with_name('prompts')
# The request kind recorded with a transport retry, by prompt (mechanic.md is the policy proposal).
REQUEST_KINDS={'diagnosis.md':'mechanic_diagnosis','mechanic.md':'mechanic_proposal','completion.md':'mechanic_completion'}

class Mechanic:
    def __init__(self,provider,store,ledger):
        self.provider,self.store,self.ledger=provider,store,ledger
        self.trace=None; self.metadata=None
        # The Learn campaign's rule-v2 lab-role backoff (app.agents.transport_retry.LabBackoff), set by the
        # learning loop when its plan declares it. None keeps rule v1's single blind retry.
        self.lab_retry=None
    async def _generate(self,prompt,context,adapter,*,reservation=None,allow_format_repair=True,validate_result=None):
        context={**context,'output_schema':adapter.json_schema()}
        messages=[{'role':'system','content':(PROMPTS/prompt).read_text()},{'role':'user','content':canonical_json(context)}]
        raws=[]; request_id=new_id('mechanic-request'); request_kind=REQUEST_KINDS[prompt]  # before any charge
        role_model=getattr(self.provider,'role_model',None)
        expected=(role_model('mechanic') if callable(role_model) else None) or (self.metadata or {}).get('model_id',context.get('model_id','openai/gpt-oss-120b'))
        for attempt in range(2 if allow_format_repair else 1):
            validate_model_input(messages,expected)
            self.ledger.consume_call(reservation=reservation,role='mechanic')
            from app.lab.tracing import phase_span
            span_inputs={'format_attempt':attempt,'evidence_ids':context.get('evidence_ids',[]),'parent_version':context.get('parent_version')}
            async def send(retry):
                async with phase_span(self.trace,'diagnose' if prompt=='diagnosis.md' else 'propose_policy',self.metadata,{**span_inputs,'transport_retry':True} if retry else span_inputs) as span:
                    generation=await self.provider.complete(messages,role='mechanic',max_output_tokens=2000,timeout_seconds=20)
                    if span: span.set_output({'raw_proposal':generation.content})
                return generation
            def failed(error):
                if error.generation is not None: self.ledger.reconcile(error.generation)
                return record_provider_failure(self.store,error,role='mechanic',metadata=self.metadata or context)
            def record(error,failure_id):
                return record_transport_retry(self.store,error,role='mechanic',failure_id=failure_id,metadata=self.metadata or context,
                    request={'kind':request_kind,'request_id':request_id,'format_attempt':attempt})
            # The shared blind-retry rule (app.agents.transport_retry): one retry of this same
            # request, charged on the ledger first from unreserved capacity, never after an answer.
            # A format repair (the second attempt above) is a new request, not a retry.
            lab=self.lab_retry
            if lab is None:
                generation,retries=await complete_with_one_retry(send,failed=failed,admit=lambda:charge_ledger_retry(self.ledger,'mechanic'),record=record)
            else:
                # Rule v2: up to three backed-off retries of this same request within the campaign's lab-role cap,
                # each charged on the ledger before it is sent; a Stop during a wait ends the campaign STOPPED.
                def record_backoff(error,failure_id,retry_attempt,delay):
                    return record_transport_retry(self.store,error,role='mechanic',failure_id=failure_id,metadata=self.metadata or context,
                        request={'kind':request_kind,'request_id':request_id,'format_attempt':attempt,'phase':request_kind},
                        backoff={'attempt':retry_attempt,'delay':delay,'campaign_retry_number':lab.used})  # counted just before
                generation,retries=await complete_with_backoff(send,failed=failed,admit=lambda:charge_ledger_retry(self.ledger,'mechanic'),
                                                               record=record_backoff,session=lab,role='mechanic',
                                                               fits=lambda:ledger_retry_fits(self.ledger,'mechanic'))
            self.ledger.reconcile(generation)
            if self.metadata and generation.model_id!=expected:
                raise RuntimeProviderError('Provider returned a different frozen model')
            raws.append(generation.content)
            ref=new_id('mechanic')
            metadata=self.metadata or {}
            self.store.put_record('mechanic_outputs',ref,{'raw':generation.content,'role':'mechanic','prompt':prompt,'attempt':attempt,'model_id':generation.model_id,'request_id':request_id,'campaign_id':metadata.get('campaign_id') or context.get('campaign_id'),'episode_id':metadata.get('episode_id'),'usage':request_usage(generation,retries),**({'transport_retries':retries} if retries else {})},immutable=True)
            try:
                result=adapter.validate_json(generation.content)
                errors=validate_result(result) if validate_result else []
            except ValidationError as error:
                errors=[{'location':list(issue['loc']),'type':issue['type']}
                        for issue in error.errors(include_input=False,include_context=False,include_url=False)]
            if not errors: return ref,result,raws
            if attempt==0 and allow_format_repair:
                messages.extend([{'role':'assistant','content':generation.content},{'role':'user','content':canonical_json({'validation_errors':errors,'instruction':'Your response failed output_schema or its supplied evidence/choice bindings. Correct formatting only. Copy cited IDs exactly from the supplied allowed lists; cite only the evidence needed. Do not add authority, a new hypothesis, or a replacement canned solution.'})}])
        return ref,None,raws
    async def diagnose(self,context,*,reservation=None):
        def validate_bindings(result):
            allowed=set(context.get('evidence_ids',[]))
            options=set(context.get('intervention_ids',[]))
            errors=[]
            if not set(result.evidence_ids)<=allowed:
                errors.append({'location':['evidence_ids'],'type':'unknown_evidence_reference'})
            if result.requested_intervention_id is not None and result.requested_intervention_id not in options:
                errors.append({'location':['requested_intervention_id'],'type':'unknown_intervention_reference'})
            return errors
        return await self._generate('diagnosis.md',context,TypeAdapter(DiagnosticProposal),reservation=reservation,validate_result=validate_bindings)
    async def propose(self,context,*,reservation=None):
        # Schema is complete but contains no solved benchmark examples.
        return await self._generate('mechanic.md',context,TypeAdapter(MechanicOutput),reservation=reservation)
    async def propose_completion(self,context,*,reservation=None):
        # This separate development objective cannot invoke invariant promotion.
        return await self._generate('completion.md',context,TypeAdapter(MechanicOutput),reservation=reservation)
