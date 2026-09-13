"""B1: handwritten operation-aware reference, never a learned-policy substitute."""
from app.contracts.models import TaskReport, NoNextAction, CheckNextAction
from app.lab.policy_state import PolicyState
from app.lab.budgets import BudgetExhausted

class ReferenceActor:
    async def __call__(self,intent,context):
        broker=context.broker; state=PolicyState(broker.journal)
        async def resolve(service):
            while not state.receipt(service):
                try:
                    await broker.call('get_operation_status',{'service':service})
                    if state.receipt(service): break
                    if broker.meter.usage.wait_cycles>=broker.meter.caps.wait_cycles: break
                    remaining=broker.meter.caps.ticks-broker.meter.usage.ticks
                    if remaining<=0: break
                    if state.status(service)=='UNKNOWN' and state.attempted(service):
                        await broker.retry_original(service,hook='after_notification_response' if service=='notifications' else 'after_upgrade_response')
                        if state.receipt(service): break
                    remaining=broker.meter.caps.ticks-broker.meter.usage.ticks
                    if remaining<=0: break
                    await broker.wait_ticks(min(4,remaining))
                except BudgetExhausted: break
            return state.receipt(service)
        try:
            await broker.call('get_order')
            await broker.call('update_order',{'desired_shipping':'express'})
            upgrade=state.receipt('orders') or await resolve('orders')
            if upgrade and upgrade.status=='SUCCEEDED':
                await broker.call('send_confirmation')
                await resolve('notifications')
        except BudgetExhausted:
            pass
        upgrade=state.receipt('orders'); notify=state.receipt('notifications')
        us=upgrade.status if upgrade else state.status('orders') or 'NOT_STARTED'
        ns=notify.status if notify else state.status('notifications') or 'NOT_STARTED'
        if us=='FAILED': overall='CORRECTLY_REJECTED'; ns='NOT_REQUIRED'; nxt=NoNextAction(kind='NONE')
        elif us==ns=='SUCCEEDED': overall='COMPLETED'; nxt=NoNextAction(kind='NONE')
        else:
            overall='SAFE_UNRESOLVED'
            service='notifications' if us=='SUCCEEDED' and state.attempted('notifications') else 'orders'
            nxt=CheckNextAction(kind='CHECK_EXISTING_NOTIFICATION' if service=='notifications' else 'CHECK_EXISTING_UPGRADE',operation_id=intent.notification_operation_id if service=='notifications' else intent.upgrade_operation_id)
        return TaskReport(upgrade_outcome=us,notification_outcome=ns,overall=overall,evidence_ids=[o.evidence_id for o in broker.journal.observations],next_action=nxt)
