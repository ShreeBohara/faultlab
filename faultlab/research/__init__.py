"""The research track (plan stage 4) on the v2 lab. Nothing here imports the legacy ``backend/app``."""

from faultlab.research.mechanic import (MECHANIC_ID, RULE_LANGUAGE, ClaudeCodeMechanic, Proposal, ScriptedMechanic,
                                        counterexample_view)
from faultlab.research.repair_study import SCHEMA, RepairStudy, RepairStudyDesign, summarize_trial
from faultlab.research.unseen_study import UnseenStudy, UnseenStudyDesign

__all__ = ["MECHANIC_ID", "RULE_LANGUAGE", "SCHEMA", "ClaudeCodeMechanic", "Proposal", "RepairStudy", "RepairStudyDesign",
           "ScriptedMechanic", "UnseenStudy", "UnseenStudyDesign", "counterexample_view", "summarize_trial"]
