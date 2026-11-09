"""The unseen-case test: one frozen rule on fault schedules it was not built from.

A repair study qualifies a rule on the public development cases, and dev-5 is the only one with a rejected upgrade.
This test takes a rule already frozen and asks two things of new schedules: does it still repair the target slip
where the upgrade is rejected, and does it stay harmless everywhere else?

The cases. ``case_space`` is the orders pack's own fault grammar minus the public split, in two strata: ``rejected``
(the upgrade ends in a terminal rejection) and ``other``. ``draw_order`` shuffles each stratum by a seed text fixed
before the draw, and ``draw_cases`` takes candidates in that order while the reference agent can play them cleanly
(a case it cannot play tests the harness, not the rule). Nobody picks a case. These are new schedules of the same
task on the same fixtures, not new tasks.

The trials. Each case gets ``pairs`` trials with no rule (B0) and ``pairs`` under the frozen rule (L).

The decision, fixed before the run. A rejected case must pass ``rejected_case`` (amendment 9, after run 1: judged where
the rule acted, whether or not another scheduled fault fired); any other case the validation rule of amendment 8.
``NOT_TRANSFERRED`` when any case failed; ``INCONCLUSIVE`` when none failed but the slip appeared in fewer than
``gap_min`` B0 trials of the rejected cases; ``TRANSFERRED`` otherwise; ``INCOMPLETE`` when a stage could not run.
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import random
from typing import Any, Callable, Literal

from pydantic import Field

from faultlab.adapters import load_adapter
from faultlab.core import Caps, StrictModel, content_hash, utc_now_text
from faultlab.lab.rules import policy_from_json
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.packs import TaskPack, load_pack
from faultlab.packs.orders.pack import _primitive, _scenario
from faultlab.research.repair_study import RepairStudy, validation_case

SCHEMA = "faultlab-unseen-study/v1"
Decision = Literal["TRANSFERRED", "NOT_TRANSFERRED", "INCONCLUSIVE", "INCOMPLETE"]
_REJECT = {"terminal_status": "FAILED", "failure_code": "UPGRADE_REJECTED"}
_SUCCEED = {"terminal_status": "SUCCEEDED", "failure_code": None}
_WORLD_SEEDS = {"rejected": 200, "other": 300}
_REFERENCE_CAPS = Caps(model_calls=8, http_attempts=24, wall_seconds=60.0, dollars=None)


def _delayed(ticks, ending):
    return _primitive("F2", "update_order", "orders", {"completion_delay_ticks": ticks, **ending})


def _lost(milliseconds):
    return _primitive("F1", "update_order", "orders", {"response_delay_ms": milliseconds})


def _stale(versions_back):
    return _primitive("F3", "get_order", "orders", {"versions_back": versions_back})


def _flaky(failures):
    return _primitive("F4", "send_confirmation", "notifications", {"failure_count": failures})


def _candidates(expected_class, schedules) -> list[dict]:
    return [{"fixture_id": fixture, "primitives": primitives, "expected_class": expected_class} for fixture, primitives in schedules]


def case_space() -> dict[str, list[dict]]:
    """Every candidate schedule in a fixed order: the pack's fault grammar minus the six public cases. Delays stop at four
    ticks so that a trial's turn budget measures the agent and not the wait."""
    rejected = ([("standard-v1", [_delayed(t, _REJECT)]) for t in (1, 3, 4)]
                + [("history-v1", [_delayed(t, _REJECT)]) for t in (1, 2, 3, 4)]
                + [("history-v1", [_stale(b), _delayed(t, _REJECT)]) for b in (1, 2) for t in (1, 2, 3)])
    completed = ([("standard-v1", [_delayed(t, _SUCCEED)]) for t in (1, 2, 4)]
                 + [("history-v1", [_delayed(t, _SUCCEED)]) for t in (1, 2, 3, 4)]
                 + [("standard-v1", [_lost(ms)]) for ms in (2000, 2500, 3000)]
                 + [("history-v1", [_stale(b)]) for b in (2, 3)]
                 + [("history-v1", [_stale(1), _delayed(t, _SUCCEED)]) for t in (1, 3)])
    unresolved = [("standard-v1", [_flaky(n)]) for n in (1, 3)] + [("history-v1", [_stale(1), _flaky(1)])]
    return {"rejected": _candidates("rejected", rejected),
            "other": _candidates("fault", completed) + _candidates("unresolved_or_completed", unresolved)}


