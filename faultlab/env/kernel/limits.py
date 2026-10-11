"""Per-world limits the kernel enforces. The defaults are the legacy simulator's."""

from pydantic import Field

from faultlab.core.model import StrictModel


class KernelLimits(StrictModel):
    http_attempts: int = Field(default=18, ge=1)     # admitted business requests per world
    ticks: int = Field(default=20, ge=1)             # logical ticks available to the agent
    waits: int = Field(default=4, ge=0)              # explicit waits per world
    wait_ticks: int = Field(default=4, ge=1)         # ticks per explicit wait
    horizon_ticks: int = Field(default=5, ge=1)      # the one observer advance after stop
    max_tick: int = Field(default=25, ge=1)          # ticks including the observer horizon
