"""The claude-code provider: the Claude Code CLI on the owner's subscription, driven through a fake CLI."""
import asyncio
import json
import os
import stat
from datetime import date

import pytest

from app.config import ConfigurationError, Settings
from app.providers.catalog import client_spec, parse_model_ref, request_profile
from app.providers.runtime import RuntimeProvider, RuntimeProviderError
from app.providers.spend import SpendLedger

SUCCESS = {"type": "result", "subtype": "success", "is_error": False, "result": '{"ok": true}',
           "usage": {"input_tokens": 401, "output_tokens": 25, "cache_creation_input_tokens": 7, "cache_read_input_tokens": 3},
           "total_cost_usd": 0.002104, "duration_api_ms": 781, "num_turns": 1,
           "modelUsage": {"claude-haiku-5-5": {"inputTokens": 401, "outputTokens": 25, "canonicalModel": "claude-haiku-5-5"}}}


def fake_cli(tmp_path, result: dict, *, sleep: float = 0.0, raw: str | None = None):
    """A stand-in for ``claude``: records argv, stdin and its environment, then prints the given result."""
    record = tmp_path / "record.json"
    body = f'''#!/usr/bin/env python3
import json, os, sys, time
prompt = sys.stdin.read()
json.dump({{"argv": sys.argv[1:], "stdin": prompt, "env": sorted(os.environ), "cwd": os.getcwd()}}, open({str(record)!r}, "w"))
time.sleep({sleep})
sys.stdout.write({(raw if raw is not None else json.dumps(result))!r})
'''
    script = tmp_path / "fake-claude"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script, record


def priced_settings(tmp_path, script, **overrides):
    table = tmp_path / "pricing.json"
    table.write_text(json.dumps({"schema": "faultlab-pricing-table/v1", "entries": [
        {"ref": "anthropic:claude-haiku-5-5", "input_per_million": 0.1, "output_per_million": 0.5, "verified": True,
         "verified_on": date.today().isoformat(), "source": "test"}]}))
    values = dict(faultlab_live_enabled=True, faultlab_read_only=False, faultlab_weave_enabled=False,
                  faultlab_actor_model="claude-code:claude-haiku-5-5", faultlab_claude_code_bin=str(script),
                  faultlab_pricing_table=str(table), faultlab_dollar_cap=60.0, faultlab_monthly_dollar_cap=5.0)
    values.update(overrides)
    return Settings(**values)


def test_the_reference_profile_and_spec_name_the_subscription_channel(tmp_path):
    ref = parse_model_ref("claude-code:claude-sonnet-5-5")
    assert (ref.provider, ref.model_id, ref.ref) == ("claude-code", "claude-sonnet-5-5", "claude-code:claude-sonnet-5-5")
    frozen = request_profile(ref).frozen()
    assert frozen["provider"] == "claude-code" and frozen["temperature"] is None and not frozen["response_format_enforced"]
    assert frozen["extra_body"] == {"channel": "subscription", "transport": "claude -p"}
    script, _ = fake_cli(tmp_path, SUCCESS)
    assert client_spec(ref, priced_settings(tmp_path, script)).configured
    missing = client_spec(ref, priced_settings(tmp_path, script, faultlab_claude_code_bin=str(tmp_path / "absent"))).missing
    assert missing == ("FAULTLAB_CLAUDE_CODE_BIN",)
    with pytest.raises(ConfigurationError) as refused:
        priced_settings(tmp_path, script, faultlab_claude_code_bin=str(tmp_path / "absent")).require_live()
    assert "FAULTLAB_CLAUDE_CODE_BIN" in refused.value.missing_fields
    priced_settings(tmp_path, script).require_live()          # the fake binary and the shadow price satisfy it


def test_shadow_pricing_bounds_a_subscription_model_at_the_api_price(tmp_path):
    script, _ = fake_cli(tmp_path, SUCCESS)
    settings = priced_settings(tmp_path, script)
    assert settings.model_rates_for_role("actor") == (0.1, 0.5)
    assert settings.per_call_dollar_bound_for_role("actor") == pytest.approx(0.0042)   # 32,000 in + 2,000 out


