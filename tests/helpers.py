from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from chatgpt_client.application import GeneratorFactory
from chatgpt_client.api import OpenAIClientConfig
from chatgpt_client.config import Settings
from chatgpt_client.models import GeneratedResponse, StoredPrompt


@dataclass(frozen=True, slots=True)
class GenerationCall:
    prompt: str
    model: str
    store: bool


@dataclass(slots=True)
class FakeGenerator:
    response: GeneratedResponse = field(
        default_factory=lambda: GeneratedResponse(
            response_id="resp_test",
            request_id="req_test",
            model="test-model",
            text="A generated answer",
        )
    )
    error: Exception | None = None
    calls: list[GenerationCall] = field(default_factory=list)

    def generate(self, prompt: str, *, model: str, store: bool = False) -> GeneratedResponse:
        self.calls.append(GenerationCall(prompt, model, store))
        if self.error:
            raise self.error
        return self.response


@dataclass(slots=True)
class FakeGeneratorFactory:
    generator: FakeGenerator
    configs: list[OpenAIClientConfig] = field(default_factory=list)

    def __call__(self, config: OpenAIClientConfig) -> FakeGenerator:
        self.configs.append(config)
        return self.generator


@dataclass(frozen=True, slots=True)
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str


class CLIRunner(Protocol):
    def __call__(
        self,
        *arguments: str,
        environ: Mapping[str, str] | None = None,
        generator_factory: GeneratorFactory | None = None,
    ) -> CLIResult: ...


class PromptFactory(Protocol):
    def __call__(
        self,
        *,
        prompt: str = "question",
        response: str = "answer",
        response_id: str | None = None,
        request_id: str | None = "req_test",
        model: str = "test-model",
    ) -> StoredPrompt: ...


class SettingsFactory(Protocol):
    def __call__(self, **overrides: object) -> Settings: ...
