"""Competent typed prototype. Every answer remains authored by this model."""
from pathlib import Path
import json
from pydantic import TypeAdapter,ValidationError
from app.contracts.models import ActorAction, ReportAction, canonical_json, new_id, content_hash
from app.lab.budgets import BudgetExhausted
from app.providers.runtime import (RuntimeProviderError, validate_request_input, response_format_for,
                                   ACTOR_RESPONSE_PROTOCOL_VERSION, actor_response_protocol)
from app.agents.progress import (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOLS,
                                 INDEXED_EVIDENCE_PROTOCOLS, actor_context_protocol,
                                 decode_citations, evidence_labels, turn_message)
from app.lab.provider_failures import record_provider_failure

# Codes that mean no generation was received. Retrying these is blind: nothing was
# observed, so nothing can be selected on. Deliberately excludes EMPTY_FINAL_RESPONSE.
RETRYABLE_TRANSPORT_CODES=('CONNECTION_ERROR','REQUEST_TIMEOUT')

ACTOR_PROMPT=Path(__file__).with_name('prompts').joinpath('actor.md').read_text()
ACTOR_PROMPT_HASH=content_hash(ACTOR_PROMPT)
ACTION_ADAPTER=TypeAdapter(ActorAction)

class ActorReportError(ValueError):
    pass

class Actor:
    async def __call__(self,intent,context):
        broker=context.broker; meter=broker.meter; interpreter=context.interpreter
        # One frozen source serves both comparison arms. v1 rebuilds the preserved
        # turn message byte for byte; v2 adds only already-public attempt facts.
        protocol=getattr(context,'actor_context_protocol',None) or ACTOR_CONTEXT_PROTOCOL_V1
        if protocol not in ACTOR_CONTEXT_PROTOCOLS: raise ValueError('Unknown actor context protocol')
        context_descriptor=actor_context_protocol(protocol)
        messages=[{'role':'system','content':ACTOR_PROMPT},{'role':'user','content':canonical_json({'task':intent.model_dump(mode='json'),'output_schema':ACTION_ADAPTER.json_schema()})}]
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
            user=turn_message([o.model_dump(mode='json') for o in broker.journal.observations],
                              final_report_required=final,
                              remaining_actor_calls=meter.caps.actor_calls-meter.usage.actor_calls,
                              protocol=protocol,journal=broker.journal,logical_calls=getattr(broker,'logical_calls',()))
            call_messages=messages+[{'role':'user','content':canonical_json(user)}]
            response_contract='actor_final_report' if final else None
            response_format=response_format_for(response_contract=response_contract)
            validate_request_input(call_messages,context.metadata['model_id'],response_contract=response_contract)
            generation=None
            for transport_attempt in range(2):
                # One turn costs one actor call. A blind retry of a call that delivered
                # no generation is admitted separately and does not spend a turn.
                if transport_attempt==0: meter.model_call()
                try:
                    generation=await context.provider.complete(call_messages,role='actor',max_output_tokens=2000,timeout_seconds=min(20,max(.01,meter.caps.wall_seconds-meter.usage.wall_seconds)),response_contract=response_contract)
                    break
                except RuntimeProviderError as error:
                    if error.generation is not None: account(error.generation)
                    record_provider_failure(broker.journal.store,error,role='actor',metadata=context.metadata)
                    # A transport failure delivered no generation, so there is nothing to
                    # look at and nothing to select on: the retry is blind. That is why it
                    # is restricted to codes meaning "no response arrived", and why an
                    # EMPTY_FINAL_RESPONSE - a response that did arrive - is not retried.
                    # The retry is charged in dollars and model calls but not in actor
                    # turns, so it still fires on the final allowed turn - the turn that
                    # carries the report, and the one Phase 13 measured losing an episode.
                    # meter.transport_retry() returns False rather than raising, so a
                    # retry never substitutes a budget error for the transport failure.
                    if (transport_attempt==0 and error.code in RETRYABLE_TRANSPORT_CODES
                            and meter.transport_retry()):
                        broker.journal.store.append_event(broker.journal.episode_id,tick=meter.usage.ticks,role='actor',type='actor_transport_retry',payload={'code':error.code,'attempt':transport_attempt+1})
                        continue
                    raise
            account(generation)
            if generation.model_id!=context.metadata['model_id']:
                raise RuntimeProviderError('Provider returned a different frozen model')
            # Preserve the provider-redacted final content before validation.
            # This is local supplemental evidence, not a submitted report or
            # remotely verified observation. It never changes the next request.
            broker.journal.store.append_event(broker.journal.episode_id,
                tick=meter.usage.ticks,role='actor',type='actor_output',payload={
                    'source':'local_actor_output','actor_turn':meter.usage.actor_calls,
                    'request_hash':content_hash({'messages':call_messages,'response_format':response_format}),
                    'messages_hash':content_hash(call_messages),
                    'actor_response_protocol':ACTOR_RESPONSE_PROTOCOL_VERSION,
                    'actor_response_protocol_hash':content_hash(actor_response_protocol()),
                    'actor_context_protocol':protocol,
                    'actor_context_protocol_hash':context_descriptor['descriptor_hash'],
                    'response_contract':response_contract,
                    'response_format_hash':content_hash(response_format),
                    'final_report_required':final,
                    'remaining_actor_calls_at_request':user['remaining_actor_calls'],
                    'delivered_evidence_ids':[o.evidence_id for o in broker.journal.observations],
                    'raw':generation.content})
            try: action=ACTION_ADAPTER.validate_json(generation.content)
            except (ValidationError,ValueError) as error:
                errors=([{'location':list(issue['loc']),'type':issue['type']}
                         for issue in error.errors(include_input=False,include_context=False,include_url=False)]
                        if isinstance(error,ValidationError) else [{'location':[],'type':'invalid_json'}])
                # RuntimeProvider has already redacted credentials. Preserve the
                # actual invalid answer, never substitute a repaired action.
                messages.extend([{'role':'assistant','content':generation.content},
                                 {'role':'user','content':canonical_json({'action_errors':errors,'instruction':'Your action failed output_schema. Return exactly one allowed tool or report action with only its declared fields. No business call was executed; this correction consumes a turn.'})}])
                continue
            proposal_id=new_id('proposal')
            if isinstance(action,ReportAction):
                hook=await interpreter.invoke('before_final_report',proposal_id,action)
                if hook.blocked:
                    messages.append({'role':'user','content':canonical_json({'blocked_report':hook.reasons})})
                    continue
                # Reference violations are scored on the original report; never repair or drop invalid citations.
                # Under an indexed-evidence protocol the Actor writes labels for observations it
                # was shown; decoding them is parsing the declared alphabet, not repairing. The
                # decode is total and exact-match only, and an unmatched token passes through
                # verbatim so it still fails C6. Both forms are retained below.
                emitted=action.report
                if protocol in INDEXED_EVIDENCE_PROTOCOLS:
                    rows=[o.model_dump(mode='json') for o in broker.journal.observations]
                    action=action.model_copy(update={'report':emitted.model_copy(update={
                        'evidence_ids':decode_citations(emitted.evidence_ids,rows)})})
                payload={'report':action.report.model_dump(mode='json')}
                if action.report is not emitted:
                    payload.update(emitted_report=emitted.model_dump(mode='json'),
                                   citation_protocol=protocol,
                                   evidence_labels=evidence_labels(rows))
                broker.journal.store.append_event(broker.journal.episode_id,tick=meter.usage.ticks,role='actor',type='report_submitted',payload=payload)
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
