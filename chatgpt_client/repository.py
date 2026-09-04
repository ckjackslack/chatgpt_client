from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from chatgpt_client.database import (
    DEFAULT_TIMEOUT_SECONDS,
    Migration,
    MigrationPlan,
    SQLiteConfig,
    SQLiteDatabase,
    TransactionMode,
)
from chatgpt_client.errors import RepositoryError
from chatgpt_client.models import NewPrompt, StoredPrompt

SQLITE_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS
_SELECT_PROMPTS = """
    SELECT
        id,
        COALESCE(created_at, '') AS created_at,
        COALESCE(key, '') AS response_id,
        request_id,
        COALESCE(prompt, '') AS prompt,
        COALESCE(model, '') AS model,
        COALESCE(response, '') AS response
    FROM prompts
"""


class PromptRepository:
    """SQLite persistence boundary for prompt history."""

    def __init__(
        self,
        database_path: Path,
        *,
        timeout_seconds: float = SQLITE_TIMEOUT_SECONDS,
    ) -> None:
        self._database = SQLiteDatabase(
            SQLiteConfig(database_path, timeout_seconds),
            configure_connection=_configure_connection,
        )

    @property
    def database_path(self) -> Path:
        return self._database.path

    def initialize(self) -> None:
        self._database.prepare()
        with self._database.transaction(TransactionMode.IMMEDIATE) as connection:
            _MIGRATIONS.apply(connection)
            _validate_schema(connection)
            self._database.validate_integrity(connection)

    def add(self, prompt: NewPrompt) -> StoredPrompt:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO prompts (key, request_id, prompt, model, response)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    prompt.response_id,
                    prompt.request_id,
                    prompt.prompt,
                    prompt.model,
                    prompt.response,
                ),
            )
            row = connection.execute(
                f"{_SELECT_PROMPTS} WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        if row is None:  # pragma: no cover - defensive guard around SQLite
            raise RepositoryError("Inserted prompt could not be read back.")
        return _to_prompt(row)

    def get(self, prompt_id: int) -> StoredPrompt | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"{_SELECT_PROMPTS} WHERE id = ?",
                (prompt_id,),
            ).fetchone()
        return _to_prompt(row) if row is not None else None

    def list_all(self, *, limit: int | None = None) -> list[StoredPrompt]:
        query = f"{_SELECT_PROMPTS} ORDER BY created_at DESC, id DESC"
        parameters: tuple[int, ...] = ()
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be a positive integer")
            query += " LIMIT ?"
            parameters = (limit,)
        with self._database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_to_prompt(row) for row in rows]

    def search(self, query: str) -> list[StoredPrompt]:
        if not query.strip():
            raise ValueError("query must not be empty")
        pattern = f"%{_escape_like(query.casefold())}%"
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                {_SELECT_PROMPTS}
                WHERE CASEFOLD(prompt) LIKE ? ESCAPE '\\'
                   OR CASEFOLD(response) LIKE ? ESCAPE '\\'
                ORDER BY created_at DESC, id DESC
                """,
                (pattern, pattern),
            ).fetchall()
        return [_to_prompt(row) for row in rows]

    def clear(self) -> int:
        with self._database.transaction() as connection:
            count = connection.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
            connection.execute("DELETE FROM prompts")
        return int(count)


def _migrate_to_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            key TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL,
            model TEXT NOT NULL,
            response TEXT NOT NULL
        )
        """
    )
    columns = _column_names(connection)
    legacy_columns = {"id", "created_at", "prompt", "model", "response"}
    missing = legacy_columns - columns
    if missing:
        raise RepositoryError(
            f"Existing prompts table is missing required columns: {', '.join(sorted(missing))}."
        )
    if "key" not in columns:
        connection.execute("ALTER TABLE prompts ADD COLUMN key TEXT NOT NULL DEFAULT ''")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompts_created_at ON prompts(created_at DESC)"
    )


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    if "request_id" not in _column_names(connection):
        connection.execute("ALTER TABLE prompts ADD COLUMN request_id TEXT")


def _validate_schema(connection: sqlite3.Connection) -> None:
    expected = {
        "id",
        "created_at",
        "key",
        "request_id",
        "prompt",
        "model",
        "response",
    }
    missing = expected - _column_names(connection)
    if missing:
        raise RepositoryError(
            f"Database schema is missing columns: {', '.join(sorted(missing))}."
        )


def _column_names(connection: sqlite3.Connection) -> set[str]:
    return {
        cast(str, row["name"])
        for row in connection.execute("PRAGMA table_info(prompts)")
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _casefold(value: str | None) -> str:
    return value.casefold() if value is not None else ""


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.create_function("CASEFOLD", 1, _casefold, deterministic=True)


def _to_prompt(row: sqlite3.Row) -> StoredPrompt:
    return StoredPrompt(
        id=cast(int, row["id"]),
        created_at=cast(str, row["created_at"]),
        response_id=cast(str, row["response_id"]),
        request_id=cast(str | None, row["request_id"]),
        prompt=cast(str, row["prompt"]),
        model=cast(str, row["model"]),
        response=cast(str, row["response"]),
    )


_MIGRATIONS = MigrationPlan(
    (
        Migration(1, _migrate_to_v1),
        Migration(2, _migrate_to_v2),
    )
)
SCHEMA_VERSION = _MIGRATIONS.target_version
