from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from chatgpt_client.errors import RepositoryError
from chatgpt_client.models import NewPrompt, StoredPrompt


SCHEMA_VERSION = 2
SQLITE_TIMEOUT_SECONDS = 5.0
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

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=SQLITE_TIMEOUT_SECONDS,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                yield connection
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise RepositoryError(
                f"SQLite operation failed for {self.database_path}: {exc}"
            ) from exc

    def initialize(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RepositoryError(
                f"Cannot create database directory {self.database_path.parent}: {exc}"
            ) from exc

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                version = _schema_version(connection)
                if version > SCHEMA_VERSION:
                    raise RepositoryError(
                        f"Database schema version {version} is newer than supported "
                        f"version {SCHEMA_VERSION}."
                    )
                for target_version in range(version + 1, SCHEMA_VERSION + 1):
                    _MIGRATIONS[target_version](connection)
                    connection.execute(f"PRAGMA user_version = {target_version}")
                _validate_schema(connection)

    def add(self, prompt: NewPrompt) -> StoredPrompt:
        with self._connect() as connection, connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_to_prompt(row) for row in rows]

    def search(self, query: str) -> list[StoredPrompt]:
        if not query.strip():
            raise ValueError("query must not be empty")
        pattern = f"%{_escape_like(query)}%"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                {_SELECT_PROMPTS}
                WHERE prompt COLLATE NOCASE LIKE ? ESCAPE '\\'
                   OR response COLLATE NOCASE LIKE ? ESCAPE '\\'
                ORDER BY created_at DESC, id DESC
                """,
                (pattern, pattern),
            ).fetchall()
        return [_to_prompt(row) for row in rows]

    def clear(self) -> int:
        with self._connect() as connection, connection:
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


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _column_names(connection: sqlite3.Connection) -> set[str]:
    return {
        cast(str, row["name"])
        for row in connection.execute("PRAGMA table_info(prompts)")
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migrate_to_v1,
    2: _migrate_to_v2,
}
