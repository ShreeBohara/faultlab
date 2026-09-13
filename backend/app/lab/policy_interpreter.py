"""Finite reviewed hooks; no recursive dispatch or actor-report rewriting."""
from dataclasses import dataclass,field
from app.lab.policy_state import PolicyState
from app.lab.budgets import BudgetExhausted, StopRequested

@dataclass
class HookResult:
    blocked: bool=False
    final_requested: bool=False
    reasons: list[str]=field(default_factory=list)
    observations: list=field(default_factory=list)

class PolicyInterpreter:
    def __init__(self,policy,broker):
        self.policy,self.broker=policy,broker
        self.state=PolicyState(broker.journal)
        self.visited=set()

    async def invoke(self,hook,proposal_id,proposal=None):
        key=(hook,proposal_id)
        if key in self.visited: raise ValueError('Hook already invoked for proposal')
        self.visited.add(key)
        result=HookResult(); self.state.receipt_missing=False
        requirements=set(); start=len(self.broker.journal.observations)
        for rule in self.policy.rules:
            if rule.hook!=hook or not self.state.condition(rule.when): continue
            for step in rule.steps:
                self.broker.meter.take('policy_steps')
                execute=self.state.condition(step.only_if)
                self.broker.journal.store.append_event(self.broker.journal.episode_id,tick=self.broker.meter.usage.ticks,role='policy',type='policy_step',payload={'hook':hook,'op':step.op,'executed':execute})
                if not execute: continue
                op=step.op
                if op in ('read_current_operation','read_notification_operation'):
                    await self.broker.call('get_operation_status',{'service':'orders' if op=='read_current_operation' else 'notifications'},caller='policy',hook=hook)
                elif op=='read_order': await self.broker.call('get_order',caller='policy',hook=hook)
                elif op=='wait_ticks': await self.broker.wait_ticks(step.ticks)
                elif op=='retry_original_request':
                    receipt=self.state.receipt(step.service)
                    if receipt and receipt.status=='FAILED': result.reasons.append('POLICY_PRECONDITION_UNMET')
                    elif not self.state.attempted(step.service): result.reasons.append('POLICY_PRECONDITION_UNMET')
                    else: await self.broker.retry_original(step.service,hook=hook)
                elif op=='require_receipt':
                    requirements.add(step.service)
                    r=self.state.receipt(step.service)
                    self.state.receipt_missing=not (r and r.status=='SUCCEEDED')
                elif op=='report_terminal_failure':
                    r=self.state.receipt(step.service)
                    if not r or r.status!='FAILED': result.reasons.append('POLICY_PRECONDITION_UNMET')
                    else: result.final_requested=True
                elif op=='defer_unresolved': result.final_requested=True
                if result.final_requested:
                    self.broker.meter.business_closed=True
                    break
            if result.final_requested: break
        for service in requirements:
            r=self.state.receipt(service)
            if r and r.status=='SUCCEEDED': continue
            if hook=='before_confirmation': result.blocked=True
            if hook=='before_final_report' and proposal is not None:
                report=getattr(proposal,'report',proposal)
                claim=report.upgrade_outcome if service=='orders' else report.notification_outcome
                if claim=='SUCCEEDED': result.blocked=True
            result.reasons.append(f'RECEIPT_REQUIRED:{service}')
        result.observations=self.broker.journal.observations[start:]
        return result
