"""Minimal trusted context and optional LangChain Runnable, same invocation."""
from dataclasses import dataclass
from app.contracts.models import Provenance
from app.adapters.decorator import track_faultlab
from app.agents.actor import Actor

@dataclass
class EpisodeContext:
    provenance: Provenance
    broker: object
    interpreter: object
    provider: object
    policy: object
    policy_hash: str
    policy_decision: str
    metadata: dict
    trace: object=None
    lab_mode: bool=True
    adapter_id: str='orders/v1'

@track_faultlab(adapter_id='orders/v1')
async def run_prototype(task,context):
    return await Actor()(task,context)


def as_runnable(context):
    from langchain_core.runnables import RunnableLambda
    async def invoke(task): return await run_prototype(task,context)
    return RunnableLambda(invoke)
