from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chatgpt_client.database import (
    JournalMode,
    Migration,
    MigrationPlan,
    SQLiteConfig,
    SQLiteDatabase,
    TransactionMode,
)
from chatgpt_client.errors import DatabaseError


@pytest.fixture
def database(tmp_path: Path) -> SQLiteDatabase:
    result = SQLiteDatabase(SQLiteConfig(tmp_path / "database.db", timeout_seconds=0.25))
    result.prepare()
    return result


def test_prepare_creates_parent_and_configures_sqlite(tmp_path: Path) -> None:
    database = SQLiteDatabase(
        SQLiteConfig(
            tmp_path / "nested" / "database.db",
            timeout_seconds=0.125,
            journal_mode=JournalMode.WAL,
        )
    )

    database.prepare()

    with database.connection() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert journal_mode == "wal"
    assert busy_timeout == 125
    assert foreign_keys == 1


def test_connection_configurator_runs_for_every_connection(tmp_path: Path) -> None:
    configured: list[sqlite3.Connection] = []

    def configure(connection: sqlite3.Connection) -> None:
        configured.append(connection)
        connection.create_function("REVERSE", 1, lambda value: str(value)[::-1])

    database = SQLiteDatabase(
        SQLiteConfig(tmp_path / "database.db"),
        configure_connection=configure,
    )
    database.prepare()

    with database.connection() as connection:
        reversed_value = connection.execute("SELECT REVERSE('abc')").fetchone()[0]

    assert reversed_value == "cba"
    assert len(configured) == 2


def test_connection_is_closed_when_configuration_fails(tmp_path: Path) -> None:
    configured: list[sqlite3.Connection] = []

    def fail(connection: sqlite3.Connection) -> None:
        configured.append(connection)
        raise sqlite3.OperationalError("configuration failed")

    database = SQLiteDatabase(
        SQLiteConfig(tmp_path / "database.db"),
        configure_connection=fail,
    )
    with pytest.raises(DatabaseError, match="configuration failed"), database.connection():
        pass

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        configured[0].execute("SELECT 1")


def test_connection_is_closed_after_context(database: SQLiteDatabase) -> None:
    with database.connection() as connection:
        connection.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_transaction_commits_successful_unit_of_work(database: SQLiteDatabase) -> None:
    with database.transaction() as connection:
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")
        connection.execute("INSERT INTO example VALUES ('committed')")

    with database.connection() as connection:
        assert connection.execute("SELECT value FROM example").fetchone()[0] == "committed"


def test_transaction_rolls_back_failed_unit_of_work(database: SQLiteDatabase) -> None:
    with database.transaction() as connection:
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")

    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction(TransactionMode.IMMEDIATE) as connection:
            connection.execute("INSERT INTO example VALUES ('rolled back')")
            raise RuntimeError("abort")

    with database.connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM example").fetchone()[0]
    assert count == 0


def test_sqlite_errors_include_database_context(tmp_path: Path) -> None:
    invalid_path = tmp_path / "directory.db"
    invalid_path.mkdir()

    with pytest.raises(DatabaseError, match=r"SQLite operation failed.*directory\.db"):
        SQLiteDatabase(SQLiteConfig(invalid_path)).prepare()


def test_corrupted_database_is_reported_with_context(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.db"
    path.write_bytes(b"this is not a SQLite database")

    with pytest.raises(DatabaseError, match=r"SQLite operation failed.*corrupted\.db"):
        SQLiteDatabase(SQLiteConfig(path)).prepare()


def test_locked_database_obeys_configured_timeout(tmp_path: Path) -> None:
    database = SQLiteDatabase(
        SQLiteConfig(tmp_path / "database.db", timeout_seconds=0.01)
    )
    database.prepare()

    with database.transaction() as connection:
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")

    with database.transaction(TransactionMode.IMMEDIATE):
        with (
            pytest.raises(DatabaseError, match="database is locked"),
            database.transaction(TransactionMode.IMMEDIATE),
        ):
            pass


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_config_rejects_invalid_timeout(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(ValueError, match="finite number greater than zero"):
        SQLiteConfig(tmp_path / "database.db", timeout_seconds=timeout)


def test_migration_plan_applies_each_migration_once(database: SQLiteDatabase) -> None:
    applied: list[int] = []

    def migration(version: int, statement: str) -> Migration:
        def apply(connection: sqlite3.Connection) -> None:
            applied.append(version)
            connection.execute(statement)

        return Migration(version, apply)

    plan = MigrationPlan(
        (
            migration(1, "CREATE TABLE example (value TEXT)"),
            migration(2, "ALTER TABLE example ADD COLUMN extra TEXT"),
        )
    )

    with database.transaction(TransactionMode.IMMEDIATE) as connection:
        plan.apply(connection)
    with database.transaction(TransactionMode.IMMEDIATE) as connection:
        plan.apply(connection)
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert applied == [1, 2]
    assert version == plan.target_version == 2


@pytest.mark.parametrize(
    "versions",
    [
        (2,),
        (1, 1),
        (1, 3),
        (2, 1),
    ],
)
def test_migration_plan_rejects_invalid_version_sequences(versions: tuple[int, ...]) -> None:
    migrations = tuple(Migration(version, lambda connection: None) for version in versions)
    with pytest.raises(ValueError, match="unique, ordered, and contiguous"):
        MigrationPlan(migrations)


def test_migration_plan_rejects_newer_database(database: SQLiteDatabase) -> None:
    plan = MigrationPlan((Migration(1, lambda connection: None),))
    with database.transaction() as connection:
        connection.execute("PRAGMA user_version = 2")

    with (
        database.transaction() as connection,
        pytest.raises(DatabaseError, match="newer than supported"),
    ):
        plan.apply(connection)
