from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from chatgpt_client.models import NewPrompt
from chatgpt_client.repository import PromptRepository


class PromptRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_directory.name, "prompts.db")
        self.repository = PromptRepository(self.database)
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def add(self, prompt: str = "question", response: str = "answer") -> int:
        return self.repository.add(
            NewPrompt(
                response_id="resp_123",
                prompt=prompt,
                model="test-model",
                response=response,
            )
        ).id

    def test_add_get_list_search_and_clear(self) -> None:
        prompt_id = self.add("Where is the fish?", "The fish is here.")
        self.add("Unrelated", "Nothing to see")

        self.assertEqual(self.repository.get(prompt_id).prompt, "Where is the fish?")
        self.assertEqual(len(self.repository.list()), 2)
        self.assertEqual([row.id for row in self.repository.search("FISH")], [prompt_id])
        self.assertEqual(self.repository.clear(), 2)
        self.assertEqual(self.repository.list(), [])

    def test_search_treats_sql_wildcards_as_literals(self) -> None:
        percent_id = self.add("100%", "percent")
        self.add("1000", "number")
        self.assertEqual([row.id for row in self.repository.search("%")], [percent_id])

    def test_existing_table_without_key_is_migrated_without_data_loss(self) -> None:
        legacy_database = Path(self.temp_directory.name, "legacy.db")
        with sqlite3.connect(legacy_database) as connection:
            connection.execute(
                """
                CREATE TABLE prompts (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    prompt TEXT,
                    model TEXT,
                    response TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO prompts (prompt, model, response) VALUES (?, ?, ?)",
                ("old question", "old model", "old answer"),
            )

        repository = PromptRepository(legacy_database)
        repository.initialize()

        self.assertEqual(repository.list()[0].prompt, "old question")
        with sqlite3.connect(legacy_database) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(prompts)")}
        self.assertIn("key", columns)


if __name__ == "__main__":
    unittest.main()

