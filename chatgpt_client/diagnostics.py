from __future__ import annotations

from collections.abc import Iterable

from chatgpt_client.config import Settings
from chatgpt_client.models import StoredPrompt


def configuration_diagnostics(settings: Settings) -> tuple[str, ...]:
    """Return a stable, secret-free view of effective runtime settings."""
    return (
        f"database={settings.database_path.expanduser().absolute()}",
        f"database_timeout_seconds={settings.database_timeout_seconds:g}",
        f"model={settings.model}",
        f"api_key={'configured' if settings.api_key else 'missing'}",
        f"base_url={'<custom>' if settings.base_url else '<SDK default>'}",
        f"timeout_seconds={settings.timeout_seconds:g}",
        f"max_retries={settings.max_retries}",
        f"store_responses={str(settings.store_responses).lower()}",
        f"organization={'configured' if settings.organization else 'missing'}",
        f"project={'configured' if settings.project else 'missing'}",
    )


def response_diagnostics(prompt: StoredPrompt) -> tuple[str, ...]:
    """Return identifiers useful when tracing a completed request."""
    return (
        f"history_id={prompt.id}",
        f"response_id={prompt.response_id}",
        f"request_id={prompt.request_id or '<unavailable>'}",
        f"response_model={prompt.model}",
    )


def render_diagnostics(values: Iterable[str]) -> str:
    return "\n".join(f"[debug] {value}" for value in values)
