"""Genuine model proposals retained verbatim; format repair never supplies a policy."""
from pathlib import Path
from app.providers.runtime import RuntimeProviderError
from app.lab.provider_failures import record_provider_failure
from app.contracts.tokens import validate_model_input
from pydantic import TypeAdapter,ValidationError
from app.contracts.models import MechanicOutput,DiagnosticProposal,canonical_json,new_id
PROMPTS=Path(__file__).with_name('prompts')

class Mechanic:
    def __init__(self,provider,store,ledger):
        self.provider,self.store,self.ledger=provider,store,ledger
        self.trace=None; self.metadata=None
    async def _generate(self,prompt,context,adapter,*,reservation=None,allow_format_repair=True,validate_result=None):
        context={**context,'output_schema':adapter.json_schema()}
        messages=[{'role':'system','content':(PROMPTS/prompt).read_text()},{'role':'user','content':canonical_json(context)}]
        raws=[]
        role_model=getattr(self.provider,'role_model',None)
        expected=(role_model('mechanic') if callable(role_model) else None) or (self.metadata or {}).get('model_id',context.get('model_id','openai/gpt-oss-120b'))
        for attempt in range(2 if allow_format_repair else 1):
            validate_model_input(messages,expected)
            self.ledger.consume_call(reservation=reservation)
            from app.lab.tracing import phase_span
            try:
                async with phase_span(self.trace,'diagnose' if prompt=='diagnosis.md' else 'propose_policy',self.metadata,{'format_attempt':attempt,'evidence_ids':context.get('evidence_ids',[]),'parent_version':context.get('parent_version')}) as span:
                    generation=await self.provider.complete(messages,role='mechanic',max_output_tokens=2000,timeout_seconds=20)
                    if span: span.set_output({'raw_proposal':generation.content})
            except RuntimeProviderError as error:
                if error.generation is not None: self.ledger.reconcile(error.generation)
                record_provider_failure(self.store,error,role='mechanic',metadata=self.metadata or context)
                raise
            self.ledger.reconcile(generation)
            if self.metadata and generation.model_id!=expected:
                raise RuntimeProviderError('Provider returned a different frozen model')
            raws.append(generation.content)
            ref=new_id('mechanic')
            self.store.put_record('mechanic_outputs',ref,{'raw':generation.content,'role':'mechanic','prompt':prompt,'attempt':attempt,'model_id':generation.model_id},immutable=True)
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
