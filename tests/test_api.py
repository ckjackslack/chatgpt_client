from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from chatgpt_client.api import OpenAIClientConfig, OpenAIResponsesClient
from chatgpt_client.errors import ResponseGenerationError


class FakeOpenAIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.status_code = status_code


class FakeResponse:
    id: object = "resp_123"
    _request_id: object = "req_123"
    model: object = "resolved-model"
    output_text: object = " generated text "


class ResponsesEndpoint:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class SDKHarness:
    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        response: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.endpoint = ResponsesEndpoint(response, error)
        self.options: dict[str, Any] | None = None
        harness = self

        class OpenAI:
            def __init__(self, **options: Any) -> None:
                harness.options = options
                self.responses = harness.endpoint

        module = ModuleType("openai")
        module.OpenAI = OpenAI  # type: ignore[attr-defined]
        module.OpenAIError = FakeOpenAIError  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "openai", module)


def test_client_configuration_and_responses_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = SDKHarness(monkeypatch)
    config = OpenAIClientConfig(
        api_key="secret",
        base_url="https://example.test/v1",
        timeout_seconds=42,
        max_retries=3,
        organization="org_test",
        project="project_test",
    )

    result = OpenAIResponsesClient(config).generate(
        "hello",
        model="chosen-model",
        store=False,
    )

    assert sdk.options == {
        "api_key": "secret",
        "base_url": "https://example.test/v1",
        "timeout": 42,
        "max_retries": 3,
        "organization": "org_test",
        "project": "project_test",
    }
    assert sdk.endpoint.calls == [
        {"model": "chosen-model", "input": "hello", "store": False}
    ]
    assert result.response_id == "resp_123"
    assert result.request_id == "req_123"
    assert result.model == "resolved-model"
    assert result.text == "generated text"


def test_optional_sdk_options_are_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = SDKHarness(monkeypatch)
    OpenAIResponsesClient(OpenAIClientConfig(api_key="secret"))
    assert sdk.options == {"api_key": "secret", "timeout": 120.0, "max_retries": 2}


def test_client_config_repr_does_not_expose_api_key() -> None:
    assert "top-secret" not in repr(OpenAIClientConfig(api_key="top-secret"))


@pytest.mark.parametrize(("prompt", "model"), [("", "model"), ("  ", "model"), ("hi", "")])
def test_empty_input_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    model: str,
) -> None:
    sdk = SDKHarness(monkeypatch)
    client = OpenAIResponsesClient(OpenAIClientConfig(api_key="secret"))
    with pytest.raises(ResponseGenerationError, match="must not be empty"):
        client.generate(prompt, model=model)
    assert sdk.endpoint.calls == []


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("output_text", None, "without text output"),
        ("output_text", "  ", "without text output"),
        ("id", None, "without an id"),
        ("id", 123, "without an id"),
    ],
)
def test_malformed_sdk_response_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    value: object,
    message: str,
) -> None:
    response = FakeResponse()
    setattr(response, attribute, value)
    SDKHarness(monkeypatch, response=response)
    client = OpenAIResponsesClient(OpenAIClientConfig(api_key="secret"))
    with pytest.raises(ResponseGenerationError, match=message):
        client.generate("hello", model="model")


@pytest.mark.parametrize(
    ("attribute", "value"),
    [("output_text", None), ("id", None)],
)
def test_malformed_response_preserves_request_id(
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    value: object,
) -> None:
    response = FakeResponse()
    setattr(response, attribute, value)
    SDKHarness(monkeypatch, response=response)

    with pytest.raises(ResponseGenerationError) as raised:
        OpenAIResponsesClient(OpenAIClientConfig(api_key="secret")).generate(
            "hello",
            model="model",
        )

    assert raised.value.request_id == "req_123"


def test_sdk_error_preserves_diagnostic_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = FakeOpenAIError("rate limited", request_id="req_failed", status_code=429)
    SDKHarness(monkeypatch, error=failure)
    client = OpenAIResponsesClient(OpenAIClientConfig(api_key="secret"))

    with pytest.raises(ResponseGenerationError) as raised:
        client.generate("hello", model="model")

    assert raised.value.request_id == "req_failed"
    assert raised.value.status_code == 429
    assert "status=429" in str(raised.value)
    assert "request_id=req_failed" in str(raised.value)
