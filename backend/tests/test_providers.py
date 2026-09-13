"""Provider safeguards tested with fake responses, never local credentials."""

import logging
import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

import check_provider
from app.config import ConfigurationError, Settings
from app.providers import ProviderCheckError
from app.providers import typesafe, wandb_inference, weave_tracing


@pytest.fixture
def configured():
    return Settings(
        wandb_api_key="dummy-private-key",
        wandb_entity="test-credited-entity",
        wandb_project="faultlab",
        wandb_model="model-from-fake-list",
        typesafe_api_key="dummy-typesafe-key",
    )


class FakeInferenceClient:
    def __init__(self, model_ids=("model-from-fake-list",), error=None, response="FaultLab connection OK"):
        self.list_requests = 0
        self.generations = []
        self.model_ids = model_ids
        self.error = error
        self.response = response
        self.models = SimpleNamespace(list=self.list)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def list(self):
        self.list_requests += 1
        return SimpleNamespace(data=[SimpleNamespace(id=model) for model in self.model_ids])

    def create(self, **kwargs):
        self.generations.append(kwargs)
        if self.error:
            print(self.error, file=sys.stderr)
            logging.getLogger("openai").critical(str(self.error))
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.response))])


class FakeWeave:
    def __init__(self, *, persist=True, init_error=None):
        self.persist = persist
        self.init_error = init_error
        self.events = []
        self.traced_inputs = None
        self.traced_output = None

    def init(self, project, *, settings):
        self.events.append("init")
        self.project = project
        self.settings = settings.copy()
        self.explicit_key = os.environ["WANDB_API_KEY"]
        self.http_endpoint = os.environ["WF_TRACE_SERVER_URL"]
        if self.init_error:
            raise self.init_error
        return self

    def op(self, *, name):
        def decorate(fn):
            def call(*args):
                self.traced_inputs = args
                self.traced_output = fn(*args)
                return self.traced_output, SimpleNamespace(id="test-call-id", ui_url="https://wandb.ai/test-credited-entity/faultlab/r/call/test-call-id")
            return SimpleNamespace(call=call)
        return decorate

    def flush(self):
        self.events.append("flush")

    def get_call(self, call_id):
        self.events.append("read")
        if not self.persist:
            raise RuntimeError("dummy-private-key failed to upload")
        return SimpleNamespace(id=call_id, project_id=self.project, ended_at="completed")

    def finish(self):
        self.events.append("finish")


def use_fakes(monkeypatch, client, weave=None):
    monkeypatch.setattr(wandb_inference, "_client", lambda settings: client)
    fake = weave or FakeWeave()
    monkeypatch.setitem(sys.modules, "weave", fake)
    return fake


def test_actual_openai_constructor_has_explicit_attribution_and_zero_retries(configured):
    # Construct the installed SDK client, without performing any HTTP requests.
    with wandb_inference._client(configured) as client:
        assert str(client.base_url) == "https://api.inference.wandb.ai/v1/"
        assert client.api_key == configured.wandb_api_key
        assert client.project == configured.project_path
        assert client.timeout == 20.0
        assert client.max_retries == 0


def test_actual_weave_settings_and_op_signature_are_compatible(monkeypatch):
    monkeypatch.setenv("WANDB_ERROR_REPORTING", "false")
    import weave
    from weave.trace.settings import UserSettings

    settings = UserSettings(**weave_tracing.WEAVE_SETTINGS)
    assert settings.capture_code is False
    assert settings.implicitly_patch_integrations is False
    assert settings.retry_max_attempts == 1
    assert settings.http_timeout == 20.0

    @weave.op(name="offline_signature_check")
    def uncalled(model: str):
        raise AssertionError("Must not execute")

    assert callable(uncalled.call)


def test_actual_weave_logger_accepts_frozen_environment_level(configured):
    from weave.trace.display.term import logger, update_logger_level
    previous_level = logger.level
    previous_environment = os.environ.get("WEAVE_LOG_LEVEL")
    try:
        with weave_tracing._weave_environment(configured):
            assert os.environ["WEAVE_LOG_LEVEL"] == "CRITICAL"
            assert os.environ["WEAVE_CAPTURE_CODE"] == "false"
            update_logger_level()  # Real SDK call, no init or network.
            assert logger.level == logging.CRITICAL
        assert os.environ.get("WEAVE_LOG_LEVEL") == previous_environment
    finally:
        logger.setLevel(previous_level)


