from __future__ import annotations

import io
import itertools
from collections.abc import Mapping
from pathlib import Path

import pytest

from chatgpt_client.application import GeneratorFactory
from chatgpt_client.cli import run
from chatgpt_client.config import Settings
from chatgpt_client.models import NewPrompt, StoredPrompt
from chatgpt_client.repository import PromptRepository
from tests.helpers import (
    CLIResult,
    CLIRunner,
    FakeGenerator,
    FakeGeneratorFactory,
    PromptFactory,
    SQLDatabaseFactory,
    SettingsFactory,
    sqlite_connection,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "history.db"


@pytest.fixture
def sql_database_factory(tmp_path: Path) -> SQLDatabaseFactory:
    fixtures = Path(__file__).parent / "fixtures"

    def create(fixture_name: str) -> Path:
        database = tmp_path / f"{Path(fixture_name).stem}.db"
        with sqlite_connection(database) as connection:
            connection.executescript(
                (fixtures / fixture_name).read_text(encoding="utf-8")
            )
        return database

    return create


@pytest.fixture
def repository(database_path: Path) -> PromptRepository:
    result = PromptRepository(database_path)
    result.initialize()
    return result


@pytest.fixture
def fake_generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def fake_generator_factory(fake_generator: FakeGenerator) -> FakeGeneratorFactory:
    return FakeGeneratorFactory(fake_generator)


@pytest.fixture
def settings_factory(database_path: Path) -> SettingsFactory:
    def create(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "api_key": "test-key",
            "model": "test-model",
            "database_path": database_path,
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    return create


@pytest.fixture
def prompt_factory(repository: PromptRepository) -> PromptFactory:
    sequence = itertools.count(1)

    def create(
        *,
        prompt: str = "question",
        response: str = "answer",
        response_id: str | None = None,
        request_id: str | None = "req_test",
        model: str = "test-model",
    ) -> StoredPrompt:
        number = next(sequence)
        return repository.add(
            NewPrompt(
                response_id=response_id or f"resp_{number}",
                request_id=request_id,
                prompt=prompt,
                model=model,
                response=response,
            )
        )

    return create


@pytest.fixture
def cli_runner(
    database_path: Path,
    fake_generator_factory: FakeGeneratorFactory,
) -> CLIRunner:
    def invoke(
        *arguments: str,
        environ: Mapping[str, str] | None = None,
        generator_factory: GeneratorFactory | None = None,
    ) -> CLIResult:
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = run(
            ["--database", str(database_path), *arguments],
            stdout=stdout,
            stderr=stderr,
            environ={} if environ is None else environ,
            generator_factory=generator_factory or fake_generator_factory,
        )
        return CLIResult(exit_code, stdout.getvalue(), stderr.getvalue())

    return invoke
