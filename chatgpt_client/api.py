from __future__ import annotations

from typing import Any, Protocol

from chatgpt_client.models import GeneratedResponse


class ResponseGenerationError(RuntimeError):
    """Raised when a response cannot be generated or decoded."""


class TextGenerator(Protocol):
    def generate(self, prompt: str, *, model: str, store: bool = False) -> GeneratedResponse:
        """Generate one text response."""


class OpenAIResponsesClient:
    """Thin adapter around the official OpenAI Python SDK."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        try:
            from openai import OpenAI, OpenAIError
        except ImportError as exc:  # pragma: no cover - depends on installation state
            raise ResponseGenerationError(
                "The OpenAI SDK is not installed. Run `python -m pip install -e .`."
            ) from exc

        options: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if base_url:
            options["base_url"] = base_url
        self._client = OpenAI(**options)
        self._openai_error = OpenAIError

    def generate(self, prompt: str, *, model: str, store: bool = False) -> GeneratedResponse:
        try:
            response = self._client.responses.create(
                model=model,
                input=prompt,
                store=store,
            )
        except self._openai_error as exc:
            raise ResponseGenerationError(f"OpenAI request failed: {exc}") from exc

        text = response.output_text.strip()
        if not text:
            raise ResponseGenerationError("OpenAI returned a response without text output.")

        return GeneratedResponse(
            response_id=response.id,
            model=getattr(response, "model", model),
            text=text,
        )