def test_missing_config_prevents_client_creation(monkeypatch):
    monkeypatch.setattr(wandb_inference, "_client", lambda _: pytest.fail("Created client without config"))
    with pytest.raises(ConfigurationError):
        wandb_inference.list_models(Settings())
    with pytest.raises(ConfigurationError):
        wandb_inference.generate_once(Settings())


def test_list_models_never_initializes_weave_or_generates(configured, monkeypatch):
    client = FakeInferenceClient(model_ids=("model-b", "model-a", "model-a"))
    fake = use_fakes(monkeypatch, client)
    assert wandb_inference.list_models(replace(configured, wandb_model="")) == ["model-a", "model-b"]
    assert client.list_requests == 1
    assert client.generations == []
    assert fake.events == []


def test_unavailable_model_prevents_generation_and_tracing(configured, monkeypatch):
    client = FakeInferenceClient(model_ids=("different-available-model",))
    fake = use_fakes(monkeypatch, client)
    with pytest.raises(ProviderCheckError, match="not in the available model list"):
        wandb_inference.generate_once(configured)
    assert client.list_requests == 1
    assert client.generations == []
    assert fake.events == []


def test_single_generation_has_small_output_and_verified_trace(configured, monkeypatch):
    client = FakeInferenceClient()
    fake = use_fakes(monkeypatch, client)
    monkeypatch.setenv("WANDB_API_KEY", "other-global-key")
    monkeypatch.setenv("WEAVE_CAPTURE_CODE", "true")
    result = wandb_inference.generate_once(configured)
    assert client.list_requests == 1
    assert len(client.generations) == 1
    assert client.generations[0] == {
        "model": configured.wandb_model,
        "messages": [{"role": "user", "content": wandb_inference.CHECK_PROMPT}],
        "max_tokens": 32,
        "stream": False,
    }
    assert fake.project == configured.project_path
    assert fake.explicit_key == configured.wandb_api_key
    assert fake.http_endpoint == "https://trace.wandb.ai"
    assert fake.traced_inputs == (configured.wandb_model,)
    assert configured.wandb_api_key not in repr(fake.traced_output)
    assert fake.events == ["init", "flush", "read", "finish"]
    assert result.response == "FaultLab connection OK"
    assert result.trace_url.endswith("/r/call/test-call-id")
    assert os.environ["WANDB_API_KEY"] == "other-global-key"
    assert os.environ["WEAVE_CAPTURE_CODE"] == "true"


def test_provider_exception_is_not_logged_traced_or_retried(configured, monkeypatch, capsys):
    client = FakeInferenceClient(error=RuntimeError(f"Authorization: Bearer {configured.wandb_api_key}"))
    fake = use_fakes(monkeypatch, client)
    with pytest.raises(ProviderCheckError) as caught:
        wandb_inference.generate_once(configured)
    captured = capsys.readouterr()
    assert len(client.generations) == 1
    assert fake.traced_output == {"ok": False, "error": "Inference request failed; no retry was made."}
    assert configured.wandb_api_key not in str(caught.value) + captured.out + captured.err + repr(fake.traced_output)


def test_explicit_output_cap_reaches_single_generation(configured, monkeypatch):
    client = FakeInferenceClient()
    use_fakes(monkeypatch, client)
    wandb_inference.generate_once(configured, max_output_tokens=2000)
    assert len(client.generations) == 1 and client.generations[0]["max_tokens"] == 2000


@pytest.mark.parametrize("limit", [0, 2001, -1, True, "2000"])
def test_invalid_direct_output_cap_precedes_client(configured, monkeypatch, limit):
    monkeypatch.setattr(wandb_inference, "_client", lambda _: pytest.fail("Client created for invalid token cap"))
    with pytest.raises(ProviderCheckError, match="1 to 2000"):
        wandb_inference.generate_once(configured, max_output_tokens=limit)


