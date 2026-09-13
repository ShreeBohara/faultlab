"""Summary-only W&B runs for the supported Aria UI automation workflow.

There is deliberately no Aria SDK, callback, polling, or generated output URL.
The separately captured history/output is operator-observed evidence.
"""

import json

from app.telemetry.safety import TelemetryError, digest, public_json, utc_now, wandb_url


RUN_NAME_FILTER = "^faultlab-campaign-.*"
ARIA_PROMPT = (
    "Analyze the completed FaultLab development campaign `${run_name}` in `${entity_name}/${project_name}` "
    "using its logged evidence table and verified Weave links. Explain which failures reproduced in fresh "
    "trials, what fault reductions changed, and whether each intervention supports the recorded POLICY_GAP, "
    "CONTRACT_EVIDENCE_GAP, or INCONCLUSIVE diagnosis. Compare incumbent and candidate challenge results, "
    "including failed repairs, new counterexamples, actual fault triggers, trial denominators and overhead. "
    "Distinguish same-contract policy comparisons from separately fingerprinted capability demonstrations. "
    "Explain any external-agent result with its source provenance and limitations. Recommend up to three "
    "bounded next development experiments, with a reason and cited evidence; suggestions are advisory and "
    "may not reopen this campaign. Distinguish completed, safe unresolved, correctly rejected, violation, "
    "interrupted and lab-error records. Do not claim global minimality, universal impossibility, statistical "
    "certainty or an unbreakable repair from these samples. Create a report linked to the evidence. Do not "
    "change policies, checker rules, contracts, test splits, budgets or promotion decisions. Do not request "
    "private promotion or final-audit manifests."
)


class AriaBridge:
    def __init__(self, worker, outbox, *, project: str):
        self.worker, self.outbox, self.project = worker, outbox, project

    async def publish_campaign(self, campaign_id: str, *, completed: bool, development_summary: dict,
                               verified_links: list[dict], evidence_table: list[dict], authorize):
        if not completed:
            raise TelemetryError("The development campaign must be complete before Aria publication.")
        existing = self.outbox.store.get_record("aria_runs", campaign_id)
        if existing:
            return existing
        prior_attempt = self.outbox.store.get_record("aria_publish_intents", campaign_id)
        if prior_attempt:
            # A timed-out finish may already have triggered Aria. Resuming a
            # Finished run could trigger twice; require observed UI reconciliation.
            return {"campaign_id": campaign_id, "state": "publication_unverified",
                    "reason": "Prior publication outcome is uncertain; inspect its W&B run in the UI before remediation."}
        if not verified_links or not evidence_table:
            raise TelemetryError("Aria requires verified links and substantive observed development evidence.")
        for link in verified_links:
            if (link.get("status") != "weave_verified" or link.get("split") != "development"
                    or link.get("experiment_purpose") in {"selection_comparison", "promotion", "portability", "final_audit"}
                    or not authorize(link)):
                raise TelemetryError("Aria source is not authorized campaign development evidence.")
            wandb_url(link["url"])
        for row in evidence_table:
            if row.get("split") != "development" or row.get("experiment_purpose") == "selection_comparison":
                raise TelemetryError("Protected study detail cannot enter the development Aria run.")
        summary = public_json({"campaign_id": campaign_id, "source_mode": "live", "metrics": development_summary,
                               "verified_weave_links": verified_links, "evidence_table": evidence_table,
                               "association": "explicit_prior_verified_references", "analysis_role": "advisory_only"})
        run_id = "fl" + digest({"project": self.project, "campaign_id": campaign_id})[:30]
        payload = {"run_id": run_id, "name": f"faultlab-campaign-{campaign_id}", "summary": summary}
        job = self.outbox.enqueue("campaign", campaign_id, payload)
        self.outbox.store.put_record("aria_publish_intents", campaign_id,
            {"campaign_id": campaign_id, "requested_run_id": run_id, "started_at": utc_now()}, immutable=True)
        result_record = None
        async def upload(saved):
            nonlocal result_record
            if not all(authorize(link) for link in saved["summary"]["verified_weave_links"]):
                raise TelemetryError("Aria evidence authorization expired.")
            result = await self.worker.request("campaign_bridge", saved, timeout_seconds=60)
            if result.get("run_id") != run_id:
                raise TelemetryError("W&B campaign run identity mismatch.")
            url = wandb_url(result["url"])
            result_record = {"campaign_id": campaign_id, "run_id": run_id, "url": url,
                             "name": saved["name"], "state": "awaiting_aria_verification",
                             "published_at": utc_now(), "summary_digest": digest(saved["summary"]),
                             "invocation_verified": False, "analysis_verified": False}
            self.outbox.store.put_record("aria_runs", campaign_id, result_record, immutable=True)
            return url
        result = await self.outbox.deliver(job["outbox_id"], upload)
        return result_record or {"campaign_id": campaign_id, "state": "publication_pending", "outbox_id": result["outbox_id"]}


def validate_automation_setup(record: dict, *, project: str) -> dict:
    data = public_json(record)
    required = {"project", "automation_id", "team_confirmed", "smart_features_enabled", "ask_aria_observed",
                "event", "run_name_filter", "action", "prompt", "configuration_url", "recorder", "observed_at"}
    if set(data) != required or data["project"] != project:
        raise TelemetryError("Aria setup requires exact observed project and configuration fields.")
    if data["event"] != "Finished" or data["run_name_filter"] != RUN_NAME_FILTER or data["action"] != "Trigger ARIA":
        raise TelemetryError("Aria automation does not match the reviewed campaign trigger.")
    if data["prompt"] != ARIA_PROMPT or len(data["prompt"]) > 4000:
        raise TelemetryError("Aria automation prompt differs from the reviewed prompt.")
    if not all(data[k] is True for k in ("team_confirmed", "smart_features_enabled", "ask_aria_observed")):
        raise TelemetryError("Aria team/Smart-feature access remains unverified.")
    if not all(data[k] for k in ("automation_id", "recorder", "observed_at")):
        raise TelemetryError("Observed Aria setup provenance is incomplete.")
    wandb_url(data["configuration_url"])
    return data


def validate_analysis_capture(analysis, *, campaign_run: dict, automation_id: str) -> dict:
    from app.contracts.models import AriaAnalysis
    record = AriaAnalysis.model_validate_json(json.dumps(public_json(analysis))).model_dump(mode="json")
    if (record["campaign_id"] != campaign_run["campaign_id"] or record["run_id"] != campaign_run["run_id"]
            or record["automation_id"] != automation_id):
        raise TelemetryError("Aria evidence does not match the registered campaign run and automation.")
    for key in ("history_url", "output_url"):
        if record[key]:
            wandb_url(record[key])
    output_observed = bool(record["output_url"] and record["summary"].strip() and record["recorder"].strip())
    automatic_observed = (record["status"] == "COMPLETED" and record["invocation_mode"] == "automatic"
                          and bool(record["history_url"] and record["execution_id"]) and output_observed)
    return {"analysis": public_json(record), "automatic_evidence_complete": automatic_observed,
            "remote_verification": False, "evidence_provenance": "manual_ui_capture",
            "state": "automatic_output_observed" if automatic_observed else "manual_output_observed"
            if output_observed and record["invocation_mode"] == "manual" else "pending_unverified"}
