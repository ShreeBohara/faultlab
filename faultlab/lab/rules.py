"""Recovery rules on a trial session: effectsafe rules at the lab's report gate.

An adapter may be given a ``RulePolicy``. The policy is part of the agent's recorded configuration
(it changes the adapter's settings digest, so a trial with a policy never shares a plan with one
without) and its body is recorded as the first rule-step event of every trial that carries it.
This slice runs rules at one hook, ``before_final_report``, with the ``report`` gate: a rule may
read a status, wait, resend the pinned bytes of a write, require a receipt or a label, or ask for
a terminal report, and the hook's result either lets the agent's report through unchanged or blocks
it with reasons the agent is shown. Nothing here rewrites a report; the referee and the oracle
score only what was submitted. A policy with rules at any other hook is refused before any trial.

Rules name operations by the pack's aliases (``upgrade`` and ``notification`` for the orders
pack); the aliases resolve to the trial's own operation ids through its intent.
"""

from __future__ import annotations

from typing import Any

from effectsafe import HookResult, Interpreter, RulePolicy
from faultlab.core import canonical_json, content_hash

REPORT_HOOK = "before_final_report"
SUPPORTED_HOOKS = (REPORT_HOOK,)
REQUIRED_ALIAS_KEYS = ("intent_key", "service", "write_tool", "status_tool", "claim")


class RuleError(ValueError):
    """A policy this adapter cannot run as declared: an unsupported hook, an unknown alias or claim."""


def policy_from_json(value: Any) -> RulePolicy:
    """A policy from JSON text, a JSON value or an existing policy; strict, closed, validated."""
    if isinstance(value, RulePolicy):
        return value
    text = value if isinstance(value, str) else canonical_json(value)
    return RulePolicy.model_validate_json(text)


def policy_digest(policy: RulePolicy) -> str:
    return content_hash(policy.model_dump(mode="json"))


def check_policy(policy: RulePolicy, pack) -> None:
    """Refuse a policy that names a hook this slice does not run, an alias the pack lacks, or an unknown claim."""
    aliases = pack.operation_aliases
    if not aliases:
        raise RuleError(f"pack {pack.pack_id} declares no operation aliases; rules cannot name its operations")
    claims = set(pack.report_model.model_fields)
    for rule in policy.rules:
        if rule.hook not in SUPPORTED_HOOKS:
            raise RuleError(f"hook {rule.hook!r} is not run at the report gate; supported: {', '.join(SUPPORTED_HOOKS)}")
        if rule.operation not in aliases:
            raise RuleError(f"unknown operation alias {rule.operation!r}; known: {', '.join(sorted(aliases))}")
        for step in rule.steps:
            if step.operation is not None and step.operation not in aliases:
                raise RuleError(f"unknown operation alias {step.operation!r}; known: {', '.join(sorted(aliases))}")
            if step.op == "require_label" and step.claim not in claims:
                raise RuleError(f"unknown report claim {step.claim!r}; known: {', '.join(sorted(claims))}")


def resolve_policy(policy: RulePolicy, pack, intent: dict) -> RulePolicy:
    """The same policy with the pack's operation aliases replaced by this trial's operation ids."""
    def operation_id(alias: str) -> str:
        return str(intent[pack.operation_aliases[alias]["intent_key"]])
    rules = []
    for rule in policy.rules:
        steps = tuple(step.model_copy(update={"operation": operation_id(step.operation)}) if step.operation else step
                      for step in rule.steps)
        rules.append(rule.model_copy(update={"operation": operation_id(rule.operation), "steps": steps}))
    return policy.model_copy(update={"rules": tuple(rules)})


class SessionExecutor:
    """The three bounded actions a rule may take, done through the session so they are journalled and shown."""

    def __init__(self, session, pack, hook: str):
        self.session, self.pack, self.hook = session, pack, hook
        self.by_operation = {str(session.intent[spec["intent_key"]]): spec for spec in pack.operation_aliases.values()}

    async def read_status(self, operation: str) -> None:
        spec = self.by_operation[operation]
        await self.session.call(spec["status_tool"], {"service": spec["service"], "operation_id": operation}, caller="rule", hook=self.hook)

    async def wait(self, ticks: int) -> None:
        await self.session.wait(ticks, caller="rule", hook=self.hook)

    async def resend(self, operation: str) -> None:
        recorded = next((call for call in reversed(self.session.calls) if call["operation_id"] == operation), None)
        if recorded is None:
            raise RuleError(f"nothing recorded to resend for {operation}")
        await self.session.call(recorded["tool"], dict(recorded["request"]), caller="rule", hook=self.hook)


class ReportGate:
    """One trial's policy, invoked once per report proposal at the report gate; records what it did."""

    def __init__(self, policy: RulePolicy | None, pack, session):
        if policy is not None:
            check_policy(policy, pack)
        self.policy, self.pack, self.session = policy, pack, session
        self.digest = policy_digest(policy) if policy is not None else None
        self.resolved = resolve_policy(policy, pack, session.intent) if policy is not None else None
        self.interpreter: Interpreter | None = None
        self.proposals = 0
        self.last_new_observations = 0

    def declare(self) -> None:
        """Record the policy as the trial's first rule-step event, so the envelope shows what the agent carried."""
        if self.policy is not None:
            self.session.rule_step("policy_declared", {"policy": self.policy.model_dump(mode="json"), "policy_digest": self.digest,
                                                       "hooks": list(SUPPORTED_HOOKS), "gate": "report"})

    async def check(self, report: dict) -> HookResult | None:
        """Run the report hook on one proposal; None when the trial carries no policy."""
        if self.policy is None:
            return None
        self.proposals += 1
        proposal_id = f"proposal-{self.proposals}"
        if self.interpreter is None:
            self.interpreter = Interpreter(self.resolved, self.session.journal, SessionExecutor(self.session, self.pack, REPORT_HOOK))
        intent = self.session.intent
        claims = {str(intent[spec["intent_key"]]): report.get(spec["claim"]) for spec in self.pack.operation_aliases.values()}
        labels = {key: value for key, value in report.items() if isinstance(value, str)}
        before = len(self.session.observations)
        result = await self.interpreter.invoke(REPORT_HOOK, proposal_id, gate="report", claims=claims, labels=labels)
        self.last_new_observations = len(self.session.observations) - before
        self.session.rule_step(REPORT_HOOK, {"gate": "report", "proposal_id": proposal_id, "policy_digest": self.digest,
                                             "blocked": result.blocked, "final_requested": result.final_requested,
                                             "reasons": list(result.reasons), "steps_run": list(result.steps_run),
                                             "new_observations": self.last_new_observations, "proposal": report})
        return result


__all__ = ["REPORT_HOOK", "SUPPORTED_HOOKS", "ReportGate", "RuleError", "SessionExecutor", "check_policy", "policy_digest",
           "policy_from_json", "resolve_policy"]
