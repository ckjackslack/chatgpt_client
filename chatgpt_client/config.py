from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from chatgpt_client.database import (
    DEFAULT_TIMEOUT_SECONDS as DEFAULT_DATABASE_TIMEOUT_SECONDS,
)
from chatgpt_client.errors import ConfigurationError

DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_DATABASE = Path("prompts.db")
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_RETRIES = 2
_ENVIRONMENT_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str | None = field(repr=False)
    model: str
    database_path: Path
    database_timeout_seconds: float = DEFAULT_DATABASE_TIMEOUT_SECONDS
    store_responses: bool = False
    base_url: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    organization: str | None = None
    project: str | None = None

    def require_api_key(self) -> str:
        if not self.api_key or not self.api_key.strip():
            raise ConfigurationError(
                "Missing OPENAI_API_KEY. Set it in the environment or .env file."
            )
        return self.api_key.strip()


def read_env_file(path: Path) -> dict[str, str]:
    """Read a small, dependency-free subset of dotenv syntax."""
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ConfigurationError(f"Cannot read environment file {path}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise ConfigurationError(f"Invalid environment entry at {path}:{line_number}.")

        key, value = (part.strip() for part in line.split("=", 1))
        if not _ENVIRONMENT_KEY.fullmatch(key):
            raise ConfigurationError(
                f"Invalid environment key at {path}:{line_number}: {key!r}."
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def load_settings(
    *,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str],
    database_override: Path | None = None,
    model_override: str | None = None,
) -> Settings:
    """Build settings without mutating process-global environment state."""
    values = read_env_file(env_file)
    values.update(environ)

    model = _first_non_empty(model_override, values.get("OPENAI_MODEL"), values.get("MODEL"))
    model = model or DEFAULT_MODEL
    database_value = values.get("CHATGPT_CLIENT_DB", str(DEFAULT_DATABASE)).strip()
    if database_override is None and not database_value:
        raise ConfigurationError("CHATGPT_CLIENT_DB must not be empty.")
    database_path = database_override or Path(database_value).expanduser()

    return Settings(
        api_key=_optional(values.get("OPENAI_API_KEY")),
        model=model,
        database_path=database_path,
        database_timeout_seconds=_parse_positive_float(
            "CHATGPT_CLIENT_DB_TIMEOUT_SECONDS",
            values.get(
                "CHATGPT_CLIENT_DB_TIMEOUT_SECONDS",
                str(DEFAULT_DATABASE_TIMEOUT_SECONDS),
            ),
        ),
        store_responses=_parse_bool(values.get("OPENAI_STORE_RESPONSES", "false")),
        base_url=_optional(values.get("OPENAI_BASE_URL")),
        timeout_seconds=_parse_positive_float(
            "OPENAI_TIMEOUT_SECONDS",
            values.get("OPENAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)),
        ),
        max_retries=_parse_non_negative_int(
            "OPENAI_MAX_RETRIES",
            values.get("OPENAI_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)),
        ),
        organization=_optional(values.get("OPENAI_ORGANIZATION")),
        project=_optional(values.get("OPENAI_PROJECT")),
    )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        "OPENAI_STORE_RESPONSES must be one of: true, false, 1, 0, yes, no, on, off."
    )


def _parse_positive_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ConfigurationError(f"{name} must be a finite number greater than zero.")
    return parsed


def _parse_non_negative_int(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if parsed < 0:
        raise ConfigurationError(f"{name} must be zero or greater.")
    return parsed


def _first_non_empty(*values: str | None) -> str | None:
    return next((value.strip() for value in values if value and value.strip()), None)


def _optional(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None
