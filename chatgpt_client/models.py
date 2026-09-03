from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedResponse:
    """Text returned by OpenAI before it is persisted."""

    response_id: str
    model: str
    text: str


@dataclass(frozen=True, slots=True)
class NewPrompt:
    """A prompt/response pair ready to be persisted."""

    response_id: str
    prompt: str
    model: str
    response: str


@dataclass(frozen=True, slots=True)
class StoredPrompt:
    """A prompt/response pair loaded from SQLite."""

    id: int
    created_at: str
    response_id: str
    prompt: str
    model: str
    response: str

