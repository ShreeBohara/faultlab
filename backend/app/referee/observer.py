"""Fixed observer horizon. Snapshots never become delivered actor observations."""
from dataclasses import dataclass
from app.contracts.models import WorldSnapshot

@dataclass(frozen=True)
class ObservationHorizon:
    decision:WorldSnapshot
    horizon:WorldSnapshot

async def observe(control_client,world_id):
    """Control client implements async stop/snapshot/advance(world_id,ticks,observer)."""
    await control_client.stop(world_id)
    decision=await control_client.snapshot(world_id)
    await control_client.advance(world_id,5,observer=True)
    horizon=await control_client.snapshot(world_id)
    return ObservationHorizon(decision,horizon)
