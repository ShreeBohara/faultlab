"""Persist only machine-safe provider diagnostics, never raw exceptions or text."""
from app.contracts.models import new_id


def record_provider_failure(store,error,*,role,metadata=None):
    metadata=metadata or {}
    # RuntimeProviderError constructs these values from explicit allowlists.
    # Copy only its reviewed scalar diagnostic fields; omit messages, headers,
    # response bodies, provider reasoning and any arbitrary exception attributes.
    supplied=error.diagnostics
    diagnostics={key:supplied.get(key) for key in ('code','error_class','http_status','finish_reason','input_tokens','output_tokens')}
    failure_id=new_id('provider-failure')
    store.put_record('provider_failures',failure_id,{'failure_id':failure_id,'role':role,'campaign_id':metadata.get('campaign_id'),'episode_id':metadata.get('episode_id'),'study_id':metadata.get('study_id'),'diagnostics':diagnostics},immutable=True)
    return failure_id


def record_transport_retry(store,error,*,role,failure_id,metadata=None,request=None,backoff=None):
    """Durable, visible record of one admitted Explorer/Mechanic transport retry.

    The retry was already charged on the campaign ledger. Only the failure's allowlisted
    code/status is kept, linked to its provider_failures record.

    ``backoff`` (rule v2, app.agents.transport_retry) is {'attempt','delay','campaign_retry_number'}:
    the record then carries rule v2's protocol, the attempt number (1-3), the wait before it and
    its number among the campaign's lab-role retries. Without it the record is exactly rule v1's.
    """
    from app.agents.transport_retry import (TRANSPORT_RETRY_PROTOCOL,TRANSPORT_RETRY_PROTOCOL_V2,
                                            LAB_RETRIES_PER_CAMPAIGN_MAX,backoff_payload,retry_payload)
    from app.contracts.models import utc_now
    metadata=metadata or {}
    retry_id=new_id('transport-retry')
    if backoff is None:
        facts={'retry_id':retry_id,**retry_payload(error),'provider_failure_id':failure_id}
        extra={'protocol':TRANSPORT_RETRY_PROTOCOL}
    else:
        facts={'retry_id':retry_id,**backoff_payload(error,backoff['attempt'],backoff['delay']),'provider_failure_id':failure_id}
        extra={'protocol':TRANSPORT_RETRY_PROTOCOL_V2,'campaign_retry_number':backoff['campaign_retry_number'],
               'campaign_retries_max':LAB_RETRIES_PER_CAMPAIGN_MAX}
    store.put_record('transport_retries',retry_id,{**facts,**extra,'role':role,
        'campaign_id':metadata.get('campaign_id'),'episode_id':metadata.get('episode_id'),
        'study_id':metadata.get('study_id'),'request':request or {},'charged_model_calls':1,
        'recorded_at':utc_now().isoformat()},immutable=True)
    return facts
