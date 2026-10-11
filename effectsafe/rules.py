"""The bounded recovery-rule language and its interpreter (from the lab's policy DSL).

A policy is a list of rules; a rule fires at one *hook* (a named point in a workflow, declared
by the pack or the integration) when a *condition* about one operation holds, and runs a short
list of *steps*. Steps are the only side effects a rule can have, every step is bounded by the
caller's limits, and no step rewrites the agent's own report: a rule may block a dependent
write, request a status read or a wait, resend the pinned bytes, require a receipt, or ask the
workflow to end unresolved or with a terminal failure.

Conditions are evaluated against the journal only (delivered evidence), never against the
agent's beliefs. This is the legacy ``PolicyState``/``PolicyInterpreter`` made generic over
operation names and hook names.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from effectsafe.journal import Journal

Condition = Literal["always", "receipt_missing", "pending", "outcome_uncertain", "terminal_failure", "succeeded"]
Op = Literal["read_status", "wait", "retry_original", "require_receipt", "report_terminal_failure", "defer_unresolved"]
MAX_STEPS_PER_HOOK = 32


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    op: Op
    operation: str | None = None                 # which operation the step is about (not for wait/defer)
    ticks: int | None = Field(default=None, ge=1, le=20)
    only_if: Condition = "always"

    @model_validator(mode="after")
    def shape(self):
        needs_operation = self.op in ("read_status", "retry_original", "require_receipt", "report_terminal_failure")
        if needs_operation and not self.operation:
            raise ValueError(f"{self.op} names an operation")
        if self.op == "wait" and self.ticks is None:
            raise ValueError("wait needs ticks")
        if self.only_if != "always" and not self.operation and self.op in ("wait", "defer_unresolved"):
            raise ValueError("a conditional wait or defer names the operation its condition is about")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    hook: str = Field(min_length=1, max_length=80)
    operation: str = Field(min_length=1, max_length=120)      # the operation the condition is about
    when: Condition = "always"
    steps: tuple[Step, ...] = Field(min_length=1, max_length=8)


class RulePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: str = Field(min_length=1, max_length=80)
    rules: tuple[Rule, ...] = Field(default=(), max_length=16)


class Executor(Protocol):
    """What the workflow lends the interpreter: the three bounded actions a rule may take."""
    async def read_status(self, operation: str) -> None: ...
    async def wait(self, ticks: int) -> None: ...
    async def resend(self, operation: str) -> None: ...


class HookResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    blocked: bool = False
    final_requested: bool = False
    reasons: list[str] = Field(default_factory=list)
    steps_run: list[str] = Field(default_factory=list)


def _state(journal: Journal, operation: str):
    try:
        return journal.operation(operation)["state"]
    except Exception:
        return None


def holds(journal: Journal, operation: str, condition: Condition) -> bool:
    """A condition about one operation, read from delivered evidence only."""
    if condition == "always":
        return True
    state = _state(journal, operation)
    if state is None:
        return condition in ("receipt_missing",)
    if condition == "receipt_missing":
        return state.outcome != "SUCCEEDED"
    if condition == "pending":
        return state.outcome == "PENDING"
    if condition == "outcome_uncertain":
        return state.attempts > 0 and state.outcome in ("UNKNOWN", "PENDING")
    if condition == "terminal_failure":
        return state.outcome == "FAILED"
    if condition == "succeeded":
        return state.outcome == "SUCCEEDED"
    raise ValueError("Unknown condition")


class Interpreter:
    def __init__(self, policy: RulePolicy, journal: Journal, executor: Executor, *, step_budget: int = MAX_STEPS_PER_HOOK):
        self.policy, self.journal, self.executor = policy, journal, executor
        self.step_budget = step_budget
        self.steps_used = 0
        self.visited: set[tuple[str, str]] = set()

    async def invoke(self, hook: str, proposal_id: str, *, claims: dict | None = None) -> HookResult:
        """Run every rule of ``hook`` once for this proposal; a hook never re-enters for the same proposal."""
        key = (hook, proposal_id)
        if key in self.visited:
            raise ValueError("Hook already invoked for proposal")
        self.visited.add(key)
        result = HookResult()
        requirements: list[str] = []
        for rule in self.policy.rules:
            if rule.hook != hook or not holds(self.journal, rule.operation, rule.when):
                continue
            for step in rule.steps:
                if self.steps_used >= self.step_budget:
                    result.reasons.append("STEP_BUDGET_EXHAUSTED")
                    result.final_requested = True
                    break
                self.steps_used += 1
                target = step.operation or rule.operation
                if not holds(self.journal, target, step.only_if):
                    continue
                result.steps_run.append(f"{step.op}:{target}" if step.operation else step.op)
                if step.op == "read_status":
                    await self.executor.read_status(target)
                elif step.op == "wait":
                    await self.executor.wait(step.ticks)
                elif step.op == "retry_original":
                    state = _state(self.journal, target)
                    if state is None or state.attempts == 0 or state.outcome == "FAILED":
                        result.reasons.append("POLICY_PRECONDITION_UNMET")
                    else:
                        await self.executor.resend(target)
                elif step.op == "require_receipt":
                    requirements.append(target)
                elif step.op == "report_terminal_failure":
                    state = _state(self.journal, target)
                    if state is None or state.outcome != "FAILED":
                        result.reasons.append("POLICY_PRECONDITION_UNMET")
                    else:
                        result.final_requested = True
                elif step.op == "defer_unresolved":
                    result.final_requested = True
                if result.final_requested:
                    break
            if result.final_requested:
                break
        for operation in requirements:
            state = _state(self.journal, operation)
            if state is not None and state.outcome == "SUCCEEDED":
                continue
            # A missing receipt blocks the dependent write, and blocks a success claim about it.
            if claims is None or claims.get(operation) == "SUCCEEDED":
                result.blocked = True
            result.reasons.append(f"RECEIPT_REQUIRED:{operation}")
        return result
