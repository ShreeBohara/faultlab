"""FaultLab v2: the lab that proves what an acting agent actually did.

This package is the new home being built beside the legacy ``backend/app`` tree (strangler
refactor, plan Stage 1). Nothing here imports ``app``; the legacy tree stays importable and
every historical store stays readable through ``faultlab.evidence.legacy``.
"""

__version__ = "2.0.0a0"