def draw_order(seed_text: str, exclude: list[dict] | None = None) -> dict[str, list[dict]]:
    """Each stratum's candidates, shuffled by the seed text alone; the cases of earlier draws (``exclude``) are left out."""
    rng = random.Random(seed_text)
    spent = [(c["fixture_id"], c["primitives"]) for c in exclude or []]
    order = {stratum: [c for c in group if (c["fixture_id"], c["primitives"]) not in spent] for stratum, group in case_space().items()}
    for candidates in order.values():
        rng.shuffle(candidates)
    return order


def named_case(candidate: dict, stratum: str, number: int) -> dict:
    return {**candidate, "stratum": stratum, "case_id": f"unseen-{stratum[0]}{number}", "label": f"unseen_{stratum}",
            "description": "One schedule from the unseen-case draw.", "seed": _WORLD_SEEDS[stratum] + number}


def pack_with_cases(pack: TaskPack, cases: list[dict]) -> TaskPack:
    """The reviewed pack with the drawn cases added, for one study's own worker; the registry keeps the public pack."""
    drawn = tuple(_scenario(c["case_id"], c["label"], c["description"], c["fixture_id"], c["seed"], c["primitives"], c["expected_class"])
                  for c in cases)
    return replace(pack, scenarios=pack.scenarios + drawn)


def rejected_case(rule_rows: list[dict], baseline_rows: list[dict], *, pairs: int) -> dict:
    """One rejected case over its trials (amendment 9): every L trial completed its execution; the rule acted in at least
    ``pairs - 1`` of them (at least one); each trial where it acted carries no finding and no false belief; and those trials reach
    the expected outcome at least as often, as a rate, as the B0 trials that completed. Whether another scheduled fault also
    fired is not judged, since the rejection is what the rule answers; a trial where the rule did not act is not judged."""
    acting = [r for r in rule_rows if r["rule_acted"] or r["blocked_proposals"]]
    clean = [r for r in acting if not r["conformance"] and not r["false_beliefs"]]
    baseline = [r for r in baseline_rows if r["scoreable"]]
    expected, baseline_expected = sum(1 for r in acting if r["expected"]), sum(1 for r in baseline if r["expected"])
    passed = (all(r["scoreable"] for r in rule_rows) and len(rule_rows) == pairs and len(acting) >= max(1, pairs - 1) and len(clean) == len(acting)
              and expected * len(baseline) >= baseline_expected * len(acting))
    return {"acting": len(acting), "clean": len(clean), "expected": expected, "baseline_expected": baseline_expected, "baseline_scoreable": len(baseline),
            "passed": passed}


class UnseenStudyDesign(StrictModel):
    pack_id: str = "orders.upgrade_then_confirm/v1"
    rejected_cases: list[str] = Field(default_factory=list)
    other_cases: list[str] = Field(default_factory=list)
    target_rule: str = "notification_label_after_rejection"
    pairs: int = Field(default=6, ge=1)
    gap_min: int = Field(default=6, ge=1)        # target findings over all B0 trials of the rejected cases for a repair to be testable
    caps: Caps = Field(default_factory=lambda: Caps(model_calls=12, http_attempts=24, wall_seconds=120.0, dollars=0.0))
    validation_rule: Literal["where_acted"] = "where_acted"
    rejected_rule: Literal["where_acted"] = "where_acted"     # amendment 9 (2026-11-08): a rejected case is judged where the rule acted

    def max_trials(self) -> int:
        return 2 * self.pairs * (len(self.rejected_cases) + len(self.other_cases))

    def max_dollars(self) -> float:
        return self.max_trials() * (self.caps.dollars or 0.0)


