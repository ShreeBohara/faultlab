"""New bookings cases (second task plan, step 4): a grammar-valid space without the public cases, a draw fixed by its seed
text, and drawn cases the correct agent plays cleanly through the worker with every fault fired."""

from faultlab.packs.bookings.pack import SCENARIOS
from faultlab.research.bookings_draw import STRATA, case_space, draw, load_cases, pack_with, playable, scenario
from taskpacks.bookings_move_with_hold import world as september


def test_the_space_is_grammar_valid_fireable_and_leaves_out_the_public_cases():
    space = case_space()
    assert len(space) > 200 and {c["stratum"] for c in space} == set(STRATA)
    public = {(s.fixture_id, str([p.model_dump(mode="json") for p in s.fault_spec.primitives])) for s in SCENARIOS}
    for candidate in space:
        spec = {"scope": "bookings.move_with_hold/v1",
                "primitives": [{k: p[k] for k in ("kind", "target_tool", "occurrence", "parameters")} for p in candidate["primitives"]]}
        september.validate_fault_spec(spec, candidate["fixture_id"])
        assert not september.cannot_fire(spec, candidate["fixture_id"])
        assert (candidate["fixture_id"], str(candidate["primitives"])) not in public
    assert len({c["key"] for c in space}) == len(space)


def test_the_draw_is_fixed_by_its_seed_text_and_takes_playable_cases_in_order(tmp_path):
    always = draw("seed-a", 3, play=lambda candidate: True)
    assert always == draw("seed-a", 3, play=lambda candidate: True) != draw("seed-b", 3, play=lambda candidate: True)
    assert [c["stratum"] for c in always["cases"]] == [name for name in STRATA for _ in range(3)]
    refused = draw("seed-a", 1, play=lambda candidate: candidate["key"] != always["cases"][0]["key"])
    assert refused["cases"][0]["key"] == always["cases"][1]["key"] and refused["tried"]["lost_create"] == 2
    real = draw("seed-a", 1)                                       # the reference through the worker, at $0
    assert len(real["cases"]) == len(STRATA) and all(playable({"key": c["key"], "stratum": c["stratum"],
                                                               "fixture_id": c["scenario"]["fixture_id"],
                                                               "primitives": c["scenario"]["fault_spec"]["primitives"]}) for c in real["cases"])
    path = tmp_path / "cases.json"
    path.write_text(__import__("json").dumps(real))
    scenarios = load_cases(path)
    pack = pack_with(scenarios)
    assert [s.scenario_id for s in pack.scenarios] == [f"hk-new-{n}" for n in range(1, len(STRATA) + 1)]
    assert pack.digest() != pack_with(SCENARIOS).digest() and pack_with(SCENARIOS).digest() == __import__(
        "faultlab.packs.bookings.pack", fromlist=["PACK"]).PACK.digest()
