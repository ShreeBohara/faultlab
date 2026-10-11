"""effectsafe: the runtime action layer for agents that act on the world.

An agent's write becomes an *operation* with a pinned identity and exact original bytes
(``intent``), every dispatch is journalled before it touches the wire (``journal``), what came
back is reconciled into an outcome lattice where uncertainty never silently decays
(``outcome``), and a bounded recovery-rule language decides what may happen next (``rules``).

This package never imports ``faultlab``; the lab imports it. Extracted from the legacy broker
(``backend/app/adapters/journal.py``, ``business_tools.py``, ``app/lab/policy_interpreter.py``).
"""

from effectsafe.contract import ToolContract
from effectsafe.intent import Intent, canonical_json, derive_key, digest
from effectsafe.journal import Journal, JournalError, UnsafeResend
from effectsafe.outcome import CONFLICT, FAILED, NOT_STARTED, PENDING, SUCCEEDED, UNKNOWN, Evidence, OperationState, reconcile
from effectsafe.rules import HookResult, Interpreter, Rule, RulePolicy, Step

__version__ = "0.1.0a0"
__all__ = ["CONFLICT", "FAILED", "NOT_STARTED", "PENDING", "SUCCEEDED", "UNKNOWN", "Evidence", "HookResult", "Intent",
           "Interpreter", "Journal", "JournalError", "OperationState", "Rule", "RulePolicy", "Step", "ToolContract",
           "UnsafeResend", "canonical_json", "derive_key", "digest", "reconcile"]
