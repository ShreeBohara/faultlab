"""Original bytes and identities persist before first write dispatch."""
from app.contracts.models import TaskIntent, OperationJournal, PublicObservation, canonical_json, content_hash, new_id


def allocate_intent(order_id,task_text,expected_version=1):
    task_id=new_id('task'); upgrade=new_id('upgrade'); notification=new_id('notify')
    up=content_hash({'task_id':task_id,'order_id':order_id,'desired_shipping':'express','expected_version':expected_version,'operation_id':upgrade})
    notify=content_hash({'task_id':task_id,'order_id':order_id,'upgrade_operation_id':upgrade,'operation_id':notification,'template_version':'confirmation/v1'})
    return TaskIntent(task_id=task_id,order_id=order_id,expected_version=expected_version,upgrade_operation_id=upgrade,notification_operation_id=notification,upgrade_idempotency_key=new_id('key'),notification_idempotency_key=new_id('key'),upgrade_intent_hash=up,notification_intent_hash=notify,task_text=task_text)


class Journal:
    def __init__(self,store,episode_id,intent):
        self.store,self.episode_id,self.intent=store,episode_id,intent
        self.observations=[]

    def original(self, service):
        operation_id=self.intent.upgrade_operation_id if service=='orders' else self.intent.notification_operation_id
        return self.store.get_model('journals',f'{self.episode_id}:{operation_id}',OperationJournal)

    def prepare(self,service,payload):
        original=self.original(service)
        encoded=canonical_json(payload)
        if original:
            if original.original_request!=encoded: raise ValueError('Original intent bytes cannot change')
            return original
        intent_hash=self.intent.upgrade_intent_hash if service=='orders' else self.intent.notification_intent_hash
        record=OperationJournal(episode_id=self.episode_id,operation_id=payload['operation_id'],service=service,intent_hash=intent_hash,payload_hash=content_hash(payload),original_request=encoded,attempt_ids=[],latest_status=None,terminal_receipt_id=None)
        self.store.put_record('journals',f'{self.episode_id}:{record.operation_id}',record)
        return record

    def attempt(self,service,attempt_id):
        record=self.original(service)
        if record is None: raise ValueError('Write intent missing before dispatch')
        record.attempt_ids.append(attempt_id)
        self.store.put_record('journals',f'{self.episode_id}:{record.operation_id}',record)

    def deliver(self,result,tick):
        data=result.data
        observation=PublicObservation(evidence_id=new_id('evidence'),episode_id=self.episode_id,call_id=result.call_id,delivered_tick=tick,result=result,observed_operation_id=getattr(data,'operation_id',None),observed_order_id=getattr(data,'order_id',None),observed_intent_hash=getattr(data,'intent_hash',None),source_receipt_id=result.receipt_id)
        self.observations.append(observation)
        self.store.put_record('observations',observation.evidence_id,observation,immutable=True)
        self.store.append_event(self.episode_id,tick=tick,role='actor',type='observation_delivered',payload={'observation':observation.model_dump(mode='json')},call_id=result.call_id,evidence_id=observation.evidence_id)
        return observation

    def validate_report_references(self,report):
        allowed={o.evidence_id for o in self.observations}
        if not set(report.evidence_ids)<=allowed: raise ValueError('Report references undelivered evidence')
        action=report.next_action
        if action.kind=='CHECK_EXISTING_UPGRADE' and action.operation_id!=self.intent.upgrade_operation_id: raise ValueError('Foreign upgrade operation')
        if action.kind=='CHECK_EXISTING_NOTIFICATION' and action.operation_id!=self.intent.notification_operation_id: raise ValueError('Foreign notification operation')
