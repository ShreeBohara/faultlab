"""The screen driver's watch loop, offline: a fake lab answers the queue and status calls."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def driver():
    spec = importlib.util.spec_from_file_location("baseline_screen", ROOT / "scripts" / "experiments" / "baseline_screen.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLab:
    """Answers the driver's calls from a scripted sequence of status records."""

    def __init__(self, queued: dict, statuses: list[dict]):
        self.queued, self.statuses, self.calls = queued, list(statuses), []

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        class Response:
            def __init__(self, payload):
                self.status_code, self._payload, self.text = 200, payload, ""
            def json(self):
                return self._payload
        if method == "POST" and path.endswith("/stop"):
            return Response({"stopped": True})
        if method == "POST":
            return Response(self.queued)
        return Response(self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0])


def test_a_baseline_study_is_watched_to_its_terminal_status(driver, tmp_path):
    trials = [{"arm": "B0", "outcome": "COMPLETED", "lifecycle": "COMPLETED", "episode_id": "e1"}]
    lab = FakeLab({"study_id": "study-1", "status": "QUEUED"},
                  [{"study_id": "study-1", "status": "RUNNING", "trials": trials, "slots": []},
                   {"study_id": "study-1", "status": "COMPLETED", "trials": trials * 2, "slots": [], "reason": "done"}])
    record, rule = driver.queue_and_watch(lab, "camp-1", "baseline", run_dir=tmp_path, max_minutes=10, max_lab_error_streak=3,
                                          sleep=lambda s: None, clock=lambda: 0.0)
    assert record["status"] == "COMPLETED" and rule is None
    assert lab.calls[0] == ("POST", "/api/campaigns/camp-1/baseline-study", {"execute_live": True})
    assert all(path == "/api/baseline-studies/study-1" for method, path, _ in lab.calls[1:])
    assert json.loads((tmp_path / "baseline-study.json").read_text())["reason"] == "done"


def test_a_completion_study_uses_its_own_routes_and_the_stop_rules_fire(driver, tmp_path):
    lab = FakeLab({"study_id": "study-2", "status": "QUEUED"},
                  [{"study_id": "study-2", "status": "RUNNING", "stage": "controls", "decision": "PENDING",
                    "slots": [{"status": "COMPLETED", "outcome": "LAB_ERROR"}] * 3},
                   {"study_id": "study-2", "status": "INTERRUPTED", "decision": "INCOMPLETE", "slots": [], "reason": "stopped"}])
    record, rule = driver.queue_and_watch(lab, "camp-2", "completion", run_dir=tmp_path, max_minutes=240, max_lab_error_streak=3,
                                          sleep=lambda s: None, clock=lambda: 0.0, evidence_protocol="proto/v1")
    assert rule == "3 consecutive LAB_ERROR live trials" and record["status"] == "INTERRUPTED"
    assert lab.calls[0] == ("POST", "/api/campaigns/camp-2/completion-study", {"execute_live": True, "evidence_protocol": "proto/v1"})
    assert ("POST", "/api/campaigns/camp-2/stop", {}) in lab.calls
    assert (tmp_path / "completion-study.json").exists()
    ticks = iter([0.0, 0.0, 10_000.0, 10_000.0, 10_000.0])
    lab = FakeLab({"study_id": "study-3", "status": "QUEUED"},
                  [{"study_id": "study-3", "status": "RUNNING", "stage": "controls", "slots": []},
                   {"study_id": "study-3", "status": "INCOMPLETE", "decision": "INCOMPLETE", "slots": []}])
    record, rule = driver.queue_and_watch(lab, "camp-3", "completion", run_dir=tmp_path, max_minutes=1, max_lab_error_streak=3,
                                          sleep=lambda s: None, clock=lambda: next(ticks))
    assert rule == "exceeded 1 minutes" and record["status"] == "INCOMPLETE"


def test_the_driver_parses_the_study_choice(driver):
    import argparse
    with pytest.raises(SystemExit):
        driver.main(["--model", "m", "--data-dir", "/tmp/x", "--declaration", "/nonexistent", "--declaration-sha256", "0", "--study", "other"])
    assert set(driver.STUDIES) == {"baseline", "completion"}
