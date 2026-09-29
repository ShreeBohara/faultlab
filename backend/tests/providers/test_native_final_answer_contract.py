"""The native final-answer response contract (native adapter v2's strict final-report turn).

A new, separate contract beside the reference Actor's 'actor_final_report'. The existing contracts keep
their exact bytes and hashes (pinned below from the code before this contract existed). Offline: fake client.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import ReportAction, TaskReport, content_hash
from app.providers.runtime import (NATIVE_FINAL_ANSWER_CONTRACT, RuntimeProvider, RuntimeProviderError,
                                   actor_response_protocol, native_final_answer_protocol, response_format_for,
                                   validate_request_input)

# Captured before the native contract was added (identity-before.json, September 29, 2026).
JSON_OBJECT_FORMAT_HASH = "376bde7986cc2f8fd182f04e745c607933760bea7c306ea6e8e992b7f70be25a"
ACTOR_FINAL_REPORT_FORMAT_HASH = "0576de04398fe472089a77baa1620f9050094e0c5e4c350d38ba4950cdb7dd32"
ACTOR_RESPONSE_PROTOCOL_HASH = "4e6455acf31e4b45fa3e95c2eb225123b2211f8c74a4b7d805f2073d80a43ae5"


def test_existing_contracts_keep_their_bytes_and_hashes():
    assert content_hash(response_format_for()) == JSON_OBJECT_FORMAT_HASH
    assert content_hash(response_format_for(response_contract="actor_final_report")) == ACTOR_FINAL_REPORT_FORMAT_HASH
    assert content_hash(actor_response_protocol()) == ACTOR_RESPONSE_PROTOCOL_HASH
    assert response_format_for(response_contract="actor_final_report")["json_schema"]["schema"] == ReportAction.model_json_schema()
    assert actor_response_protocol()["response_contract"] == "actor_final_report"


def test_native_contract_is_exactly_the_native_final_answer_action():
    fmt = response_format_for(response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "FaultLabNativeFinalAnswer"
    schema = fmt["json_schema"]["schema"]
    assert schema["required"] == ["name", "arguments"] and schema["additionalProperties"] is False
    assert schema["properties"]["name"] == {"const": "final_answer", "title": "Name", "type": "string"}
    arguments = schema["$defs"][schema["properties"]["arguments"]["$ref"].rsplit("/", 1)[1]]
    assert arguments["required"] == ["answer"] and arguments["additionalProperties"] is False
    assert arguments["properties"]["answer"] == {"$ref": "#/$defs/TaskReport"}
    report = TaskReport.model_json_schema()
    assert schema["$defs"]["TaskReport"] == {key: value for key, value in report.items() if key != "$defs"}
    for name, definition in report["$defs"].items():
        assert schema["$defs"][name] == definition
    assert fmt != response_format_for(response_contract="actor_final_report")


def test_native_protocol_descriptor():
    protocol = native_final_answer_protocol()
    fmt = response_format_for(response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
    assert protocol["response_contract"] == "native_final_answer" and protocol["scope"] == "smolagents_native_adapter_v2"
    assert protocol["response_format"] == fmt and protocol["response_format_hash"] == content_hash(fmt)
    assert protocol["schema_hash"] == content_hash(fmt["json_schema"]["schema"])


@pytest.mark.parametrize("role", ["explorer", "mechanic"])
def test_native_contract_is_actor_only(role):
    provider = RuntimeProvider(Settings(wandb_api_key="fixture-key", wandb_entity="fixture", wandb_project="project", wandb_model="model"),
        live_authorized=True, client_factory=lambda **_: pytest.fail("Client created for a role-incompatible contract"))
    with pytest.raises(RuntimeProviderError) as error:
        asyncio.run(provider.complete([{"role": "user", "content": "hello"}], role=role, response_contract=NATIVE_FINAL_ANSWER_CONTRACT))
    assert error.value.code == "INVALID_INPUT"


def test_provider_sends_the_native_schema_and_returns_the_answer_unrepaired():
    calls = []
    original = '{"name":"get_order","arguments":{}}'      # a provider that ignores the schema is not repaired
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=original))], usage=None)
    settings = Settings(wandb_api_key="fixture-key", wandb_entity="fixture", wandb_project="project", wandb_model="deepseek-ai/DeepSeek-V3.1")
    provider = RuntimeProvider(settings, live_authorized=True,
        client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    messages = [{"role": "user", "content": "Final turn."}]
    returned = asyncio.run(provider.complete(messages, response_contract=NATIVE_FINAL_ANSWER_CONTRACT))
    assert len(calls) == 1 and calls[0]["messages"] == messages
    assert calls[0]["response_format"] == response_format_for(response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
    assert returned.content == original


def test_admission_counts_the_native_schema():
    model = "unregistered-byte-bound-model"
    plain = validate_request_input([{"role": "user", "content": "x"}], model)
    native = validate_request_input([{"role": "user", "content": "x"}], model, response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
    assert native > plain
    assert len(json.dumps(response_format_for(response_contract=NATIVE_FINAL_ANSWER_CONTRACT))) < 4000