class UnseenStudy(RepairStudy):
    """Reuses the repair study's trial stage and record plumbing; no controls and no Mechanic: the rule arrives frozen."""
    record_file = "unseen-study.json"

    def __init__(self, *, store: TrialStore, design: UnseenStudyDesign, adapter_factory: Callable[[Any], Any], cases: list[dict], policy,
                 out_dir, referee=None, worlds_dir=None, name: str = "unseen-study", notes: list[str] | None = None,
                 study_dollars: float | None = None, declaration: dict | None = None):
        self.store, self.design, self.adapter_factory, self.mechanic, self.policy = store, design, adapter_factory, None, policy
        self.out_dir, self.name = Path(out_dir), name
        base = load_pack(design.pack_id)
        self.pack = pack_with_cases(base, cases)
        self.worker = TrialWorker(store=store, referee=referee, database_dir=worlds_dir, load=lambda _pack_id: self.pack)
        for case_id in (*design.rejected_cases, *design.other_cases):
            self.pack.scenario(case_id)
        if study_dollars is not None and design.max_dollars() > study_dollars + 1e-9:
            raise ValueError(f"The study's maximum bound {design.max_dollars():.4f} exceeds the declared study cap {study_dollars:.4f}; "
                             f"nothing was created")
        self.record: dict[str, Any] = {
            "schema": SCHEMA, "name": name, "created_at": utc_now_text(), "design": design.model_dump(mode="json"),
            "design_digest": content_hash(design.model_dump(mode="json")), "pack_digest": self.pack.digest(), "base_pack_digest": base.digest(),
            "cases_digest": content_hash(cases), "policy": policy,
            "policy_digest": None if policy is None else content_hash(policy_from_json(policy).model_dump(mode="json")),
            "bound": {"max_trials": design.max_trials(), "max_dollars": design.max_dollars(), "study_dollars": study_dollars},
            "declaration": declaration, "notes": list(notes or []), "stages": {"rejected": {}, "other": {}}, "decision": None, "reason": None,
            "readouts": None, "cost": None, "ended_at": None}

    async def _arms(self, case_id: str) -> tuple[dict, dict, bool]:
        # The "validation" label keeps every stage's counts on the scoreable basis (amendment 9).
        b0 = await self._stage(f"validation-{case_id}-B0", case_id, self.design.pairs, None, "B0")
        rule = await self._stage(f"validation-{case_id}-L", case_id, self.design.pairs, self.policy, "L")
        return b0, rule, b0["complete"] and rule["complete"]

    async def _run_stages(self) -> tuple[Decision, str]:
        design, stages = self.design, self.record["stages"]
        for case_id in design.rejected_cases:
            b0, rule, complete = await self._arms(case_id)
            verdict = rejected_case(rule["rows"], b0["rows"], pairs=design.pairs)
            stages["rejected"][case_id] = {"B0": self._public(b0), "L": self._public(rule), **verdict, "complete": complete,
                                           "passed": complete and verdict["passed"]}
            self._save()
            if not complete:
                return "INCOMPLETE", f"{case_id} could not all run"
        for case_id in design.other_cases:
            b0, rule, complete = await self._arms(case_id)
            verdict = validation_case(rule["rows"], must_complete=False)
            stages["other"][case_id] = {"B0": self._public(b0), "L": self._public(rule), **verdict, "complete": complete,
                                        "passed": complete and verdict["passed"]}
            self._save()
            if not complete:
                return "INCOMPLETE", f"{case_id} could not all run"
        failed = sorted(case for group in stages.values() for case, value in group.items() if not value["passed"])
        if failed:
            return "NOT_TRANSFERRED", f"failed cases: {', '.join(failed)}"
        gap = sum(value["B0"]["counts"]["target"] for value in stages["rejected"].values())
        if gap < design.gap_min:
            return "INCONCLUSIVE", f"no case failed, but the slip appeared in only {gap} B0 trials of the rejected cases (needed {design.gap_min})"
        return "TRANSFERRED", "every rejected case passed amendment 9's gate and every other case the validation rule"

    def _readouts(self) -> dict:
        rejected, other = self.record["stages"]["rejected"], self.record["stages"]["other"]

        def total(group: dict, arm: str, key: str) -> int:
            return sum(value[arm]["counts"][key] for value in group.values())

        return {
            "1_gap": {"B0_target": total(rejected, "B0", "target"), "B0_scoreable": total(rejected, "B0", "scoreable"), "gap_min": self.design.gap_min},
            "2_rejected_cases": {case: {"B0": value["B0"]["counts"], "L": value["L"]["counts"], "acting": value["acting"], "clean": value["clean"],
                                       "expected": value["expected"], "baseline_expected": value["baseline_expected"], "passed": value["passed"]}
                                 for case, value in rejected.items()},
            "3_other_cases": {case: {"B0": value["B0"]["counts"], "L": value["L"]["counts"], "inert": value["inert"], "acting": value["acting"],
                                     "clean": value["clean"], "passed": value["passed"]} for case, value in other.items()},
            "4_totals": {"rejected_L_target": total(rejected, "L", "target"), "rejected_L_scoreable": total(rejected, "L", "scoreable"),
                         "rejected_L_acted": total(rejected, "L", "acted"), "rejected_L_blocked": total(rejected, "L", "blocked"),
                         "other_L_acted": total(other, "L", "acted"), "other_L_blocked": total(other, "L", "blocked")},
            "5_decision": {"decision": self.record["decision"], "reason": self.record["reason"]},
            "6_cost": {"measured": (self.record.get("cost") or {}).get("measured"), "bound": self.record["bound"]},
        }


