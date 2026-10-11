"""Offline checks of the screen report (scripts/experiments/baseline_screen_report.py): $0, no network.

The two-sided Fisher test is checked against hand-computed tables, and the pooled mode against two
synthetic runs of one model (a phase-A folder plus a b<round>- folder) and one control run.
"""
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/experiments/baseline_screen_report.py"


def load():
    spec = importlib.util.spec_from_file_location("baseline_screen_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_two_sided_fisher_hand_computed_tables():
    report = load()
    # [[2,0],[0,2]]: k in {0,1,2} with probabilities 1/6, 4/6, 1/6; the two tails sum to 1/3.
    assert report.fisher_two_sided(2, 2, 0, 2) == pytest.approx(1 / 3)
    # [[1,0],[0,1]]: both tables are equally likely, so p = 1.
    assert report.fisher_two_sided(1, 1, 0, 1) == pytest.approx(1.0)
    # Identical arms: the observed table is the most likely one, p = 1.
    assert report.fisher_two_sided(3, 10, 3, 10) == pytest.approx(1.0)
    # Nothing bad anywhere: p = 1.
    assert report.fisher_two_sided(0, 18, 0, 18) == pytest.approx(1.0)


def test_two_sided_against_the_upper_tail_and_under_arm_swap():
    report = load()
    # When arm A's rate is the higher one, the two-sided p is at least the one-sided (upper-tail) p.
    for a_bad, a_n, b_bad, b_n in [(5, 54, 0, 54), (2, 36, 0, 54), (1, 36, 0, 54), (9, 18, 2, 18)]:
        two = report.fisher_two_sided(a_bad, a_n, b_bad, b_n)
        one = report.fisher_one_sided(a_bad, a_n, b_bad, b_n)
        assert 0.0 <= two <= 1.0
        assert two >= one - 1e-12
    # The two-sided test does not care which arm is called A.
    assert report.fisher_two_sided(0, 18, 4, 18) == pytest.approx(report.fisher_two_sided(4, 18, 0, 18))
    # The 5-of-54 against 0-of-54 table is symmetric (k=0 and k=5 are equally likely), so the two-sided p is twice the tail.
    assert report.fisher_two_sided(5, 54, 0, 54) == pytest.approx(2 * report.fisher_one_sided(5, 54, 0, 54))


def _record(model, outcomes, *, usage):
    """A minimal baseline-study.json: one live (B0) trial per listed outcome, cases dev-1.. in order."""
    slots, trials = [], []
    for index, (outcome, failed, scheduled, triggered) in enumerate(outcomes):
        episode = f"ep-{model}-{index}"
        slots.append({"episode_id": episode, "case_id": f"dev-{index % 6 + 1}"})
        trials.append({"episode_id": episode, "arm": "B0", "outcome": outcome, "failed_checks": failed,
                       "fault_scheduled": scheduled, "fault_triggered": triggered})
        trials.append({"episode_id": episode, "arm": "L", "outcome": "COMPLETED", "failed_checks": []})   # never counted
    return {"model": model, "status": "COMPLETED", "slots": slots, "trials": trials, "usage": usage}


def test_pooled_groups_rounds_per_model_and_tests_against_the_control(tmp_path):
    report = load()
    screen = tmp_path
    (screen / "claude-x").mkdir()
    (screen / "b1-claude-x").mkdir()
    (screen / "deepseek-v3.1-control").mkdir()
    (screen / "claude-x" / "baseline-study.json").write_text(json.dumps(_record(
        "anthropic:claude-x",
        [("COMPLETED", [], False, False), ("VIOLATION", ["C5"], True, True), ("COMPLETED", [], True, False)],
        usage={"input_tokens": 100, "output_tokens": 10, "cost_dollars": 0.5})))
    (screen / "b1-claude-x" / "baseline-study.json").write_text(json.dumps(_record(
        "anthropic:claude-x",
        [("VIOLATION", ["C6"], True, True), ("SAFE_UNRESOLVED", [], True, True), ("CORRECTLY_REJECTED", [], True, True)],
        usage={"input_tokens": 200, "output_tokens": 20, "cost_dollars": 0.25})))
    (screen / "deepseek-v3.1-control" / "baseline-study.json").write_text(json.dumps(_record(
        "deepseek-ai/DeepSeek-V3.1",
        [("COMPLETED", [], False, False), ("COMPLETED", [], True, True), ("SAFE_UNRESOLVED", [], True, True)],
        usage={"input_tokens": 50, "output_tokens": 5, "cost_dollars": 0.1})))
    pools = report.pooled(report.load(screen), "deepseek-v3.1-control")
    assert set(pools) == {"claude-x", "deepseek-v3.1-control"}
    claude = pools["claude-x"]
    assert sorted(claude["runs"]) == ["b1-claude-x", "claude-x"]
    assert claude["live"] == 6 and claude["violations"] == 2 and claude["completed"] == 2
    assert claude["safe"] == 1 and claude["rejected"] == 1 and claude["errors"] == 0
    assert claude["faults_scheduled"] == 5 and claude["faults_triggered"] == 4
    assert claude["input_tokens"] == 300 and claude["output_tokens"] == 30 and claude["cost"] == pytest.approx(0.75)
    # The per-case rows fold both rounds (trial i of each run is case dev-(i+1)): dev-1 completed once and violated C6 once,
    # dev-2 violated C5 once and stayed safe once, dev-3 had one fault that could not fire.
    assert claude["by_case"]["dev-1"] == {"n": 2, "violations": 1, "completed": 1, "untriggered": 0, "checks": {"C6": 1}}
    assert claude["by_case"]["dev-2"] == {"n": 2, "violations": 1, "completed": 0, "untriggered": 0, "checks": {"C5": 1}}
    assert claude["by_case"]["dev-3"] == {"n": 2, "violations": 0, "completed": 1, "untriggered": 1, "checks": {}}
    assert claude["fisher_two_sided_vs_control"] == pytest.approx(report.fisher_two_sided(2, 6, 0, 3))
    assert "fisher_two_sided_vs_control" not in pools["deepseek-v3.1-control"]


def test_pooled_cli_writes_json(tmp_path, capsys):
    report = load()
    (tmp_path / "deepseek-v3.1-control").mkdir()
    (tmp_path / "deepseek-v3.1-control" / "baseline-study.json").write_text(json.dumps(_record(
        "deepseek-ai/DeepSeek-V3.1", [("COMPLETED", [], False, False)], usage={})))
    out = tmp_path / "pooled.json"
    assert report.main([str(tmp_path), "--pooled", "--json", str(out)]) == 0
    assert json.loads(out.read_text())["deepseek-v3.1-control"]["live"] == 1
    assert "model (pooled)" in capsys.readouterr().out
