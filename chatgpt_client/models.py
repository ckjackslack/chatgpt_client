from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedResponse:
    """Text returned by OpenAI before it is persisted."""

    response_id: str
    request_id: str | None
    model: str
    text: str


@dataclass(frozen=True, slots=True)
class NewPrompt:
    """A prompt/response pair ready to be persisted."""

    response_id: str
    request_id: str | None
    prompt: str
    model: str
    response: str

    @classmethod
    def from_generated(cls, prompt: str, generated: GeneratedResponse) -> NewPrompt:
        return cls(
            response_id=generated.response_id,
            request_id=generated.request_id,
            prompt=prompt,
            model=generated.model,
            response=generated.text,
        )


@dataclass(frozen=True, slots=True)
class StoredPrompt:
    """A prompt/response pair loaded from SQLite."""

    id: int
    created_at: str
    response_id: str
    request_id: str | None
    prompt: str
    model: str
    response: str
