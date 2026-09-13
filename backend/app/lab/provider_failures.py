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
