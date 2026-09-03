from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from chatgpt_client.models import NewPrompt, StoredPrompt


SCHEMA_VERSION = 1


class PromptRepository:
    """Persistence boundary for prompt history."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(prompts)").fetchall()
            }
            if "key" not in columns:
                connection.execute(
                    "ALTER TABLE prompts ADD COLUMN key TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_prompts_created_at ON prompts(created_at DESC)"
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def add(self, prompt: NewPrompt) -> StoredPrompt:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO prompts (key, prompt, model, response)
                VALUES (?, ?, ?, ?)
                """,
                (prompt.response_id, prompt.prompt, prompt.model, prompt.response),
            )
            row = connection.execute(
                "SELECT * FROM prompts WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:  # pragma: no cover - defensive guard around SQLite
            raise sqlite3.DatabaseError("Inserted prompt could not be read back.")
        return _to_prompt(row)

    def get(self, prompt_id: int) -> StoredPrompt | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
            ).fetchone()
        return _to_prompt(row) if row is not None else None

    def list(self, *, limit: int | None = None) -> list[StoredPrompt]:
        query = "SELECT * FROM prompts ORDER BY created_at DESC, id DESC"
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
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM prompts
                WHERE prompt COLLATE NOCASE LIKE ? ESCAPE '\\'
                   OR response COLLATE NOCASE LIKE ? ESCAPE '\\'
                ORDER BY created_at DESC, id DESC
                """,
                (pattern, pattern),
            ).fetchall()
        return [_to_prompt(row) for row in rows]

    def clear(self) -> int:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
            connection.execute("DELETE FROM prompts")
        return int(count)


def _to_prompt(row: sqlite3.Row) -> StoredPrompt:
    return StoredPrompt(
        id=row["id"],
        created_at=row["created_at"],
        response_id=row["key"] or "",
        prompt=row["prompt"],
        model=row["model"],
        response=row["response"],
    )
