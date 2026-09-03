from __future__ import annotations

from collections.abc import Callable

from chatgpt_client.api import OpenAIClientConfig, OpenAIResponsesClient, TextGenerator
from chatgpt_client.config import Settings
from chatgpt_client.models import NewPrompt, StoredPrompt
from chatgpt_client.repository import PromptRepository

GeneratorFactory = Callable[[OpenAIClientConfig], TextGenerator]


class ChatGPTApplication:
    """Application use cases, independent from argument parsing and presentation."""

    def __init__(
        self,
        repository: PromptRepository,
        generator_factory: GeneratorFactory | None = None,
    ) -> None:
        self.repository = repository
        self.generator_factory = generator_factory or OpenAIResponsesClient

    def initialize(self) -> None:
        self.repository.initialize()

    def ask(self, prompt: str, settings: Settings) -> StoredPrompt:
        client_config = OpenAIClientConfig(
            api_key=settings.require_api_key(),
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            organization=settings.organization,
            project=settings.project,
        )
        generated = self.generator_factory(client_config).generate(
            prompt,
            model=settings.model,
            store=settings.store_responses,
        )
        return self.repository.add(NewPrompt.from_generated(prompt, generated))

    def get(self, prompt_id: int) -> StoredPrompt | None:
        return self.repository.get(prompt_id)

    def history(self) -> list[StoredPrompt]:
        return self.repository.list_all()

    def search(self, query: str) -> list[StoredPrompt]:
        return self.repository.search(query)

    def clear(self) -> int:
        return self.repository.clear()
