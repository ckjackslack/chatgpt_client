from __future__ import annotations

import os

import pytest

from chatgpt_client.api import OpenAIClientConfig, OpenAIResponsesClient
from chatgpt_client.config import DEFAULT_MODEL

pytestmark = pytest.mark.integration


def test_live_responses_api_round_trip() -> None:
    if os.environ.get("RUN_OPENAI_INTEGRATION_TESTS") != "1":
        pytest.skip("set RUN_OPENAI_INTEGRATION_TESTS=1 to enable live API tests")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.fail("OPENAI_API_KEY is required for live API tests")

    client = OpenAIResponsesClient(
        OpenAIClientConfig(
            api_key=api_key,
            timeout_seconds=60,
            max_retries=0,
        )
    )
    response = client.generate(
        "Reply with only the lowercase text: integration-ok",
        model=os.environ.get("OPENAI_TEST_MODEL") or DEFAULT_MODEL,
        store=False,
    )

    assert response.text
    assert response.response_id.startswith("resp_")
    assert response.request_id
