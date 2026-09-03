from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from chatgpt_client.cli import run
from chatgpt_client.models import GeneratedResponse, NewPrompt
from chatgpt_client.repository import PromptRepository


class _FakeGenerator:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, prompt: str, *, model: str, store: bool = False) -> GeneratedResponse:
        self.calls.append((prompt, model, store))
        return GeneratedResponse("resp_1", model, "A generated answer")


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_directory.name, "history.db")
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_local_show_does_not_initialize_api_client_or_require_key(self) -> None:
        def forbidden_factory(api_key: str, base_url: str | None):
            raise AssertionError("API client must not be initialized")

        result = run(
            ["--database", str(self.database), "show"],
            stdout=self.stdout,
            stderr=self.stderr,
            environ={},
            client_factory=forbidden_factory,
        )

        self.assertEqual(result, 0)
        self.assertEqual(self.stdout.getvalue().strip(), "Empty database.")
        self.assertEqual(self.stderr.getvalue(), "")

    def test_ask_generates_and_persists_response(self) -> None:
        generator = _FakeGenerator()
        observed_credentials = []

        def factory(api_key: str, base_url: str | None):
            observed_credentials.append((api_key, base_url))
            return generator

        result = run(
            ["--database", str(self.database), "ask", "Hello", "--model", "test-model"],
            stdout=self.stdout,
            stderr=self.stderr,
            environ={"OPENAI_API_KEY": "secret"},
            client_factory=factory,
        )

        self.assertEqual(result, 0)
        self.assertEqual(observed_credentials, [("secret", None)])
        self.assertEqual(generator.calls, [("Hello", "test-model", False)])
        repository = PromptRepository(self.database)
        self.assertEqual(repository.list()[0].response, "A generated answer")

    def test_search_uses_query_and_excludes_other_rows(self) -> None:
        repository = PromptRepository(self.database)
        repository.initialize()
        repository.add(NewPrompt("1", "needle", "model", "matching response"))
        repository.add(NewPrompt("2", "other", "model", "different response"))

        result = run(
            ["--database", str(self.database), "search", "needle"],
            stdout=self.stdout,
            stderr=self.stderr,
            environ={},
        )

        self.assertEqual(result, 0)
        output = self.stdout.getvalue()
        self.assertIn("needle", output)
        self.assertNotIn("different response", output)

    def test_legacy_action_syntax_remains_supported(self) -> None:
        result = run(
            ["--action", "show", "--database", str(self.database)],
            stdout=self.stdout,
            stderr=self.stderr,
            environ={},
        )
        self.assertEqual(result, 0)
        self.assertIn("Empty database.", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

