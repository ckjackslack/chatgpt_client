from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_DATABASE = Path("prompts.db")


class ConfigurationError(ValueError):
    """Raised when application configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str | None
    model: str
    database_path: Path
    store_responses: bool = False
    base_url: str | None = None

    def require_api_key(self) -> str:
        if not self.api_key:
            raise ConfigurationError(
                "Missing OPENAI_API_KEY. Set it in the environment or .env file."
            )
        return self.api_key


def read_env_file(path: Path) -> dict[str, str]:
    """Read a small, dependency-free subset of dotenv syntax."""
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise ConfigurationError(f"Invalid environment entry at {path}:{line_number}.")

        key, value = (part.strip() for part in line.split("=", 1))
        if not key:
            raise ConfigurationError(f"Empty environment key at {path}:{line_number}.")
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

    model = model_override or values.get("OPENAI_MODEL") or values.get("MODEL") or DEFAULT_MODEL
    database_path = database_override or Path(
        values.get("CHATGPT_CLIENT_DB", str(DEFAULT_DATABASE))
    ).expanduser()

    return Settings(
        api_key=values.get("OPENAI_API_KEY") or None,
        model=model,
        database_path=database_path,
        store_responses=_parse_bool(values.get("OPENAI_STORE_RESPONSES", "false")),
        base_url=values.get("OPENAI_BASE_URL") or None,
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

