"""Manual UI capture records real observed pointers, never invokes or fetches URLs."""
from datetime import datetime
from pydantic import field_validator,Field
from urllib.parse import urlsplit
from typing import Literal
from app.contracts.models import StrictModel,Id,AriaAnalysis,new_id

class AriaEvidenceRequest(StrictModel):
    run_id:Id
    automation_id:Id
    invocation_mode:Literal['automatic','manual']
    provenance:Literal['manual_ui_capture']='manual_ui_capture'
    status:Literal['PENDING','UNVERIFIED','COMPLETED','FAILED']
    execution_id:Id|None=None
    observed_at:datetime
    thread_id:Id|None=None
    history_url:str|None=None
    output_url:str|None=None
    summary:str=Field(max_length=600)
    recorder:str=Field(min_length=1,max_length=600)

    @field_validator('observed_at',mode='before')
    @classmethod
    def parse_observed_at(cls,value):
        if isinstance(value,str):
            try: return datetime.fromisoformat(value.replace('Z','+00:00'))
            except ValueError: raise ValueError('UTC timestamp required') from None
        return value


def save_aria_evidence(coordinator,campaign_id,request):
    campaign=coordinator.get(campaign_id)
    binding=coordinator.store.get_record('aria_bindings',campaign_id)
    if not binding or binding.get('run_id')!=request.run_id or binding.get('automation_id')!=request.automation_id:
        raise ValueError('Observed run/automation must match the registered campaign binding')
    for value in (request.history_url,request.output_url):
        if value is None: continue
        url=urlsplit(value)
        if url.scheme!='https' or url.hostname not in ('wandb.ai','weave.wandb.ai') or url.username or url.password or url.port not in (None,443) or not url.path.strip('/'):
            raise ValueError('An actual allowlisted HTTPS W&B evidence link is required')
    status=request.status
    if status=='COMPLETED' and (request.invocation_mode!='automatic' or not all((request.execution_id,request.history_url,request.output_url,request.summary.strip(),request.thread_id))):
        raise ValueError('Automatic completion requires observed execution, history, thread and analysis output')
    # Pasted pointers are attributed capture, not independent remote verification.
    record=AriaAnalysis(analysis_id=new_id('aria'),campaign_id=campaign_id,**request.model_dump(),verified_source_refs=binding.get('verified_source_refs',[]))
    from app.telemetry.aria_bridge import validate_analysis_capture
    checked=validate_analysis_capture(record,campaign_run=binding,automation_id=binding['automation_id'])
    coordinator.store.put_record('aria_capture_checks',record.analysis_id,checked,immutable=True)
    coordinator.store.put_record('aria',record.analysis_id,record,immutable=True)
    campaign.aria_status=status; coordinator.save(campaign)
    return record
