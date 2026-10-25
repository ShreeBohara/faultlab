"""The Claude Agent adapter: Claude Code as the agent under test, driven by a scripted harness in place of the SDK's query."""
import asyncio
import json
import os

import pytest

import claude_agent_sdk as sdk
from faultlab.adapters import load_adapter, load_adapters
from faultlab.adapters.claude_agent import PROMPT_DIGEST, SYSTEM_PROMPT, TOOL_NAMES, ClaudeAgentAdapter
from faultlab.core import Caps
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab import TrialStore, TrialWorker
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee

ORDERS = load_pack("orders.upgrade_then_confirm/v1")
MODEL = "claude-haiku-5-5"
HARNESS_MODEL = "claude-haiku-5-5-20260401"
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=1.0)
RATES = (0.1, 0.5)
TURN_DOLLARS = (100 * 0.1 + 20 * 0.5) / 1e6


def run(coro):
    return asyncio.run(coro)


class ScriptedHarness:
    """A stand-in for ``claude_agent_sdk.query``: decides each tool call from the observations it was shown."""

    def __init__(self, adapter, *, silent=False, bad_report_first=False, fail_after=None, model=HARNESS_MODEL):
        self.adapter, self.silent, self.bad_report_first, self.fail_after, self.model = adapter, silent, bad_report_first, fail_after, model
        self.calls, self.seen, self.results, self.env_seen = [], [], [], None

    async def __call__(self, *, prompt, options):
        self.calls.append((prompt, options))
        self.env_seen = {key for key in os.environ if key.startswith(("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDECODE", "CLAUDE_CONFIG_DIR"))}
        turns = 0
        while turns < options.max_turns:
            if self.fail_after is not None and turns >= self.fail_after:
                raise RuntimeError("harness lost its process")
            name, arguments = self._decide()
            turns += 1
            yield sdk.AssistantMessage(content=[sdk.TextBlock(text=f"turn {turns}"),
                                                sdk.ToolUseBlock(id=f"tu-{turns}", name=f"mcp__faultlab__{name}", input=arguments)],
                                       model=self.model, usage={"input_tokens": 100, "output_tokens": 20})
            result = await self.adapter.handle(name, arguments)
            self.results.append((name, result))
            text = result["content"][0]["text"]
            if not result.get("is_error") and name != "report":
                self.seen.append(json.loads(text))
            yield sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id=f"tu-{turns}", content=text, is_error=result.get("is_error", False))])
            if name == "report" and not result.get("is_error"):
                break
        yield sdk.ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=turns, session_id="s")

    def _decide(self):
        if self.silent:
            return "get_order", {}
        tools = [o["tool"] for o in self.seen]
        if "get_order" not in tools:
            return "get_order", {}
        if "update_order" not in tools:
            return "update_order", {}
        upgrade = [o["result"].get("status") for o in self.seen
                   if o["tool"] in ("update_order", "get_operation_status") and str(o["result"].get("operation_id") or "").startswith("upgrade-")]
        last = upgrade[-1] if upgrade else None
        if last in ("PENDING", "UNKNOWN", None):
            return "get_operation_status", {"service": "orders"}
        if last == "SUCCEEDED" and "send_confirmation" not in tools:
            return "send_confirmation", {}
        return "report", self._report()

    def _report(self):
        if self.bad_report_first:
            self.bad_report_first = False
            return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "DONE", "evidence_ids": [],
                    "next_action": {"kind": "NONE"}}
        terminal = [o for o in self.seen if str(o["result"].get("operation_id") or "").startswith("upgrade-")
                    and o["result"].get("status") in ("SUCCEEDED", "FAILED")]
        confirmation = [o for o in self.seen if o["tool"] == "send_confirmation" and o["result"].get("status") == "SUCCEEDED"]
        if terminal and terminal[-1]["result"]["status"] == "FAILED":
            return {"upgrade_outcome": "FAILED", "notification_outcome": "NOT_REQUIRED", "overall": "CORRECTLY_REJECTED",
                    "evidence_ids": [terminal[-1]["evidence_id"]], "next_action": {"kind": "NONE"}}
        if terminal and confirmation:
            return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                    "evidence_ids": [terminal[-1]["evidence_id"], confirmation[-1]["evidence_id"]], "next_action": {"kind": "NONE"}}
        return {"upgrade_outcome": "UNKNOWN", "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
                "evidence_ids": [o["evidence_id"] for o in self.seen][-1:], "next_action": {"kind": "ESCALATE"}}


def adapter_with(**harness_options):
    adapter = ClaudeAgentAdapter(MODEL, cli_path="/usr/local/bin/claude-test", rates=RATES, sdk_version="0.2.174")
    harness = ScriptedHarness(adapter, **harness_options)
    adapter.query = harness
    return adapter, harness


@pytest.fixture
def worker(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        yield TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())


def trial(worker, scenario_id, adapter, attempt_id):
    plan = ORDERS.plan(scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=CAPS)
    return run(worker.run(plan, TrialAttempt(attempt_id=attempt_id, plan_hash=plan_hash(plan), lifecycle="READY"), adapter))


