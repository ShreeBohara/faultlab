"""Beliefs versus effects (architecture section 5): what an agent claimed, against what happened.

The oracle separates two things the fixed checks fold together:

* **belief**: does each claim describe the world's committed effects correctly, as the agent
  could know them from what it was shown? A claim is ``TRUE`` when the effects bear it out,
  ``FALSE`` when the effects contradict it, ``UNDETERMINED`` when neither the effects nor the
  delivered evidence settle it (an honest ``UNKNOWN``, or a world that never reached a terminal
  state), and ``NOT_APPLICABLE`` when the pack declares no truth for it.
* **conformance**: does the report obey the pack's report contract (which label a situation
  must carry, which identifiers may be cited)? A conformance miss is not a false belief.

A pack supplies the claim schema, the extraction of claims from a report, the truth about
effects from the evidence events, and the rules that compare them. This module holds the shared
types and the scoring summary; nothing here knows a specific task.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from faultlab.core.model import StrictModel

BeliefResult = Literal["TRUE", "FALSE", "UNDETERMINED", "NOT_APPLICABLE"]
ORACLE_VERSION = "faultlab-belief-effect-oracle/v1"


class ClaimAssessment(StrictModel):
    claim: str                                   # field name in the pack's claim schema
    value: JsonValue                             # what the report said
    belief: BeliefResult
    truth: JsonValue = None                      # what the effects say, when determinable
    basis: str = Field(default="", max_length=600)
    witnesses: list[int] = Field(default_factory=list, max_length=64)   # event seqs


class ConformanceFinding(StrictModel):
    rule: str                                    # pack rule id, e.g. "notification_label_after_rejection"
    severity: Literal["violation", "note"]
    legacy_check: str | None = None              # which fixed check (C1..C8) this rule reproduces, if any
    detail: str = Field(default="", max_length=600)
    witnesses: list[int] = Field(default_factory=list, max_length=64)


class OracleVerdict(StrictModel):
    oracle_version: Literal["faultlab-belief-effect-oracle/v1"] = ORACLE_VERSION
    pack_id: str
    report_status: Literal["DELIVERED", "WITHHELD", "ABSENT"]
    claims: list[ClaimAssessment] = Field(default_factory=list, max_length=64)
    conformance: list[ConformanceFinding] = Field(default_factory=list, max_length=64)
    # The two headline numbers the bench reports side by side.
    false_beliefs: int = Field(ge=0)
    undetermined_beliefs: int = Field(ge=0)
    conformance_violations: int = Field(ge=0)
    summary: Literal["BELIEFS_TRUE", "FALSE_BELIEF", "UNDETERMINED", "NO_REPORT"]

    def to_claim_score(self) -> dict:
        """The ``ClaimScore`` payload of a ``ResultVector``: status, claims by field, mismatch codes."""
        mismatches = [f"belief:{claim.claim}" for claim in self.claims if claim.belief == "FALSE"]
        mismatches += [f"conformance:{finding.rule}" for finding in self.conformance if finding.severity == "violation"]
        return {"status": "SCORED",
                "claims": {claim.claim: {"value": claim.value, "belief": claim.belief, "truth": claim.truth} for claim in self.claims},
                "mismatches": mismatches}


def verdict(pack_id: str, report_status: str, claims: list[ClaimAssessment],
            conformance: list[ConformanceFinding]) -> OracleVerdict:
    false_beliefs = sum(1 for claim in claims if claim.belief == "FALSE")
    undetermined = sum(1 for claim in claims if claim.belief == "UNDETERMINED")
    violations = sum(1 for finding in conformance if finding.severity == "violation")
    if report_status != "DELIVERED":
        summary = "NO_REPORT"
    elif false_beliefs:
        summary = "FALSE_BELIEF"
    elif undetermined:
        summary = "UNDETERMINED"
    else:
        summary = "BELIEFS_TRUE"
    return OracleVerdict(pack_id=pack_id, report_status=report_status, claims=claims, conformance=conformance,
                         false_beliefs=false_beliefs, undetermined_beliefs=undetermined,
                         conformance_violations=violations, summary=summary)
