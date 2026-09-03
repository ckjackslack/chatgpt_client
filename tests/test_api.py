from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from chatgpt_client.api import OpenAIResponsesClient, ResponseGenerationError


class _FakeResponse:
    id = "resp_123"
    model = "resolved-model"
    output_text = " generated text "


class _FakeResponses:
    def __init__(self) -> None:
        self.arguments = None

    def create(self, **kwargs):
        self.arguments = kwargs
        return _FakeResponse()


class _FakeOpenAI:
    last_instance = None

    def __init__(self, **kwargs) -> None:
        self.options = kwargs
        self.responses = _FakeResponses()
        _FakeOpenAI.last_instance = self


class APIClientTests(unittest.TestCase):
    def test_generate_uses_responses_api_and_explicit_storage_setting(self) -> None:
        fake_module = types.SimpleNamespace(OpenAI=_FakeOpenAI, OpenAIError=RuntimeError)
        with patch.dict(sys.modules, {"openai": fake_module}):
            client = OpenAIResponsesClient("secret")
            result = client.generate("hello", model="chosen-model", store=False)

        instance = _FakeOpenAI.last_instance
        self.assertEqual(
            instance.responses.arguments,
            {"model": "chosen-model", "input": "hello", "store": False},
        )
        self.assertEqual(result.response_id, "resp_123")
        self.assertEqual(result.model, "resolved-model")
        self.assertEqual(result.text, "generated text")

    def test_empty_text_is_rejected(self) -> None:
        class EmptyResponse(_FakeResponse):
            output_text = "  "

        class EmptyResponses(_FakeResponses):
            def create(self, **kwargs):
                return EmptyResponse()

        class EmptyOpenAI(_FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                self.responses = EmptyResponses()

        fake_module = types.SimpleNamespace(OpenAI=EmptyOpenAI, OpenAIError=RuntimeError)
        with patch.dict(sys.modules, {"openai": fake_module}):
            client = OpenAIResponsesClient("secret")
            with self.assertRaises(ResponseGenerationError):
                client.generate("hello", model="model")


if __name__ == "__main__":
    unittest.main()

