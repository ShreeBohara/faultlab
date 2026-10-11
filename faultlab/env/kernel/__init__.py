"""The task-agnostic world kernel (plan phase 1.2).

A world is one SQLite file holding an atomic state row plus append-only histories protected
by SQL triggers. The kernel owns admission, the logical clock, attempt and wait budgets,
fault placement by ``(tool, service, occurrence)`` with honest trigger accounting, the event
log and the loopback control API. A ``WorldHandler`` (a task pack) owns the business state
transitions: what a tool does, which histories it keeps, what a snapshot shows.

This is a new implementation beside ``backend/app/simulator``; that module is left byte for
byte as it is because its identity (``service_hash``) is pinned by every earlier export.
"""

from faultlab.env.kernel.app import create_app
from faultlab.env.kernel.dispatch import DispatchContext, dispatch
from faultlab.env.kernel.errors import WorldError
from faultlab.env.kernel.faults import FaultSpec, Primitive, matching, prevented, trigger
from faultlab.env.kernel.handler import WorldHandler
from faultlab.env.kernel.limits import KernelLimits
from faultlab.env.kernel.storage import WorldStore, event

__all__ = ["DispatchContext", "FaultSpec", "KernelLimits", "Primitive", "WorldError", "WorldHandler", "WorldStore",
           "create_app", "dispatch", "event", "matching", "prevented", "trigger"]
