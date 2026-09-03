from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol

from chatgpt_client.errors import ResponseGenerationError
from chatgpt_client.models import GeneratedResponse


@dataclass(frozen=True, slots=True)
class OpenAIClientConfig:
    api_key: str = field(repr=False)
    base_url: str | None = None
    timeout_seconds: float = 120.0
    max_retries: int = 2
    organization: str | None = None
    project: str | None = None


class TextGenerator(Protocol):
    def generate(self, prompt: str, *, model: str, store: bool = False) -> GeneratedResponse:
        """Generate one text response."""


class OpenAIResponsesClient:
    """Thin adapter around the official OpenAI Python SDK."""

    def __init__(
        self,
        config: OpenAIClientConfig,
    ) -> None:
        try:
            openai = import_module("openai")
        except ImportError as exc:  # pragma: no cover - installation failure
            raise ResponseGenerationError(
                "The OpenAI SDK is not installed. Run `python -m pip install -e .`."
            ) from exc

        options: dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        options.update(
            _defined_options(
                base_url=config.base_url,
                organization=config.organization,
                project=config.project,
            )
        )
        self._client: Any = openai.OpenAI(**options)
        self._openai_error: type[Exception] = openai.OpenAIError

    def generate(self, prompt: str, *, model: str, store: bool = False) -> GeneratedResponse:
        if not prompt.strip():
            raise ResponseGenerationError("Prompt must not be empty.")
        if not model.strip():
            raise ResponseGenerationError("Model must not be empty.")

        try:
            response = self._client.responses.create(
                model=model,
                input=prompt,
                store=store,
            )
        except self._openai_error as exc:
            raise ResponseGenerationError(
                f"OpenAI request failed: {exc}",
                request_id=_string_attribute(exc, "request_id"),
                status_code=_integer_attribute(exc, "status_code"),
            ) from exc

        output_text = getattr(response, "output_text", None)
        text = output_text.strip() if isinstance(output_text, str) else ""
        if not text:
            raise ResponseGenerationError(
                "OpenAI returned a response without text output.",
                request_id=_string_attribute(response, "_request_id"),
            )

        response_id = _string_attribute(response, "id")
        if not response_id:
            raise ResponseGenerationError(
                "OpenAI returned a response without an id.",
                request_id=_string_attribute(response, "_request_id"),
            )

        return GeneratedResponse(
            response_id=response_id,
            request_id=_string_attribute(response, "_request_id"),
            model=_string_attribute(response, "model") or model,
            text=text,
        )


def _defined_options(**values: str | None) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def _string_attribute(value: object, name: str) -> str | None:
    attribute = getattr(value, name, None)
    return attribute if isinstance(attribute, str) and attribute else None


def _integer_attribute(value: object, name: str) -> int | None:
    attribute = getattr(value, name, None)
    return attribute if isinstance(attribute, int) else None