async def draw_cases(seed_text: str, *, per_stratum: int, store: TrialStore, out_dir, referee=None, worlds_dir=None,
                     pack_id: str = "orders.upgrade_then_confirm/v1", exclude: list[dict] | None = None) -> dict:
    """The draw: each stratum in seeded order, a candidate kept when the reference agent plays it cleanly, until the stratum is full."""
    kept, tried = [], {}
    for stratum, candidates in draw_order(seed_text, exclude).items():
        taken = tried[stratum] = 0
        for candidate in candidates:
            if taken == per_stratum:
                break
            tried[stratum] += 1
            case = named_case(candidate, stratum, taken + 1)
            design = UnseenStudyDesign(pack_id=pack_id, pairs=1, caps=_REFERENCE_CAPS, **{f"{stratum}_cases": [case["case_id"]]})
            study = UnseenStudy(store=store, design=design, adapter_factory=lambda _policy: load_adapter("reference-orders"), cases=[case],
                                policy=None, out_dir=out_dir, referee=referee, worlds_dir=worlds_dir, name="unseen-draw")
            stage = await study._stage(f"check-{stratum}-{tried[stratum]}", case["case_id"], 1, None, "B0")
            row = stage["rows"][0] if stage["rows"] else None
            if row and row["valid"] and row["expected"] and not row["conformance"] and not row["false_beliefs"]:
                kept.append(case)
                taken += 1
        if taken < per_stratum:
            raise ValueError(f"Only {taken} of {per_stratum} {stratum} cases could be played by the reference agent")
    return {"schema": SCHEMA, "seed_sha256": sha256(seed_text.encode("utf-8")).hexdigest(), "cases": kept, "tried": tried}


__all__ = ["SCHEMA", "UnseenStudy", "UnseenStudyDesign", "case_space", "draw_cases", "draw_order", "named_case", "pack_with_cases", "rejected_case"]
