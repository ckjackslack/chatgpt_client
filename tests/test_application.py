from __future__ import annotations

import pytest

from chatgpt_client.api import OpenAIClientConfig
from chatgpt_client.application import ChatGPTApplication
from chatgpt_client.errors import ConfigurationError
from chatgpt_client.repository import PromptRepository
from tests.helpers import FakeGenerator, FakeGeneratorFactory, PromptFactory, SettingsFactory

@pytest.fixture
def application(
    repository: PromptRepository,
    fake_generator_factory: FakeGeneratorFactory,
) -> ChatGPTApplication:
    return ChatGPTApplication(repository, fake_generator_factory)


def test_ask_generates_and_persists_response(
    application: ChatGPTApplication,
    repository: PromptRepository,
    fake_generator: FakeGenerator,
    fake_generator_factory: FakeGeneratorFactory,
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(model="chosen-model", store_responses=True)

    stored = application.ask("Hello", settings)

    assert fake_generator.calls[0].prompt == "Hello"
    assert fake_generator.calls[0].model == "chosen-model"
    assert fake_generator.calls[0].store is True
    assert fake_generator_factory.configs[0].api_key == "test-key"
    assert fake_generator_factory.configs[0].max_retries == settings.max_retries
    assert repository.get(stored.id) == stored
    assert stored.request_id == "req_test"


def test_missing_api_key_fails_before_factory_is_called(
    application: ChatGPTApplication,
    fake_generator_factory: FakeGeneratorFactory,
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(api_key=None)
    with pytest.raises(ConfigurationError, match="Missing OPENAI_API_KEY"):
        application.ask("Hello", settings)
    assert fake_generator_factory.configs == []


def test_local_use_cases_do_not_create_generator(
    repository: PromptRepository,
    prompt_factory: PromptFactory,
) -> None:
    stored = prompt_factory(prompt="needle")

    def forbidden_factory(config: OpenAIClientConfig) -> FakeGenerator:
        raise AssertionError("local use case initialized API generator")

    application = ChatGPTApplication(repository, forbidden_factory)
    assert application.get(stored.id) == stored
    assert application.history() == [stored]
    assert application.search("needle") == [stored]
    assert application.clear() == 1
