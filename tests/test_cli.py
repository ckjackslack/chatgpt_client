from __future__ import annotations

from pathlib import Path

import pytest

from chatgpt_client.api import OpenAIClientConfig
from chatgpt_client.cli import (
    AskCommand,
    ClearCommand,
    SearchCommand,
    ShowCommand,
    parse_command,
)
from chatgpt_client.errors import ResponseGenerationError
from chatgpt_client.repository import PromptRepository
from tests.helpers import CLIRunner, FakeGenerator, FakeGeneratorFactory, PromptFactory


@pytest.mark.parametrize(
    ("arguments", "command_type"),
    [
        ([], ShowCommand),
        (["show"], ShowCommand),
        (["show", "7"], ShowCommand),
        (["ask", "hello"], AskCommand),
        (["search", "needle"], SearchCommand),
        (["clear", "--yes"], ClearCommand),
        (["--action", "show"], ShowCommand),
        (["--action", "ask", "--query", "hello"], AskCommand),
        (["--action", "search", "--query", "needle"], SearchCommand),
        (["--action", "clear", "--yes"], ClearCommand),
    ],
)
def test_parse_command_supports_modern_and_legacy_syntax(
    arguments: list[str],
    command_type: type[object],
) -> None:
    assert isinstance(parse_command(arguments), command_type)


@pytest.mark.parametrize("action", ["ask", "search"])
def test_legacy_query_commands_require_query(action: str) -> None:
    with pytest.raises(SystemExit) as raised:
        parse_command(["--action", action])
    assert raised.value.code == 2


def test_local_show_does_not_initialize_api_client(cli_runner: CLIRunner) -> None:
    def forbidden_factory(config: OpenAIClientConfig) -> FakeGenerator:
        raise AssertionError("API client must not be initialized")

    result = cli_runner("show", generator_factory=forbidden_factory)
    assert result.exit_code == 0
    assert result.stdout.strip() == "Empty database."
    assert result.stderr == ""


def test_ask_generates_and_persists_response(
    cli_runner: CLIRunner,
    fake_generator: FakeGenerator,
    fake_generator_factory: FakeGeneratorFactory,
    database_path: Path,
) -> None:
    result = cli_runner(
        "ask",
        "Hello",
        "--model",
        "chosen-model",
        environ={"OPENAI_API_KEY": "secret", "OPENAI_STORE_RESPONSES": "true"},
    )

    assert result.exit_code == 0
    assert result.stdout == "A generated answer\n"
    assert result.stderr == ""
    assert fake_generator.calls[0].prompt == "Hello"
    assert fake_generator.calls[0].model == "chosen-model"
    assert fake_generator.calls[0].store is True
    assert fake_generator_factory.configs[0].api_key == "secret"
    repository = PromptRepository(database_path)
    repository.initialize()
    assert repository.list_all()[0].response == "A generated answer"


def test_ask_without_api_key_is_user_facing_error(cli_runner: CLIRunner) -> None:
    result = cli_runner("ask", "Hello")
    assert result.exit_code == 1
    assert "Missing OPENAI_API_KEY" in result.stderr
    assert result.stdout == ""


def test_api_diagnostics_are_printed(cli_runner: CLIRunner, fake_generator: FakeGenerator) -> None:
    fake_generator.error = ResponseGenerationError(
        "request failed",
        request_id="req_failed",
        status_code=429,
    )
    result = cli_runner("ask", "Hello", environ={"OPENAI_API_KEY": "secret"})
    assert result.exit_code == 1
    assert "status=429" in result.stderr
    assert "request_id=req_failed" in result.stderr


def test_search_uses_query_and_excludes_other_rows(
    cli_runner: CLIRunner,
    prompt_factory: PromptFactory,
) -> None:
    prompt_factory(prompt="needle", response="matching response")
    prompt_factory(prompt="other", response="different response")
    result = cli_runner("search", "needle")
    assert result.exit_code == 0
    assert "needle" in result.stdout
    assert "different response" not in result.stdout


def test_code_only_search_extracts_code(
    cli_runner: CLIRunner,
    prompt_factory: PromptFactory,
) -> None:
    prompt_factory(prompt="python", response="```python\nprint('hello')\n```")
    result = cli_runner("search", "python", "--code-only")
    assert result.exit_code == 0
    assert "print('hello')" in result.stdout
    assert "```" not in result.stdout


def test_code_only_search_reports_no_code(
    cli_runner: CLIRunner,
    prompt_factory: PromptFactory,
) -> None:
    prompt_factory(prompt="prose", response="ordinary prose")
    result = cli_runner("search", "prose", "--code-only")
    assert result.exit_code == 0
    assert "No code snippets" in result.stdout


def test_show_one_and_missing_prompt(
    cli_runner: CLIRunner,
    prompt_factory: PromptFactory,
) -> None:
    stored = prompt_factory(prompt="question", response="answer")
    found = cli_runner("show", str(stored.id))
    missing = cli_runner("show", "999999")
    assert found.stdout == "Q: question\nA: answer\n"
    assert missing.stdout == "No prompt with id=999999.\n"


def test_clear_requires_explicit_confirmation(
    cli_runner: CLIRunner,
    prompt_factory: PromptFactory,
    repository: PromptRepository,
) -> None:
    prompt_factory()
    refused = cli_runner("clear")
    assert refused.exit_code == 2
    assert "without --yes" in refused.stderr
    assert len(repository.list_all()) == 1

    confirmed = cli_runner("clear", "--yes")
    assert confirmed.exit_code == 0
    assert confirmed.stdout == "Deleted 1 prompt(s).\n"
    assert repository.list_all() == []


def test_legacy_action_syntax_remains_executable(cli_runner: CLIRunner) -> None:
    result = cli_runner("--action", "show")
    assert result.exit_code == 0
    assert result.stdout == "Empty database.\n"
