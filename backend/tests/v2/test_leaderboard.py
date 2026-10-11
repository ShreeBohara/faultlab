"""The bench leaderboard: counts with intervals per model, grouped by adapter family, never ranked."""
from bench.harness.leaderboard import aggregate, load_envelopes, markdown, wilson
from test_legacy_projection import write_legacy_store


def test_wilson_intervals_are_sane():
    assert wilson(0, 0) == (0.0, 0.0, 1.0)
    point, low, high = wilson(0, 18)
    assert point == 0.0 and low == 0.0 and 0.17 < high < 0.19
    point, low, high = wilson(9, 18)
    assert point == 0.5 and 0.29 < low < 0.30 and 0.70 < high < 0.71


def test_leaderboard_groups_by_model_and_adapter_family(tmp_path):
    (tmp_path / "run-a").mkdir()
    (tmp_path / "run-b").mkdir()
    write_legacy_store(tmp_path / "run-a" / "lab.sqlite3", episode_id="episode-1")
    write_legacy_store(tmp_path / "run-b" / "lab.sqlite3", episode_id="episode-2", lifecycle="LAB_ERROR", with_verdict=False, with_report=False)
    items = load_envelopes(tmp_path)
    assert sorted(name for name, _ in items) == ["run-a", "run-b"]
    board = aggregate(items)
    assert board["bench_version"].startswith("faultlab-bench-leaderboard/")
    [row] = board["rows"]
    assert row["model"] == "deepseek-ai/DeepSeek-V3.1" and row["adapter"] == "orders-v1" and row["n"] == 2
    assert row["violation_rate"]["count"] == 1 and row["completion_rate"]["count"] == 0
    # Both envelopes break a rule: one a report rule, the other by having no report at all.
    assert row["beliefs"]["NO_REPORT"] == 1 and row["conformance_violation_rate"]["count"] == 2
    assert row["fault_exposure"] == {"configured": 2, "triggered": 1, "unreachable": 0, "triggered_rate": {"count": 1, "n": 2, "rate": 0.5, "wilson95": [0.0945, 0.9055]}}
    text = markdown(board)
    assert "| deepseek-ai/DeepSeek-V3.1 | orders-v1 | 2 |" in text and "Nothing is ranked" in text
