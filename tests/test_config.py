from __future__ import annotations

from pathlib import Path

import pytest

from chatgpt_client.config import (
    DEFAULT_DATABASE_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ConfigurationError,
    load_settings,
    read_env_file,
)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
def test_true_boolean_values(value: str) -> None:
    assert load_settings(environ={"OPENAI_STORE_RESPONSES": value}).store_responses is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " Off "])
def test_false_boolean_values(value: str) -> None:
    assert load_settings(environ={"OPENAI_STORE_RESPONSES": value}).store_responses is False


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("OPENAI_STORE_RESPONSES", "perhaps", "must be one of"),
        ("OPENAI_TIMEOUT_SECONDS", "never", "must be a number"),
        ("OPENAI_TIMEOUT_SECONDS", "0", "greater than zero"),
        ("OPENAI_TIMEOUT_SECONDS", "-1", "greater than zero"),
        ("OPENAI_TIMEOUT_SECONDS", "nan", "finite number"),
        ("OPENAI_TIMEOUT_SECONDS", "inf", "finite number"),
        ("CHATGPT_CLIENT_DB_TIMEOUT_SECONDS", "0", "greater than zero"),
        ("OPENAI_MAX_RETRIES", "1.5", "must be an integer"),
        ("OPENAI_MAX_RETRIES", "-1", "zero or greater"),
    ],
)
def test_invalid_typed_settings_are_rejected(name: str, value: str, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load_settings(environ={name: value})


def test_process_environment_overrides_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=file-key\nOPENAI_MODEL='file-model'\n",
        encoding="utf-8",
    )

    settings = load_settings(
        env_file=env_file,
        environ={"OPENAI_API_KEY": "process-key", "OPENAI_MODEL": "process-model"},
    )

    assert settings.api_key == "process-key"
    assert settings.model == "process-model"


def test_model_override_precedes_environment() -> None:
    settings = load_settings(
        environ={"OPENAI_MODEL": "environment-model"},
        model_override=" cli-model ",
    )
    assert settings.model == "cli-model"


def test_legacy_model_alias_and_defaults() -> None:
    assert load_settings(environ={"MODEL": "legacy"}).model == "legacy"
    defaults = load_settings(environ={})
    assert defaults.model == DEFAULT_MODEL
    assert defaults.database_timeout_seconds == DEFAULT_DATABASE_TIMEOUT_SECONDS
    assert defaults.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert defaults.max_retries == DEFAULT_MAX_RETRIES


def test_client_options_are_parsed_and_trimmed() -> None:
    settings = load_settings(
        environ={
            "OPENAI_TIMEOUT_SECONDS": "45.5",
            "OPENAI_MAX_RETRIES": "4",
            "OPENAI_BASE_URL": " https://example.test/v1 ",
            "OPENAI_ORGANIZATION": " org_test ",
            "OPENAI_PROJECT": " project_test ",
            "CHATGPT_CLIENT_DB_TIMEOUT_SECONDS": "0.25",
        }
    )
    assert settings.timeout_seconds == 45.5
    assert settings.max_retries == 4
    assert settings.base_url == "https://example.test/v1"
    assert settings.organization == "org_test"
    assert settings.project == "project_test"
    assert settings.database_timeout_seconds == 0.25


def test_read_env_file_supports_bom_export_quotes_and_embedded_equals(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\ufeff# comment\nexport TOKEN=one=two\nQUOTED='some value'\n",
        encoding="utf-8",
    )
    assert read_env_file(env_file) == {"TOKEN": "one=two", "QUOTED": "some value"}


@pytest.mark.parametrize("line", ["NO_EQUALS", "=empty", "NOT-A-KEY=value"])
def test_invalid_env_entries_report_line_number(tmp_path: Path, line: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"VALID=1\n{line}\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"\.env:2"):
        read_env_file(env_file)


def test_empty_database_path_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="must not be empty"):
        load_settings(environ={"CHATGPT_CLIENT_DB": "  "})


def test_require_api_key() -> None:
    settings = load_settings(environ={})
    with pytest.raises(ConfigurationError, match="Missing OPENAI_API_KEY"):
        settings.require_api_key()


def test_settings_repr_does_not_expose_api_key() -> None:
    settings = load_settings(environ={"OPENAI_API_KEY": "top-secret"})
    assert "top-secret" not in repr(settings)