@pytest.mark.parametrize("flag,expected", [([], 32), (["--max-output-tokens", "2000"], 2000)])
def test_cli_forwards_output_cap_and_discloses_bound(configured, monkeypatch, capsys, flag, expected):
    calls = []
    monkeypatch.setattr(Settings, "from_env", lambda **_: configured)
    def generate(settings, *, max_output_tokens):
        calls.append((settings, max_output_tokens))
        return wandb_inference.GenerationResult("fixture response", "https://wandb.ai/fixture/project/call/fixture")
    monkeypatch.setattr(check_provider, "generate_once", generate)
    assert check_provider.main(["wandb", "--generate", "--confirm-entity", configured.wandb_entity, *flag]) == 0
    assert calls == [(configured, expected)]
    assert f"Generation limit: {expected} output tokens" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "2001", "-1", "many", "1.5"])
def test_cli_invalid_output_cap_rejected_before_settings_or_network(monkeypatch, value):
    monkeypatch.setattr(Settings, "from_env", lambda **_: pytest.fail("Loaded settings for invalid CLI input"))
    with pytest.raises(SystemExit) as caught:
        check_provider.main(["wandb", "--generate", "--max-output-tokens", value])
    assert caught.value.code == 2


def test_response_is_redacted_before_tracing(configured, monkeypatch):
    client = FakeInferenceClient(response=f"echo {configured.wandb_api_key} {configured.typesafe_api_key}")
    fake = use_fakes(monkeypatch, client)
    result = wandb_inference.generate_once(configured)
    assert result.response == "echo [redacted] [redacted]"
    assert fake.traced_output["response"] == result.response


def test_failed_trace_read_is_not_reported_as_success(configured, monkeypatch):
    client = FakeInferenceClient()
    fake = use_fakes(monkeypatch, client, FakeWeave(persist=False))
    with pytest.raises(ProviderCheckError, match="no successful trace is claimed") as caught:
        wandb_inference.generate_once(configured)
    assert caught.value.response == "FaultLab connection OK"
    assert configured.wandb_api_key not in str(caught.value)
    assert len(client.generations) == 1
    assert fake.events == ["init", "flush", "read", "finish"]


def test_weave_initialization_failure_prevents_generation(configured, monkeypatch):
    client = FakeInferenceClient()
    use_fakes(monkeypatch, client, FakeWeave(init_error=RuntimeError(configured.wandb_api_key)))
    with pytest.raises(ProviderCheckError) as caught:
        wandb_inference.generate_once(configured)
    assert configured.wandb_api_key not in str(caught.value)
    assert caught.value.response is None
    assert client.generations == []


@pytest.mark.parametrize("confirmation", [[], ["--confirm-entity", "another-entity"]])
def test_cli_requires_matching_entity_without_network(configured, monkeypatch, capsys, confirmation):
    monkeypatch.setattr(Settings, "from_env", lambda **_: configured)
    monkeypatch.setattr(check_provider, "list_models", lambda _: pytest.fail("Unconfirmed request"))
    assert check_provider.main(["wandb", "--list-models", *confirmation]) == 2
    assert "--confirm-entity" in capsys.readouterr().err


def test_typesafe_never_claims_configured_or_substitutes_wandb(configured, monkeypatch, capsys):
    populated = replace(configured, typesafe_base_url="https://placeholder.invalid", typesafe_model="placeholder")
    assert typesafe.configuration_status(populated) == "not configured — awaiting sponsor instructions"
    monkeypatch.setattr(Settings, "from_env", lambda **_: populated)
    monkeypatch.setattr(check_provider, "list_models", lambda _: pytest.fail("TypeSafe contacted W&B"))
    assert check_provider.main(["typesafe"]) == 2
    assert typesafe.STATUS in capsys.readouterr().out


def test_v4_smoke_disables_default_thinking(configured, monkeypatch):
    configured = replace(configured, wandb_model='deepseek-ai/DeepSeek-V4-Pro-0813')
    client = FakeInferenceClient(model_ids=(configured.wandb_model,))
    use_fakes(monkeypatch, client)
    result = wandb_inference.generate_once(configured, max_output_tokens=2000)
    assert result.response == 'FaultLab connection OK'
    assert len(client.generations) == 1
    assert client.generations[0]['extra_body'] == {'chat_template_kwargs': {'enable_thinking': False}}
    assert 'response_format' not in client.generations[0]