def test_the_adapter_carries_its_own_prompt_identity_and_the_subscription_channel():
    adapter, _ = adapter_with()
    manifest = adapter.manifest()
    assert manifest.adapter_id == "claude-agent" and manifest.model == "claude-code:claude-haiku-5-5"
    assert manifest.prompt_digest == PROMPT_DIGEST and manifest.settings_digest and adapter.supports(ORDERS.pack_id)
    other = ClaudeAgentAdapter("claude-code:claude-haiku-5-5", rates=RATES, sdk_version="0.0.1")
    assert other.model == MODEL and other.manifest().settings_digest != manifest.settings_digest
    with pytest.raises(ValueError):
        ClaudeAgentAdapter("claude-code:")
    assert [a.adapter_id for a in load_adapters()] == ["reference-orders"]          # the Claude Agent adapter needs a model
    assert load_adapter("claude-agent", model=MODEL, rates=RATES).adapter_id == "claude-agent"


def test_a_scripted_harness_completes_the_healthy_delayed_and_rejected_scenarios(worker):
    expected = {"dev-1": "COMPLETED", "dev-3": "COMPLETED", "dev-5": "CORRECTLY_REFUSED"}
    for scenario_id, task in expected.items():
        adapter, harness = adapter_with()
        envelope = trial(worker, scenario_id, adapter, f"trial-{scenario_id}")
        assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == task, (scenario_id, envelope.attempt.terminal_reason, envelope.source.notes)
        assert all(f.result == "PASS" for f in envelope.outcome.findings), [(f.property_id, f.note) for f in envelope.outcome.findings if f.result != "PASS"]
        assert envelope.outcome.claims.mismatches == []
        turns = len(adapter.turns)
        assert envelope.outcome.cost.model_calls == turns == len(harness.results) and turns <= 8
        assert envelope.outcome.cost.dollars_measured == pytest.approx(TURN_DOLLARS * turns)
        assert envelope.outcome.cost.input_tokens == 100 * turns and envelope.outcome.cost.output_tokens == 20 * turns
        assert envelope.outcome.identity.prompt_digest == PROMPT_DIGEST and envelope.outcome.identity.model == "claude-code:claude-haiku-5-5"
        # The harness cited labels; the submitted report carries the real evidence ids of delivered observations.
        cited = envelope.report.original["evidence_ids"]
        delivered = {e.payload["observation"]["evidence_id"] for e in envelope.events if e.kind == "response_delivered"}
        assert cited and set(cited) <= delivered
        assert all(label.startswith("obs-") for _, result in harness.results[:-1] for label in [json.loads(result["content"][0]["text"])["evidence_id"]])
        prompt, options = harness.calls[0]
        assert json.loads(prompt)["task"]["order_id"].startswith("order-") and json.loads(prompt)["limits"]["model_turns"] == 8
        assert options.model == MODEL and options.system_prompt == SYSTEM_PROMPT and options.max_turns == 8
        assert options.tools == [] and options.setting_sources == [] and options.strict_mcp_config and options.cli_path == "/usr/local/bin/claude-test"
        assert options.allowed_tools == [f"mcp__faultlab__{name}" for name in TOOL_NAMES] and list(options.mcp_servers) == ["faultlab"]
        assert options.env["ANTHROPIC_API_KEY"] == "" and options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "2000"
        assert options.cwd and not os.listdir(options.cwd)
        adapter.cleanup()
        assert not os.path.isdir(options.cwd)


def test_the_cli_inherits_no_api_key_and_the_environment_is_restored(worker, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-reach-the-cli")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "desktop-session")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/claude-config")
    adapter, harness = adapter_with()
    trial(worker, "dev-1", adapter, "trial-env")
    assert harness.env_seen == {"CLAUDE_CONFIG_DIR"}          # the config directory passes through; nothing else does
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-must-not-reach-the-cli" and os.environ["CLAUDE_CODE_SESSION_ID"] == "desktop-session"


def test_an_invalid_report_is_refused_and_the_corrected_one_counts(worker):
    adapter, harness = adapter_with(bad_report_first=True)
    envelope = trial(worker, "dev-1", adapter, "trial-report")
    assert envelope.outcome.task == "COMPLETED"
    reports = [result for name, result in harness.results if name == "report"]
    assert len(reports) == 2 and reports[0].get("is_error") and "report_errors" in reports[0]["content"][0]["text"] and not reports[1].get("is_error")
    assert envelope.outcome.cost.model_calls == len(adapter.turns) == len(harness.results)


def test_a_harness_that_never_reports_ends_without_one(worker):
    adapter, harness = adapter_with(silent=True)
    envelope = trial(worker, "dev-1", adapter, "trial-silent")
    assert envelope.report.status == "ABSENT" and envelope.outcome.cost.model_calls == 8 and len(harness.results) == 8
    assert envelope.outcome.task == "VIOLATION"


def test_a_harness_failure_is_infrastructure_not_the_task(worker):
    adapter, _ = adapter_with(fail_after=2)
    envelope = trial(worker, "dev-1", adapter, "trial-dead")
    assert envelope.outcome.execution == "INFRA_ERROR" and envelope.attempt.terminal_reason == "ADAPTER_ERROR:RuntimeError"
    adapter, _ = adapter_with(model="claude-opus-5-5-20260301")
    envelope = trial(worker, "dev-1", adapter, "trial-other-model")
    assert envelope.outcome.execution == "INFRA_ERROR" and envelope.attempt.terminal_reason == "ADAPTER_ERROR:RuntimeError"
