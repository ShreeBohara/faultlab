"""New bookings cases for a screen or a study (second task plan, step 4): the September fault grammar minus the public cases.

``case_space`` lists candidate schedules built from the September grammar (``taskpacks/bookings_move_with_hold``): every single
fault of a chosen set of kinds, targets, occurrences and parameters, and every pair of them that does not put two faults on one
attempt of a tool. A candidate the grammar refuses, one with a fault that no behaviour can fire (``world.cannot_fire``) and the
eight public schedules are left out. Each candidate falls in one stratum: ``lost_create`` (an answer to ``place_hold`` lost or
replaced by a 500: the task's trap), ``move_trouble`` (a lost move answer or a slow, possibly rejected move), ``hold_trouble``
(a short hold or trouble releasing one) and ``other``.

``draw`` orders each stratum by a seed text fixed before the draw and takes candidates in that order while the correct agent
(the September reference, through the real worker and the H1-H8 referee, at $0) plays them cleanly, fires every scheduled fault
and keeps a turn to spare. A case it cannot play tests the harness, not the agent. Nobody picks a case. These are new schedules
of the same task on the same fixtures, not new tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
from pathlib import Path
import random
import sys
import tempfile

from faultlab.core import Caps, canonical_json, content_hash
from faultlab.env.kernel import FaultSpec
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.packs.base import Scenario
from faultlab.packs.bookings import models as m
from faultlab.packs.bookings.pack import PACK, SCENARIOS
from taskpacks.bookings_move_with_hold import world as september

STRATA = ("lost_create", "move_trouble", "hold_trouble", "other")
CASES_SCHEMA = "faultlab-bookings-cases/v1"


def _fault(kind, tool, parameters, occurrence=1):
    return {"kind": kind, "target_tool": tool, "target_service": m.SERVICE_OF_TOOL[tool], "occurrence": occurrence, "parameters": parameters}


def single_faults() -> list[dict]:
    faults = []
    for occurrence in (1, 2):
        faults += [_fault("F1", "place_hold", {"response_delay_ms": 1500}, occurrence), _fault("F5", "place_hold", {}, occurrence)]
        faults += [_fault("F6", "place_hold", {"ttl_cut_ticks": cut}, occurrence) for cut in (5, 7, 9)]
    faults.append(_fault("F1", "move_booking", {"response_delay_ms": 1500}))
    faults += [_fault("F2", "move_booking", {"completion_delay_ticks": delay, "terminal_status": status})
               for delay in (1, 2, 3, 5) for status in ("SUCCEEDED", "FAILED")]
    faults += [_fault("F1", "release_hold", {"response_delay_ms": 1500}), _fault("F5", "release_hold", {})]
    faults += [_fault("F3", "get_booking", {"versions_back": back}) for back in (1, 2, 3)]
    faults += [_fault("F4", tool, {"failure_count": count}) for tool in m.SERVICE_OF_TOOL for count in (1, 2)]
    return faults


def stratum(primitives: list[dict]) -> str:
    pairs = {(p["kind"], p["target_tool"]) for p in primitives}
    if any(kind in ("F1", "F5") and tool == "place_hold" for kind, tool in pairs):
        return "lost_create"
    if any(tool == "move_booking" and kind in ("F1", "F2") for kind, tool in pairs):
        return "move_trouble"
    if any(kind == "F6" or tool == "release_hold" for kind, tool in pairs):
        return "hold_trouble"
    return "other"


def _key(fixture_id: str, primitives: list[dict]) -> str:
    return content_hash({"fixture_id": fixture_id, "primitives": primitives})


def case_space() -> list[dict]:
    singles = single_faults()
    candidates = [[fault] for fault in singles]
    candidates += [[a, b] for i, a in enumerate(singles) for b in singles[i + 1:]
                   if (a["target_tool"], a["occurrence"]) != (b["target_tool"], b["occurrence"])]
    public = {_key(s.fixture_id, [p.model_dump(mode="json") for p in s.fault_spec.primitives]) for s in SCENARIOS}
    space = []
    for primitives in candidates:
        fixture_id = "history-v1" if any(p["kind"] == "F3" for p in primitives) else "standard-v1"
        spec = {"scope": PACK.pack_id, "primitives": [{k: p[k] for k in ("kind", "target_tool", "occurrence", "parameters")} for p in primitives]}
        try:
            september.validate_fault_spec(spec, fixture_id)
        except september.FaultSpecError:
            continue
        key = _key(fixture_id, primitives)
        if september.cannot_fire(spec, fixture_id) or key in public:
            continue
        space.append({"key": key, "stratum": stratum(primitives), "fixture_id": fixture_id, "primitives": primitives})
    return space


def scenario(candidate: dict, case_id: str) -> Scenario:
    spec = FaultSpec(schema_version="faultlab/v1", scope=PACK.pack_id, seed=int(candidate["key"][:8], 16) % 2147483647,
                     primitives=candidate["primitives"])
    return Scenario(scenario_id=case_id, label=candidate["stratum"], fixture_id=candidate["fixture_id"], fault_spec=spec, expected_class="drawn",
                    description=f"A drawn {candidate['stratum']} schedule: " + ", ".join(
                        f"{p['kind']} on {p['target_tool']} #{p['occurrence']}" for p in candidate["primitives"]))


def pack_with(scenarios) -> object:
    """The bookings pack with these scenarios in place of the public ones (its digest names them)."""
    return dataclasses.replace(PACK, scenarios=tuple(scenarios))


def playable(candidate: dict) -> bool:
    """The September reference plays the case cleanly through the worker, fires every scheduled fault and keeps a turn to spare."""
    from faultlab.adapters import load_adapter
    from faultlab.lab.store import TrialStore
    from faultlab.lab.worker import TrialWorker
    from faultlab.referee.bookings import BookingsReferee
    case = scenario(candidate, "hk-candidate")
    pack, adapter = pack_with([case]), load_adapter("reference-bookings")
    with tempfile.TemporaryDirectory() as tmp:
        with TrialStore(Path(tmp) / "draw.sqlite3") as store:
            worker = TrialWorker(store=store, worker_id="bookings-draw", database_dir=Path(tmp) / "worlds", referee=BookingsReferee(),
                                 load=lambda pack_id: pack)
            plan = pack.plan(case.scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v1",
                             caps=Caps(http_attempts=18, model_calls=8))
            attempt = TrialAttempt(attempt_id=f"draw-{candidate['key'][:16]}", plan_hash=plan_hash(plan), lifecycle="READY")
            envelope = asyncio.run(worker.run(plan, attempt, adapter))
    outcome = envelope.outcome
    return (outcome.execution == "COMPLETED" and not any(f.result == "VIOLATION" for f in outcome.findings)
            and outcome.exposure.all_required_triggered is True and outcome.cost.model_calls < 8)


def draw(seed_text: str, per_stratum: int, *, play=playable) -> dict:
    """Each stratum shuffled by the seed text, then taken in that order while the reference plays the cases."""
    space, cases, tried = case_space(), [], {}
    for name in STRATA:
        pool = sorted((c for c in space if c["stratum"] == name), key=lambda c: c["key"])
        random.Random(f"{seed_text}|{name}").shuffle(pool)
        taken = tried[name] = 0
        for candidate in pool:
            if taken == per_stratum:
                break
            tried[name] += 1
            if play(candidate):
                taken += 1
                cases.append(candidate)
    # The schedule's content hash is named schedule_digest in a cases file: a field called "key" holding 64 hex characters
    # reads as a credential to secret scanners (screen 2's cases.json, 2026-11-19).
    named = [{"case_id": f"hk-new-{n}", "stratum": c["stratum"], "schedule_digest": c["key"],
              "scenario": scenario(c, f"hk-new-{n}").model_dump(mode="json")} for n, c in enumerate(cases, 1)]
    return {"schema": CASES_SCHEMA, "pack_id": PACK.pack_id, "seed_text": seed_text, "per_stratum": per_stratum,
            "space": {name: sum(1 for c in space if c["stratum"] == name) for name in STRATA}, "tried": tried, "cases": named}


def load_cases(path) -> list[Scenario]:
    value = json.loads(Path(path).read_text())
    if value.get("schema") != CASES_SCHEMA or value.get("pack_id") != PACK.pack_id:
        raise ValueError("not a bookings cases file")
    return [Scenario.model_validate(item["scenario"]) for item in value["cases"]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m faultlab.research.bookings_draw", description="Draw new bookings cases ($0, offline).")
    parser.add_argument("--seed-text", required=True, help="the text, fixed before the draw, that orders each stratum")
    parser.add_argument("--per-stratum", type=int, default=4)
    parser.add_argument("--out", required=True, help="where to write the cases file (JSON)")
    args = parser.parse_args(argv)
    drawn = draw(args.seed_text, args.per_stratum)
    Path(args.out).write_text(canonical_json(drawn))
    print(json.dumps({"cases": len(drawn["cases"]), "space": drawn["space"], "tried": drawn["tried"], "out": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["CASES_SCHEMA", "STRATA", "case_space", "draw", "load_cases", "pack_with", "playable", "scenario", "single_faults", "stratum"]
