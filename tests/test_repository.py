from __future__ import annotations

from pathlib import Path

import pytest

from chatgpt_client.errors import RepositoryError
from chatgpt_client.models import NewPrompt
from chatgpt_client.repository import SCHEMA_VERSION, PromptRepository
from tests.helpers import PromptFactory, SQLDatabaseFactory, sqlite_connection


def test_add_get_list_and_clear(
    repository: PromptRepository,
    prompt_factory: PromptFactory,
) -> None:
    first = prompt_factory(prompt="first", request_id="req_1")
    second = prompt_factory(prompt="second", request_id=None)

    assert repository.get(first.id) == first
    assert repository.get(999_999) is None
    assert repository.list_all() == [second, first]
    assert repository.list_all(limit=1) == [second]
    assert repository.clear() == 2
    assert repository.list_all() == []


@pytest.mark.parametrize("limit", [0, -1])
def test_list_rejects_invalid_limit(repository: PromptRepository, limit: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        repository.list_all(limit=limit)


@pytest.mark.parametrize(
    ("query", "matching_prompt"),
    [
        ("FISH", "Where is the fish?"),
        ("%", "100% complete"),
        ("_", "snake_case"),
        (r"C:\\", r"C:\\temp"),
        ("ŻÓŁĆ", "Zażółć gęślą jaźń"),
    ],
)
def test_search_is_case_insensitive_and_treats_wildcards_as_literals(
    repository: PromptRepository,
    prompt_factory: PromptFactory,
    query: str,
    matching_prompt: str,
) -> None:
    expected = prompt_factory(prompt=matching_prompt)
    prompt_factory(prompt="unrelated")
    assert repository.search(query) == [expected]


def test_search_matches_response(
    repository: PromptRepository,
    prompt_factory: PromptFactory,
) -> None:
    expected = prompt_factory(prompt="question", response="needle in response")
    assert repository.search("needle") == [expected]


@pytest.mark.parametrize("query", ["", "   "])
def test_search_rejects_empty_query(repository: PromptRepository, query: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        repository.search(query)


def test_initialize_creates_parent_directory(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "history.db"
    repository = PromptRepository(database)
    repository.initialize()
    assert database.is_file()


@pytest.mark.parametrize(
    ("fixture_name", "expected_prompt", "expected_response_id"),
    [
        ("legacy_prompts.sql", "old question", ""),
        ("schema_v1.sql", "version one question", "resp_v1"),
    ],
)
def test_historical_schemas_are_migrated_without_data_loss(
    sql_database_factory: SQLDatabaseFactory,
    fixture_name: str,
    expected_prompt: str,
    expected_response_id: str,
) -> None:
    database = sql_database_factory(fixture_name)
    repository = PromptRepository(database)
    repository.initialize()

    stored = repository.list_all()[0]
    assert stored.prompt == expected_prompt
    assert stored.response_id == expected_response_id
    assert stored.request_id is None
    with sqlite_connection(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(prompts)")}
    assert version == SCHEMA_VERSION
    assert {"key", "request_id"} <= columns


def test_initialize_is_idempotent(
    repository: PromptRepository,
    prompt_factory: PromptFactory,
) -> None:
    stored = prompt_factory()
    repository.initialize()
    assert repository.list_all() == [stored]


def test_newer_schema_version_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "future.db"
    with sqlite_connection(database) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RepositoryError, match="newer than supported"):
        PromptRepository(database).initialize()


def test_malformed_legacy_schema_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "malformed.db"
    with sqlite_connection(database) as connection:
        connection.execute("CREATE TABLE prompts (id INTEGER PRIMARY KEY)")

    with pytest.raises(RepositoryError, match="missing required columns"):
        PromptRepository(database).initialize()


def test_sqlite_errors_are_wrapped_with_database_context(tmp_path: Path) -> None:
    database_directory = tmp_path / "directory.db"
    database_directory.mkdir()
    with pytest.raises(RepositoryError, match="SQLite operation failed"):
        PromptRepository(database_directory).initialize()


def test_request_id_round_trip(repository: PromptRepository) -> None:
    stored = repository.add(
        NewPrompt(
            response_id="resp_123",
            request_id="req_123",
            prompt="question",
            model="model",
            response="answer",
        )
    )
    assert stored.request_id == "req_123"


def test_wal_mode_is_enabled(repository: PromptRepository) -> None:
    with sqlite_connection(repository.database_path) as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
