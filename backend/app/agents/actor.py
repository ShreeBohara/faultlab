"""Competent typed prototype. Every answer remains authored by this model."""
from pathlib import Path
from app.contracts.tokens import validate_model_input
import json
from pydantic import TypeAdapter,ValidationError
from app.contracts.models import ActorAction, ReportAction, canonical_json, new_id, content_hash
from app.lab.budgets import BudgetExhausted
from app.providers.runtime import RuntimeProviderError
from app.lab.provider_failures import record_provider_failure

ACTOR_PROMPT=Path(__file__).with_name('prompts').joinpath('actor.md').read_text()
ACTOR_PROMPT_HASH=content_hash(ACTOR_PROMPT)
ACTION_ADAPTER=TypeAdapter(ActorAction)

class ActorReportError(ValueError):
    pass

class Actor:
    async def __call__(self,intent,context):
        broker=context.broker; meter=broker.meter; interpreter=context.interpreter
        messages=[{'role':'system','content':ACTOR_PROMPT},{'role':'user','content':canonical_json({'task':intent.model_dump(mode='json')})}]
        cost_known=True; measured_cost=0.0
        def account(generation):
            nonlocal cost_known,measured_cost
            if generation.input_tokens is not None: meter.usage.input_tokens+=generation.input_tokens
            if generation.output_tokens is not None: meter.usage.output_tokens+=generation.output_tokens
            if generation.cost_usd is None: cost_known=False
            else: measured_cost+=generation.cost_usd
            meter.usage.cost_dollars=measured_cost if cost_known else None
            if meter.campaign: meter.campaign.reconcile(generation)
        while meter.usage.actor_calls<meter.caps.actor_calls:
            final=meter.final_turn
            # All delivered observations are retained. Reject excess input, never omit contradictory evidence.
            user={'observations':[o.model_dump(mode='json') for o in broker.journal.observations],'final_report_required':final,'remaining_actor_calls':meter.caps.actor_calls-meter.usage.actor_calls}
            call_messages=messages+[{'role':'user','content':canonical_json(user)}]
            validate_model_input(call_messages,context.metadata['model_id'])
            meter.model_call()
            try:
                generation=await context.provider.complete(call_messages,role='actor',max_output_tokens=2000,timeout_seconds=min(20,max(.01,meter.caps.wall_seconds-meter.usage.wall_seconds)))
            except RuntimeProviderError as error:
                if error.generation is not None: account(error.generation)
                record_provider_failure(broker.journal.store,error,role='actor',metadata=context.metadata)
                raise
            account(generation)
            if generation.model_id!=context.metadata['model_id']:
                raise RuntimeProviderError('Provider returned a different frozen model')
            try: action=ACTION_ADAPTER.validate_json(generation.content)
            except (ValidationError,ValueError):
                messages.append({'role':'user','content':'Invalid action JSON. Return exactly one allowed tool or report action. This correction consumes a turn.'})
                continue
            proposal_id=new_id('proposal')
            if isinstance(action,ReportAction):
                hook=await interpreter.invoke('before_final_report',proposal_id,action)
                if hook.blocked:
                    messages.append({'role':'user','content':canonical_json({'blocked_report':hook.reasons})})
                    continue
                # Reference violations are scored on the original report; never repair or drop invalid citations.
                broker.journal.store.append_event(broker.journal.episode_id,tick=meter.usage.ticks,role='actor',type='report_submitted',payload={'report':action.report.model_dump(mode='json')})
                return action.report
            if final:
                messages.append({'role':'user','content':'A report was required on the reserved final turn; no business call executed.'})
                continue
            if action.tool=='send_confirmation':
                hook=await interpreter.invoke('before_confirmation',proposal_id,action)
                if hook.blocked or hook.final_requested:
                    messages.append({'role':'user','content':canonical_json({'blocked_action':hook.reasons,'final_report_required':hook.final_requested})})
                    continue
            try:
                await broker.call(action.tool,action.arguments.model_dump())
                if action.tool=='update_order': await interpreter.invoke('after_upgrade_response',proposal_id,action)
                elif action.tool=='send_confirmation': await interpreter.invoke('after_notification_response',proposal_id,action)
            except BudgetExhausted:
                meter.business_closed=True
                messages.append({'role':'user','content':'Business budget exhausted. Return your truthful final report from existing observations.'})
        raise ActorReportError('No valid original report within actor limit')
