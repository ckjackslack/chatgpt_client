from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from math import ceil, isfinite
from pathlib import Path

from chatgpt_client.errors import DatabaseError

DEFAULT_TIMEOUT_SECONDS = 5.0
ConnectionConfigurator = Callable[[sqlite3.Connection], None]
MigrationOperation = Callable[[sqlite3.Connection], None]


class JournalMode(StrEnum):
    DELETE = "DELETE"
    WAL = "WAL"


class TransactionMode(StrEnum):
    DEFERRED = "DEFERRED"
    IMMEDIATE = "IMMEDIATE"
    EXCLUSIVE = "EXCLUSIVE"


@dataclass(frozen=True, slots=True)
class SQLiteConfig:
    path: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    journal_mode: JournalMode = JournalMode.WAL

    def __post_init__(self) -> None:
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be a finite number greater than zero"
            )

    @property
    def busy_timeout_ms(self) -> int:
        return max(1, ceil(self.timeout_seconds * 1_000))


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    apply: MigrationOperation


class MigrationPlan:
    """Validated, contiguous sequence of forward-only SQLite migrations."""

    def __init__(self, migrations: Sequence[Migration]) -> None:
        self._migrations = tuple(migrations)
        versions = tuple(migration.version for migration in self._migrations)
        expected = tuple(range(1, len(self._migrations) + 1))
        if versions != expected:
            raise ValueError(
                "migration versions must be unique, ordered, and contiguous from 1"
            )

    @property
    def target_version(self) -> int:
        return len(self._migrations)

    def apply(self, connection: sqlite3.Connection) -> None:
        current_version = _schema_version(connection)
        if current_version > self.target_version:
            raise DatabaseError(
                f"Database schema version {current_version} is newer than supported "
                f"version {self.target_version}."
            )
        for migration in self._migrations[current_version:]:
            migration.apply(connection)
            connection.execute(f"PRAGMA user_version = {migration.version}")


class SQLiteDatabase:
    """SQLite connection factory and transaction boundary."""

    def __init__(
        self,
        config: SQLiteConfig,
        *,
        configure_connection: ConnectionConfigurator | None = None,
    ) -> None:
        self.config = config
        self._configure_connection = configure_connection

    @property
    def path(self) -> Path:
        return self.config.path

    def prepare(self) -> None:
        """Create storage and establish persistent database-level settings."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseError(
                f"Cannot create database directory {self.path.parent}: {exc}"
            ) from exc

        with self.connection() as connection:
            connection.execute(f"PRAGMA journal_mode = {self.config.journal_mode.value}")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield one configured connection and always close it."""
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=self.config.timeout_seconds,
            )
            try:
                connection.row_factory = sqlite3.Row
                connection.execute(
                    f"PRAGMA busy_timeout = {self.config.busy_timeout_ms}"
                )
                connection.execute("PRAGMA foreign_keys = ON")
                if self._configure_connection is not None:
                    self._configure_connection(connection)
                yield connection
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise DatabaseError(f"SQLite operation failed for {self.path}: {exc}") from exc

    @contextmanager
    def transaction(
        self,
        mode: TransactionMode = TransactionMode.DEFERRED,
    ) -> Iterator[sqlite3.Connection]:
        """Run one atomic unit of work with explicit commit or rollback."""
        with self.connection() as connection:
            connection.execute(f"BEGIN {mode.value}")
            try:
                yield connection
            except BaseException as exc:
                try:
                    connection.rollback()
                except sqlite3.Error as rollback_error:
                    exc.add_note(f"SQLite rollback also failed: {rollback_error}")
                raise
            else:
                connection.commit()

    @staticmethod
    def validate_integrity(connection: sqlite3.Connection) -> None:
        results = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
        if results != ["ok"]:
            details = "; ".join(results) if results else "no result"
            raise DatabaseError(f"Database integrity check failed: {details}.")


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])