def test_a_call_runs_the_cli_scrubbed_and_records_tokens_cost_and_a_zero_ledger_row(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-reach-the-cli")
    monkeypatch.setenv("CLAUDECODE", "1")
    script, record = fake_cli(tmp_path, SUCCESS)
    settings = priced_settings(tmp_path, script)
    ledger = SpendLedger(tmp_path / "ledger.sqlite3")
    provider = RuntimeProvider(settings, live_authorized=True, spend_ledger=ledger)
    generation = asyncio.run(provider.complete([{"role": "system", "content": "You are the Actor."},
                                                {"role": "user", "content": '{"task": "upgrade"}'}], max_output_tokens=1500))
    assert generation.content == '{"ok": true}' and generation.provider == "claude-code"
    assert generation.model_id == "claude-code:claude-haiku-5-5" and not generation.structured_output_enforced
    assert generation.input_tokens == 411 and generation.output_tokens == 25     # cache tokens count as input
    assert generation.cost_usd == pytest.approx((411 * 0.1 + 25 * 0.5) / 1e6)      # the API-equivalent cost
    seen = json.loads(record.read_text())
    argv = seen["argv"]
    assert argv[:1] == ["-p"] and argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--system-prompt") + 1] == "You are the Actor." and seen["stdin"] == '{"task": "upgrade"}'
    for flag in ("--output-format", "--tools", "--max-turns", "--no-session-persistence", "--setting-sources", "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--setting-sources") + 1] == ""
    assert "ANTHROPIC_API_KEY" not in seen["env"] and "CLAUDECODE" not in seen["env"]
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" in seen["env"] and "HOME" in seen["env"]
    assert seen["cwd"].startswith(os.path.realpath(os.path.dirname(seen["cwd"])))   # an empty temp directory
    assert not os.listdir(seen["cwd"])
    summary = ledger.summary()
    assert summary.calls == 1 and summary.reserved_bound == 0 and summary.settled_actual == 0 and summary.committed == 0
    row = ledger._connect().execute("SELECT provider, model, note, input_tokens, output_tokens FROM charges").fetchone()
    assert row[:2] == ("claude-code", "claude-code:claude-haiku-5-5") and row[2].startswith("subscription; api-equivalent bound 0.0042")
    assert row[3:] == (411, 25)
    asyncio.run(provider.close())
    assert not os.path.isdir(seen["cwd"])


def test_a_transcript_with_assistant_turns_is_rendered_into_the_single_prompt(tmp_path):
    script, record = fake_cli(tmp_path, SUCCESS)
    provider = RuntimeProvider(priced_settings(tmp_path, script), live_authorized=True, spend_ledger=SpendLedger(tmp_path / "l.sqlite3"))
    asyncio.run(provider.complete([{"role": "system", "content": "S"}, {"role": "user", "content": "first"},
                                   {"role": "assistant", "content": "draft"}, {"role": "user", "content": "correct it"}]))
    prompt = json.loads(record.read_text())["stdin"]
    assert prompt.startswith("The conversation so far") and "[user]\nfirst" in prompt and "[assistant]\ndraft" in prompt
    assert prompt.endswith("[user]\ncorrect it")


@pytest.mark.parametrize("result,code,error_class", [
    ({**SUCCESS, "is_error": True, "result": "Not logged in · Please run /login", "modelUsage": {}}, "PROVIDER_ERROR", "AuthenticationError"),
    ({**SUCCESS, "is_error": True, "result": "Prompt is too long", "api_error_status": 400, "modelUsage": {}}, "PROVIDER_ERROR", "BadRequestError"),
    ({**SUCCESS, "result": "   "}, "EMPTY_FINAL_RESPONSE", "ValueError"),
    ({**SUCCESS, "modelUsage": {"claude-opus-5-5": {}}}, "INVALID_RESPONSE_SHAPE", "ValueError"),
])
def test_cli_failures_become_safe_runtime_errors(tmp_path, result, code, error_class):
    script, _ = fake_cli(tmp_path, result)
    provider = RuntimeProvider(priced_settings(tmp_path, script), live_authorized=True, spend_ledger=SpendLedger(tmp_path / "l.sqlite3"))
    with pytest.raises(RuntimeProviderError) as refused:
        asyncio.run(provider.complete([{"role": "user", "content": "x"}]))
    assert (refused.value.code, refused.value.error_class) == (code, error_class)
    assert "login" not in str(refused.value).lower()        # the CLI's text is never retained


def test_non_json_output_and_a_slow_cli_are_refused_without_retry(tmp_path):
    script, _ = fake_cli(tmp_path, SUCCESS, raw="not json at all")
    provider = RuntimeProvider(priced_settings(tmp_path, script), live_authorized=True, spend_ledger=SpendLedger(tmp_path / "l.sqlite3"))
    with pytest.raises(RuntimeProviderError) as refused:
        asyncio.run(provider.complete([{"role": "user", "content": "x"}]))
    assert refused.value.code == "INVALID_RESPONSE_SHAPE"
    slow, _ = fake_cli(tmp_path, SUCCESS, sleep=3.0)
    provider = RuntimeProvider(priced_settings(tmp_path, slow), live_authorized=True, spend_ledger=SpendLedger(tmp_path / "l2.sqlite3"))
    with pytest.raises(RuntimeProviderError) as refused:
        asyncio.run(provider.complete([{"role": "user", "content": "x"}], timeout_seconds=0.5))
    assert (refused.value.code, refused.value.error_class) == ("REQUEST_TIMEOUT", "TimeoutError")
