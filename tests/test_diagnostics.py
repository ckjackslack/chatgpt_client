from __future__ import annotations

from chatgpt_client.diagnostics import (
    configuration_diagnostics,
    render_diagnostics,
    response_diagnostics,
)
from tests.helpers import PromptFactory, SettingsFactory


def test_configuration_diagnostics_are_useful_and_secret_free(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(
        api_key="top-secret",
        base_url="https://user:base-url-secret@example.test/v1?token=hidden",
        organization="org-secret",
        project="project-secret",
    )

    rendered = render_diagnostics(configuration_diagnostics(settings))

    assert "api_key=configured" in rendered
    assert "base_url=<custom>" in rendered
    assert "organization=configured" in rendered
    assert "project=configured" in rendered
    assert "top-secret" not in rendered
    assert "base-url-secret" not in rendered
    assert "token=hidden" not in rendered
    assert "org-secret" not in rendered
    assert "project-secret" not in rendered


def test_response_diagnostics_include_trace_identifiers(
    prompt_factory: PromptFactory,
) -> None:
    prompt = prompt_factory(response_id="resp_123", request_id="req_123")
    rendered = render_diagnostics(response_diagnostics(prompt))
    assert f"history_id={prompt.id}" in rendered
    assert "response_id=resp_123" in rendered
    assert "request_id=req_123" in rendered
