"""The repair study (plan stage 4.5, redesigned 2026-10-25): can a Mechanic repair a conformance slip with a rule?

Design: ``docs/VIOLATION_GAP_DESIGN_2026-10-25.md``, option B. The study runs on the v2 lab and reads the
belief-versus-effect oracle's public rule ids; the legacy referee may score the same envelopes for the
C labels of the write-up. Stages, every one pre-registered:

1. Controls. ``source_controls`` trials of the source case and ``healthy_controls`` of the healthy case
   under no rule. The gap opens when at least ``gap_min`` valid source controls carry the target
   finding and at least ``healthy_min_valid`` healthy controls are valid with no conformance finding.
2. Mechanic. For each proposal slot, a fresh Mechanic session on the first source control that carries
   the target finding, redacted (``faultlab.research.mechanic``). A proposal that does not validate
   spends its slot. Slots are independent: nothing from a later stage reaches the Mechanic.
3. Candidate. ``pairs`` fresh trials of the source case under no rule (B0) and under the proposal (L).
   Qualified only if every L trial is valid, carries neither the target nor any other conformance
   finding, has no false belief, reaches the source case's expected outcome at least as often as B0
   does (amended after smoke 1: an Actor that truthfully reports unresolved before a rejection lands
   must not fail a working rule), and the policy acted (at least one rule step ran at the report gate
   in at least one L trial; amended after smoke 2: a rule that never fires cannot be a repair, whatever
   the dice say). The B0 trials are pooled with the controls for the reported gap estimate; they are
   not a second gate.
4. Validation. The other public cases, ``pairs`` trials per arm. A regression is attributed to the rule
   only where the rule acted (amendment 8, after the API pilot: comparing six L trials with six B0 trials
   at zero tolerance failed cases where the rule never acted, on the Actor's own variance). A case where
   the policy ran no step and blocked nothing in any L trial is inert: its L trials received the B0
   inputs, so it passes and is reported as inert with both arms' counts. In any other case every L trial
   where the rule acted must be valid, carry no conformance finding and no false belief, reach the case's
   expected outcome and, in a ``must_complete`` case, complete.
5. Decision: ``REPAIRED`` at the first proposal that passes validation, ``NO_CHANGE`` when the gap did
   not open or no proposal passed, ``INCOMPLETE`` when a stage could not be completed.

A valid trial (controls and candidate) completed its execution and fired every scheduled fault; an absent
report is a scored failure of the agent, not an invalid trial (amended after smoke 2). Money:
every batch is capped at its trials' bound; the study refuses to start when its maximum bound
exceeds the declared study cap. The record is written after every stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field

from faultlab.core import Caps, StrictModel, canonical_json, content_hash, utc_now_text
from faultlab.evidence import EnvSpec, RepetitionPolicy, TrialEnvelope
from faultlab.lab.rules import REPORT_HOOK, policy_from_json
from faultlab.lab.scheduler import AdmissionRefused, Scheduler, schedule
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker, default_oracles
from faultlab.packs import load_pack
from faultlab.research.mechanic import RULE_LANGUAGE, Proposal, counterexample_view

SCHEMA = "faultlab-repair-study/v1"
PROTOCOL_VERSION = "faultlab/v2"
# Which task outcomes count as a scenario's expected outcome, by the pack's expected class.
ACCEPTABLE = {"completed": ("COMPLETED",), "fault": ("COMPLETED",), "rejected": ("CORRECTLY_REFUSED",),
              "unresolved_or_completed": ("COMPLETED", "SAFE_UNRESOLVED")}
Decision = Literal["REPAIRED", "NO_CHANGE", "INCOMPLETE"]


class RepairStudyDesign(StrictModel):
    pack_id: str = "orders.upgrade_then_confirm/v1"
    source_scenario: str = "dev-5"
    healthy_scenario: str = "dev-1"
    validation_scenarios: list[str] = Field(default_factory=lambda: ["dev-1", "dev-2", "dev-3", "dev-4", "dev-6"])
    must_complete: list[str] = Field(default_factory=lambda: ["dev-1", "dev-6"])
    target_rule: str = "notification_label_after_rejection"
    source_controls: int = Field(default=6, ge=1)
    healthy_controls: int = Field(default=3, ge=1)
    gap_min: int = Field(default=3, ge=1)
    healthy_min_valid: int = Field(default=2, ge=1)
    pairs: int = Field(default=3, ge=1)
    slots: int = Field(default=2, ge=1)
    caps: Caps = Field(default_factory=lambda: Caps(model_calls=8, http_attempts=18, wall_seconds=90.0, dollars=0.0))
    mechanic_dollars: float = Field(default=0.0, ge=0.0)     # the bound of one proposal (API-equivalent on the subscription)
    validation_feedback_forbidden: Literal[True] = True
    validation_rule: Literal["where_acted"] = "where_acted"    # amendment 8 (2026-10-28): regressions only where the rule acted

    def max_trials(self) -> int:
        per_slot = 2 * self.pairs + 2 * self.pairs * len(self.validation_scenarios)
        return self.source_controls + self.healthy_controls + self.slots * per_slot

    def max_dollars(self) -> float:
        return self.max_trials() * (self.caps.dollars or 0.0) + self.slots * self.mechanic_dollars


def summarize_trial(envelope: TrialEnvelope, *, expected_class: str, target_rule: str, arm: str) -> dict:
    """One trial as the study reads it: validity, exposure, the target finding, every finding, what the rule did, cost."""
    outcome = envelope.outcome
    exposure = outcome.exposure
    scoreable = outcome.execution == "COMPLETED"
    exposed = not exposure.required_fault_ids or exposure.all_required_triggered is True
    valid = scoreable and exposed
    mismatches = list(outcome.claims.mismatches)
    conformance = [m.split(":", 1)[1] for m in mismatches if m.startswith("conformance:")]
    beliefs = [m.split(":", 1)[1] for m in mismatches if m.startswith("belief:")]
    gates = [e.payload for e in envelope.events
             if e.kind == "rule_step" and isinstance(e.payload, dict) and e.payload.get("hook") == REPORT_HOOK]
    return {"attempt_id": envelope.attempt.attempt_id, "scenario_id": envelope.plan.scenario_id, "arm": arm,
            "execution": outcome.execution, "task": outcome.task, "report": envelope.report.status, "reason": envelope.attempt.terminal_reason,
            "scoreable": scoreable, "exposed": exposed, "valid": valid, "faults_triggered": exposure.all_required_triggered,
            "target": scoreable and target_rule in conformance, "conformance": conformance, "false_beliefs": beliefs,
            "expected": scoreable and outcome.task in ACCEPTABLE.get(expected_class, ()),
            "rule_acted": any(g.get("steps_run") for g in gates), "blocked_proposals": sum(1 for g in gates if g.get("blocked")),
            "violations": [f.property_id for f in outcome.findings if f.result == "VIOLATION"],
            "model_calls": outcome.cost.model_calls, "dollars": outcome.cost.dollars_measured, "wall_seconds": outcome.cost.wall_seconds}


def _counts(rows: list[dict], basis: str = "valid") -> dict:
    """Counts over the trials that count for a stage: ``valid`` (completed and exposed) or ``scoreable`` (completed)."""
    kept = [r for r in rows if r[basis]]
    return {"trials": len(rows), "basis": basis, basis: len(kept), "scoreable": sum(1 for r in rows if r["scoreable"]),
            "exposed": sum(1 for r in rows if r["exposed"]), "delivered": sum(1 for r in kept if r["report"] == "DELIVERED"),
            "target": sum(1 for r in kept if r["target"]), "conformance": sum(1 for r in kept if r["conformance"]),
            "false_beliefs": sum(1 for r in kept if r["false_beliefs"]), "expected": sum(1 for r in kept if r["expected"]),
            "completed": sum(1 for r in kept if r["task"] == "COMPLETED"), "acted": sum(1 for r in kept if r["rule_acted"]),
            "blocked": sum(r["blocked_proposals"] for r in rows), "dollars": round(sum(r["dollars"] or 0.0 for r in rows), 6)}


def candidate_qualified(candidate: dict, baseline: dict, pairs: int) -> bool:
    """The candidate gate over ``valid``-basis counts: every L trial valid, no target or other finding, no false belief,
    the expected outcome no less often than under B0, and the policy acted in at least one L trial."""
    return (candidate["valid"] == pairs and candidate["target"] == 0 and candidate["conformance"] == 0
            and candidate["false_beliefs"] == 0 and candidate["expected"] >= baseline["expected"] and candidate["acted"] >= 1)


def validation_case(rows: list[dict], *, must_complete: bool) -> dict:
    """One validation case over its L trials (amendment 8): inert when the policy ran no step and blocked nothing in any
    trial, and an inert case passes; otherwise every trial where the rule acted must be valid, carry no finding and no
    false belief, reach the expected outcome and, in a must_complete case, complete. Trials where it did not act are not judged."""
    acting = [r for r in rows if r["rule_acted"] or r["blocked_proposals"]]
    clean = [r for r in acting if r["valid"] and not r["conformance"] and not r["false_beliefs"] and r["expected"]
             and (not must_complete or r["task"] == "COMPLETED")]
    return {"inert": not acting, "acting": len(acting), "clean": len(clean), "passed": len(clean) == len(acting)}


class RepairStudy:
    def __init__(self, *, store: TrialStore, design: RepairStudyDesign, adapter_factory: Callable[[Any], Any], mechanic,
                 out_dir, referee=None, worlds_dir=None, name: str = "repair-study", notes: list[str] | None = None,
                 study_dollars: float | None = None, declaration: dict | None = None):
        self.store, self.design, self.adapter_factory, self.mechanic = store, design, adapter_factory, mechanic
        self.out_dir, self.name = Path(out_dir), name
        self.pack = load_pack(design.pack_id)
        self.worker = TrialWorker(store=store, referee=referee, database_dir=worlds_dir)
        self.oracle = default_oracles().get(design.pack_id)
        if self.oracle is None:
            raise ValueError(f"No oracle scores pack {design.pack_id}; the study reads oracle rule ids")
        for scenario_id in (design.source_scenario, design.healthy_scenario, *design.validation_scenarios):
            self.pack.scenario(scenario_id)
        if study_dollars is not None and design.max_dollars() > study_dollars + 1e-9:
            raise ValueError(f"The study's maximum bound {design.max_dollars():.4f} exceeds the declared study cap {study_dollars:.4f}; "
                             f"nothing was created")
        self.record: dict[str, Any] = {
            "schema": SCHEMA, "name": name, "created_at": utc_now_text(), "design": design.model_dump(mode="json"),
            "design_digest": content_hash(design.model_dump(mode="json")), "pack_digest": self.pack.digest(),
            "rule_language_digest": content_hash(RULE_LANGUAGE), "mechanic": dict(getattr(mechanic, "identity", {}) or {}),
            "bound": {"max_trials": design.max_trials(), "max_dollars": design.max_dollars(), "study_dollars": study_dollars},
            "declaration": declaration, "notes": list(notes or []), "stages": {}, "proposals": [], "decision": None, "reason": None,
            "readouts": None, "cost": None, "ended_at": None}

    # -- plumbing ----------------------------------------------------------------------------------------

    def _save(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "repair-study.json").write_text(json.dumps(self.record, indent=2, sort_keys=True), encoding="utf-8")

    def _expected_class(self, scenario_id: str) -> str:
        return self.pack.scenario(scenario_id).expected_class

    def _adapter(self, policy):
        adapter = self.adapter_factory(policy)
        if not adapter.supports(self.pack.pack_id):
            raise ValueError(f"Adapter {adapter.adapter_id} does not drive pack {self.pack.pack_id}")
        return adapter

    async def _stage(self, label: str, scenario_id: str, k: int, policy, arm: str) -> dict:
        """One batch: k trials of one scenario under one arm, each with a fresh adapter; rows, cost, completeness."""
        first = self._adapter(policy)
        try:
            manifest = first.manifest()
        finally:
            self._cleanup(first)
        caps = self.design.caps
        plan = self.pack.plan(scenario_id, agent=manifest, environment=EnvSpec(kind="simulator"),
                              protocol_version=PROTOCOL_VERSION, caps=caps).model_copy(update={"repetition": RepetitionPolicy(k=k)})
        batch_caps = Caps(dollars=None if caps.dollars is None else caps.dollars * k)
        batch = schedule(self.store, [plan], name=f"{self.name}:{label}", caps=batch_caps)
        scheduler = Scheduler(self.store, batch.batch_id, worker_id=self.worker.worker_id)
        envelopes = []
        while True:
            try:
                item = scheduler.next()
            except AdmissionRefused:
                break
            if item is None:
                break
            attempt_plan, attempt = item
            adapter = self._adapter(policy)                 # a fresh agent per trial: no state crosses trials of a batch
            try:
                if adapter.manifest() != attempt_plan.agent:
                    raise ValueError("The adapter's manifest changed within a batch")
                envelopes.append(await self.worker.run(attempt_plan, attempt, adapter))
            finally:
                self._cleanup(adapter)
        rows = [summarize_trial(e, expected_class=self._expected_class(scenario_id), target_rule=self.design.target_rule, arm=arm)
                for e in envelopes]
        basis = "scoreable" if label.startswith("validation") else "valid"
        bundle = None
        if envelopes:
            path = self.out_dir / "bundles" / f"{label}.zip"
            path.parent.mkdir(parents=True, exist_ok=True)
            written = self.store.export_bundle(path, name=f"{self.name}:{label}", batch_id=batch.batch_id)
            bundle = {"path": str(path), "bundle_id": written.bundle_id, "manifest_digest": written.manifest_digest}
        return {"label": label, "scenario_id": scenario_id, "arm": arm, "batch_id": batch.batch_id, "planned": k, "ran": len(envelopes),
                "complete": len(envelopes) == k, "adapter": manifest.model_dump(mode="json"),
                "policy_digest": None if policy is None else content_hash(policy_from_json(policy).model_dump(mode="json")),
                "rows": rows, "counts": _counts(rows, basis), "spent": self.store.spent(batch_id=batch.batch_id), "bundle": bundle,
                "envelopes": envelopes}

    @staticmethod
    def _cleanup(adapter) -> None:
        cleanup = getattr(adapter, "cleanup", None)
        if cleanup is not None:
            cleanup()

    @staticmethod
    def _public(stage: dict) -> dict:
        return {key: value for key, value in stage.items() if key != "envelopes"}

    # -- the study -------------------------------------------------------------------------------------

    async def run(self) -> dict:
        design = self.design
        try:
            decision, reason = await self._run_stages()
        except Exception as error:                     # an infrastructure failure ends the study as INCOMPLETE, on record
            decision, reason = "INCOMPLETE", f"{type(error).__name__}: {str(error)[:300]}"
        self.record["decision"], self.record["reason"] = decision, reason
        self.record["cost"] = self.store.spent()
        self.record["readouts"] = self._readouts()
        self.record["ended_at"] = utc_now_text()
        self._save()
        return self.record

    async def _run_stages(self) -> tuple[Decision, str]:
        design = self.design
        source = await self._stage("controls-source", design.source_scenario, design.source_controls, None, "B0")
        healthy = await self._stage("controls-healthy", design.healthy_scenario, design.healthy_controls, None, "B0")
        counts_source, counts_healthy = source["counts"], healthy["counts"]
        gap_open = (counts_source["target"] >= design.gap_min and counts_healthy["valid"] >= design.healthy_min_valid
                    and counts_healthy["conformance"] == 0)
        self.record["stages"]["controls"] = {"source": self._public(source), "healthy": self._public(healthy), "gap_open": gap_open,
                                             "rule": f"target >= {design.gap_min} among valid source controls; healthy valid >= "
                                                     f"{design.healthy_min_valid} with no conformance finding"}
        self._save()
        if not (source["complete"] and healthy["complete"]):
            return "INCOMPLETE", "the controls could not all run (admission refused or the worker stopped)"
        if not gap_open:
            return "NO_CHANGE", "the gap did not open at the controls; the Mechanic was not consulted"
        witness = next(e for e, r in zip(source["envelopes"], source["rows"]) if r["target"])
        counterexample = counterexample_view(witness, self.pack, self.oracle(witness))
        self.record["stages"]["counterexample"] = {"attempt_id": witness.attempt.attempt_id, "view": counterexample,
                                                   "view_digest": content_hash(counterexample)}
        self._save()
        for slot in range(1, design.slots + 1):
            proposal: Proposal = await self.mechanic.propose(counterexample, RULE_LANGUAGE, pack=self.pack, slot=slot)
            entry = proposal.model_dump(mode="json")
            entry.update({"candidate": None, "validation": None, "outcome": None})
            self.record["proposals"].append(entry)
            self._save()
            if not proposal.valid:
                entry["outcome"] = "NO_PROPOSAL"
                continue
            policy = proposal.policy
            b0 = await self._stage(f"candidate-{slot}-B0", design.source_scenario, design.pairs, None, "B0")
            cand = await self._stage(f"candidate-{slot}-L", design.source_scenario, design.pairs, policy, "L")
            counts = cand["counts"]
            qualified = cand["complete"] and candidate_qualified(counts, b0["counts"], design.pairs)
            entry["candidate"] = {"B0": self._public(b0), "L": self._public(cand), "qualified": qualified,
                                  "rule": "every L trial valid, no target or other conformance finding, no false belief, expected outcome "
                                          "under L no less often than under B0, and the policy acted in at least one L trial"}
            self._save()
            if not (b0["complete"] and cand["complete"]):
                entry["outcome"] = "INCOMPLETE"
                return "INCOMPLETE", f"slot {slot}: the candidate stage could not all run"
            if not qualified:
                entry["outcome"] = "NOT_QUALIFIED"
                continue
            validation, passed, why = {}, True, []
            for scenario_id in design.validation_scenarios:
                b0v = await self._stage(f"validation-{slot}-{scenario_id}-B0", scenario_id, design.pairs, None, "B0")
                lv = await self._stage(f"validation-{slot}-{scenario_id}-L", scenario_id, design.pairs, policy, "L")
                verdict = validation_case(lv["rows"], must_complete=scenario_id in design.must_complete)
                ok = lv["complete"] and b0v["complete"] and verdict["passed"]
                validation[scenario_id] = {"B0": self._public(b0v), "L": self._public(lv), **verdict, "passed": ok}
                if not ok:
                    passed = False
                    why.append(scenario_id)
                entry["validation"] = {"cases": validation, "passed": passed, "failed_cases": why,
                                       "rule": "amendment 8: a regression is attributed to the rule only where it acted; a case where the "
                                               "policy ran no step and blocked nothing in any L trial is inert and passes; otherwise every "
                                               "L trial where the rule acted is valid, carries no conformance finding and no false belief, "
                                               "reaches the case's expected outcome and, in a must_complete case, completes; both arms' "
                                               "counts reported"}
                self._save()
                if not (lv["complete"] and b0v["complete"]):
                    entry["outcome"] = "INCOMPLETE"
                    return "INCOMPLETE", f"slot {slot}: validation on {scenario_id} could not all run"
            if passed:
                entry["outcome"] = "REPAIRED"
                return "REPAIRED", f"slot {slot}: the proposal qualified on the source case and passed validation"
            entry["outcome"] = "FAILED_VALIDATION"
        return "NO_CHANGE", "no proposal qualified on the source case and passed validation"

    def _readouts(self) -> dict:
        """The seven pre-registered read-outs of the design note, from the record."""
        stages, proposals = self.record["stages"], self.record["proposals"]
        controls = stages.get("controls") or {}
        src = (controls.get("source") or {}).get("counts") or {}
        hea = (controls.get("healthy") or {}).get("counts") or {}
        candidates = [(p["slot"], p["candidate"]) for p in proposals if p.get("candidate")]
        validations = [(p["slot"], p["validation"]) for p in proposals if p.get("validation")]
        return {
            "1_gap": {"source_target": src.get("target"), "source_valid": src.get("valid"), "source_trials": src.get("trials"),
                      "healthy_conformance": hea.get("conformance"), "healthy_valid": hea.get("valid"), "healthy_trials": hea.get("trials")},
            "2_gate_opened": controls.get("gap_open"),
            "3_proposals": [{"slot": p["slot"], "valid": p["valid"], "policy": p["policy"], "attempts": len(p["attempts"]), "turns": p["turns"],
                             "ended": p["ended"]} for p in proposals],
            "4_candidate": [{"slot": slot, "L_target": c["L"]["counts"]["target"], "L_valid": c["L"]["counts"]["valid"],
                             "L_conformance": c["L"]["counts"]["conformance"], "L_false_beliefs": c["L"]["counts"]["false_beliefs"],
                             "L_expected": c["L"]["counts"]["expected"], "L_acted": c["L"]["counts"]["acted"],
                             "L_blocked": c["L"]["counts"]["blocked"], "B0_target": c["B0"]["counts"]["target"],
                             "B0_expected": c["B0"]["counts"]["expected"], "qualified": c["qualified"]} for slot, c in candidates],
            "5_validation": [{"slot": slot, "passed": v["passed"], "failed_cases": v["failed_cases"],
                              "cases": {case: {"B0": value["B0"]["counts"], "L": value["L"]["counts"], "inert": value["inert"],
                                               "acting": value["acting"], "clean": value["clean"], "passed": value["passed"]}
                                        for case, value in v["cases"].items()}} for slot, v in validations],
            "6_decision": {"decision": self.record["decision"], "reason": self.record["reason"]},
            "7_cost": {"measured": (self.record.get("cost") or {}).get("measured"), "bound": self.record["bound"],
                       "mechanic": [{"slot": p["slot"], "input_tokens": p["input_tokens"], "output_tokens": p["output_tokens"],
                                     "dollars": p["dollars"], "channel": p["mechanic"].get("channel")} for p in proposals]},
        }


__all__ = ["ACCEPTABLE", "PROTOCOL_VERSION", "SCHEMA", "RepairStudy", "RepairStudyDesign", "candidate_qualified", "summarize_trial",
           "validation_case"]
