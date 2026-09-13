"""Async tracking preserves original returns/errors; no tracking on import."""
from functools import wraps
from app.contracts.models import content_hash


def track_faultlab(adapter_id='orders/v1'):
    def decorate(fn):
        @wraps(fn)
        async def tracked(task,context):
            if not context.lab_mode or context.adapter_id!=adapter_id: raise ValueError('Explicit registered mock adapter required')
            if content_hash(context.policy)!=context.policy_hash: raise ValueError('Frozen policy hash mismatch')
            if context.provenance.origin=='prototype' and context.policy_decision not in ('BASELINE','ACCEPTED'): raise ValueError('Prototype requires an accepted policy')
            if context.trace is None: return await fn(task,context)
            # Tracing defects cannot replace an original prototype exception or result.
            manager=context.trace.span('run_episode',context.metadata,{'task':task.model_dump(mode='json')})
            try: span=await manager.__aenter__()
            except Exception: return await fn(task,context)
            try:
                result=await fn(task,context)
            except BaseException as error:
                try: await manager.__aexit__(type(error),error,error.__traceback__)
                except BaseException: pass
                raise
            try:
                span.set_output({'report':result.model_dump(mode='json'),'terminal_status':'COMPLETED'})
                await manager.__aexit__(None,None,None)
            except Exception: pass
            return result
        return tracked
    return decorate
