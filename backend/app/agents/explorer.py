"""Bounded selection and explicitly labeled fixed invalid-output fallback."""
from pathlib import Path
from app.providers.runtime import RuntimeProviderError
from app.lab.provider_failures import record_provider_failure
from app.contracts.tokens import validate_model_input
from app.contracts.models import ExplorerOutput,canonical_json,new_id,content_hash
from app.lab.budgets import BudgetExhausted
PROMPT=Path(__file__).with_name('prompts').joinpath('explorer.md').read_text()
CHALLENGER=Path(__file__).with_name('prompts').joinpath('challenger.md').read_text()

class Explorer:
    def __init__(self,provider,store,ledger):
        self.provider,self.store,self.ledger=provider,store,ledger
        self.trace=None; self.metadata=None
    async def select(self,context,*,reservation=None,challenge=False,fallback=None):
        # Supply the reviewed wire contract, not a sample solution or a repaired
        # recipe. Discovery and challenge use the same exact field names.
        context={**context,'output_schema':ExplorerOutput.model_json_schema()}
        messages=[{'role':'system','content':PROMPT+('\n'+CHALLENGER if challenge else '')},{'role':'user','content':canonical_json(context)}]
        validate_model_input(messages,(self.metadata or {}).get('model_id',context.get('model_id','openai/gpt-oss-120b')))
        self.ledger.consume_call(reservation=reservation)
        from app.lab.tracing import phase_span
        try:
            async with phase_span(self.trace,'select_experiment',self.metadata,{'challenge':challenge,'selection_index':context.get('selection_index',context.get('proposal_index'))}) as span:
                generation=await self.provider.complete(messages,role='explorer',max_output_tokens=2000,timeout_seconds=20)
                if span: span.set_output({'raw_proposal':generation.content})
        except RuntimeProviderError as error:
            if error.generation is not None: self.ledger.reconcile(error.generation)
            record_provider_failure(self.store,error,role='explorer',metadata=self.metadata or context)
            raise
        self.ledger.reconcile(generation)
        if self.metadata and generation.model_id!=self.metadata['model_id']:
            raise RuntimeProviderError('Provider returned a different frozen model')
        selection_id=new_id('selection'); parsed=None; error=None
        try: parsed=ExplorerOutput.model_validate_json(generation.content)
        except Exception: error='INVALID_EXPLORER_OUTPUT'
        self.store.put_record('selections',selection_id,{'selection_id':selection_id,'context':context,'raw':generation.content,'model_id':generation.model_id,'challenge':challenge,'valid':parsed is not None,'error':error,'provenance':'model' if parsed else 'fixed_invalid_output_fallback' if fallback else 'invalid_slot','output':parsed.model_dump(mode='json') if parsed else None,'usage':{'model_calls':1,'input_tokens':generation.input_tokens,'output_tokens':generation.output_tokens,'cost_dollars':generation.cost_usd}},immutable=True)
        if parsed is None and fallback is not None:
            parsed=ExplorerOutput(fault_spec=fallback,hypothesis='Fixed fallback after invalid Explorer output; no learned selection claim')
        return selection_id,parsed
