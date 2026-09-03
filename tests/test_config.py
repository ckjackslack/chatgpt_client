from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chatgpt_client.config import ConfigurationError, load_settings, read_env_file


class SettingsTests(unittest.TestCase):
    def test_process_environment_overrides_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text(
                "OPENAI_API_KEY=file-key\nOPENAI_MODEL='file-model'\n",
                encoding="utf-8",
            )

            settings = load_settings(
                env_file=env_file,
                environ={"OPENAI_API_KEY": "process-key", "OPENAI_MODEL": "process-model"},
            )

        self.assertEqual(settings.api_key, "process-key")
        self.assertEqual(settings.model, "process-model")

    def test_read_env_file_supports_export_and_embedded_equals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text("export TOKEN=one=two\n", encoding="utf-8")
            self.assertEqual(read_env_file(env_file), {"TOKEN": "one=two"})

    def test_invalid_boolean_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(environ={"OPENAI_STORE_RESPONSES": "perhaps"})


if __name__ == "__main__":
    unittest.main()

