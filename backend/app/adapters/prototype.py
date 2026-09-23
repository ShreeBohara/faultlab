"""Minimal trusted context and optional LangChain Runnable, same invocation."""
from dataclasses import dataclass, field
from app.contracts.models import Provenance
from app.adapters.decorator import track_faultlab
from app.agents.actor import Actor
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V1

@dataclass
class ReportCompletion:
    # Native adapters shallow-copy EpisodeContext. Both contexts must retain the
    # same original return and timing boundary through telemetry finalization.
    report: object=None
    wall_seconds: float|None=None

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
    # Which per-turn Actor context protocol this episode runs. One frozen source
    # serves every arm; the chosen version is recorded with the saved evidence.
    actor_context_protocol: str=ACTOR_CONTEXT_PROTOCOL_V1
    _completion: ReportCompletion=field(default_factory=ReportCompletion)

    @property
    def returned_report(self): return self._completion.report

    @property
    def report_completed_wall_seconds(self): return self._completion.wall_seconds

    def complete_report(self, report):
        """Retain the actual return before bounded telemetry-only cleanup."""
        from app.lab.budgets import BudgetExhausted
        from app.telemetry.tracing import complete_episode_work
        meter=self.broker.meter
        meter.check()
        if report is None: return
        if not complete_episode_work():
            raise BudgetExhausted('Episode deadline exhausted')
        self._completion.report=report
        self._completion.wall_seconds=meter.usage.wall_seconds
        meter.business_closed=True

@track_faultlab(adapter_id='orders/v1')
async def run_prototype(task,context):
    return await Actor()(task,context)


def as_runnable(context):
    from langchain_core.runnables import RunnableLambda
    async def invoke(task): return await run_prototype(task,context)
    return RunnableLambda(invoke)
