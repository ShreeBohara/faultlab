"""Policy knowledge is derived exclusively from delivered matching evidence."""
from app.contracts.models import OperationData

class PolicyState:
    def __init__(self,journal):
        self.journal=journal
        self.receipt_missing=False

    def receipt(self,service):
        i=self.journal.intent
        operation=i.upgrade_operation_id if service=='orders' else i.notification_operation_id
        intent_hash=i.upgrade_intent_hash if service=='orders' else i.notification_intent_hash
        for observation in self.journal.observations:
            data=observation.result.data
            if not isinstance(data,OperationData) or data.receipt is None or observation.result.transport!='ok': continue
            if (data.service,data.operation_id,data.order_id,data.intent_hash)!=(service,operation,i.order_id,intent_hash) or observation.result.status!=data.status or observation.result.receipt_id!=data.receipt.receipt_id: continue
            r=data.receipt
            if (r.service,r.operation_id,r.order_id,r.intent_hash)==(service,operation,i.order_id,intent_hash): return r
        return None

    def status(self,service):
        terminal=self.receipt(service)
        if terminal: return terminal.status
        i=self.journal.intent
        operation=i.upgrade_operation_id if service=='orders' else i.notification_operation_id
        for observation in reversed(self.journal.observations):
            r=observation.result
            if r.operation_id==operation: return r.status or 'UNKNOWN'
        return None

    def attempted(self,service):
        record=self.journal.original(service)
        return bool(record and record.attempt_ids)

    def condition(self,name):
        if name=='always': return True
        if name=='receipt_missing': return self.receipt_missing
        service='notifications' if name.startswith('notification') else 'orders'
        receipt=self.receipt(service); status=self.status(service)
        if name.endswith('receipt_missing'): return not (receipt and receipt.status=='SUCCEEDED')
        if name in ('current_operation_pending','notification_operation_pending'): return receipt is None and status=='PENDING'
        if name.endswith('outcome_uncertain'): return self.attempted(service) and receipt is None and status in ('PENDING','UNKNOWN',None)
        if name.endswith('terminal_failure'): return bool(receipt and receipt.status=='FAILED')
        if name.endswith('succeeded'): return bool(receipt and receipt.status=='SUCCEEDED')
        raise ValueError('Unknown policy condition')
