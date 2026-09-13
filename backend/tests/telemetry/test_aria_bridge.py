import asyncio

import pytest

from app.telemetry.aria_bridge import AriaBridge, ARIA_PROMPT, RUN_NAME_FILTER, validate_analysis_capture, validate_automation_setup
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.safety import TelemetryError, wandb_url


def bridge_args():
    return {"completed": True, "development_summary": {"attempted": 3, "violations": 3, "fault_triggered": 3},
            "verified_links": [{"url": "https://wandb.ai/fixture/project/call/source", "status": "weave_verified",
                                "split": "development", "experiment_purpose": "reproduction"}],
            "evidence_table": [{"split": "development", "experiment_purpose": "reproduction", "reproduced": 3, "attempted": 3}],
            "authorize": lambda _: True}


def test_campaign_bridge_once_with_actual_returned_reference(worker, store):
    bridge = AriaBridge(worker, TelemetryOutbox(store), project="fixture/project")
    async def run():
        first = await bridge.publish_campaign("campaign", **bridge_args())
        second = await bridge.publish_campaign("campaign", **bridge_args())
        assert first == second and first["state"] == "awaiting_aria_verification"
        assert first["analysis_verified"] is False and first["invocation_verified"] is False
    asyncio.run(run())
    assert len(worker.commands) == 1
    assert worker.commands[0][1]["name"] == "faultlab-campaign-campaign"
    assert worker.commands[0][1]["summary"]["association"] == "explicit_prior_verified_references"


def test_ambiguous_campaign_completion_is_not_retriggered(worker, store):
    worker.fail = True
    bridge = AriaBridge(worker, TelemetryOutbox(store), project="fixture/project")
    async def run():
        assert (await bridge.publish_campaign("campaign", **bridge_args()))["state"] == "publication_pending"
        worker.fail = False
        assert (await bridge.publish_campaign("campaign", **bridge_args()))["state"] == "publication_unverified"
    asyncio.run(run())
    assert len(worker.commands) == 1


def test_private_or_study_evidence_cannot_enter_aria(worker, store):
    args = bridge_args()
    args["verified_links"][0]["experiment_purpose"] = "selection_comparison"
    with pytest.raises(TelemetryError):
        asyncio.run(AriaBridge(worker, TelemetryOutbox(store), project="fixture/project").publish_campaign("c", **args))
    assert worker.commands == []


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://wandb.ai/run", "https://wandb.ai.evil.example/run",
                                  "https://evil.example/run", "https://user:secret@wandb.ai/run", "https://wandb.ai:444/run"])
def test_aria_urls_are_allowlisted_links_only(url):
    with pytest.raises(TelemetryError):
        wandb_url(url)


def analysis_fixture(mode="automatic"):
    return {"analysis_id": "fixture-analysis", "campaign_id": "campaign", "run_id": "run", "automation_id": "automation",
            "invocation_mode": mode, "provenance": "manual_ui_capture", "status": "COMPLETED", "execution_id": "execution",
            "observed_at": "2026-09-12T00:00:00Z", "thread_id": "thread", "history_url": "https://wandb.ai/fixture/project/automations/history",
            "output_url": "https://wandb.ai/fixture/project/reports/fixture", "summary": "Fixture analysis, not real Aria evidence.",
            "recorder": "offline test", "verified_source_refs": []}


def test_manual_invocation_cannot_pass_automatic_evidence_shape():
    result = validate_analysis_capture(analysis_fixture("manual"), campaign_run={"campaign_id": "campaign", "run_id": "run"}, automation_id="automation")
    assert not result["automatic_evidence_complete"] and not result["remote_verification"]


def test_history_and_output_required_and_capture_still_not_remote_verification():
    data = analysis_fixture()
    valid = validate_analysis_capture(data, campaign_run={"campaign_id": "campaign", "run_id": "run"}, automation_id="automation")
    assert valid["automatic_evidence_complete"] and not valid["remote_verification"]
    data["history_url"] = None
    pending = validate_analysis_capture(data, campaign_run={"campaign_id": "campaign", "run_id": "run"}, automation_id="automation")
    assert not pending["automatic_evidence_complete"]
    with pytest.raises(TelemetryError):
        validate_analysis_capture(data, campaign_run={"campaign_id": "foreign", "run_id": "run"}, automation_id="automation")


def test_aria_automation_setup_requires_observed_access_and_reviewed_prompt():
    record = {"project": "fixture/project", "automation_id": "fixture-automation", "team_confirmed": True,
              "smart_features_enabled": True, "ask_aria_observed": True, "event": "Finished", "run_name_filter": RUN_NAME_FILTER,
              "action": "Trigger ARIA", "prompt": ARIA_PROMPT, "configuration_url": "https://wandb.ai/fixture/project/automations/config",
              "recorder": "offline fixture", "observed_at": "2026-09-12T00:00:00Z"}
    assert validate_automation_setup(record, project="fixture/project")["prompt"] == ARIA_PROMPT
    record["ask_aria_observed"] = False
    with pytest.raises(TelemetryError):
        validate_automation_setup(record, project="fixture/project")
