from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

from chatgpt_client import __version__
from chatgpt_client.api import OpenAIResponsesClient, ResponseGenerationError, TextGenerator
from chatgpt_client.config import ConfigurationError, load_settings
from chatgpt_client.formatting import code_snippets, render_table
from chatgpt_client.models import NewPrompt, StoredPrompt
from chatgpt_client.repository import PromptRepository


Action = Literal["show", "ask", "search", "clear"]
ClientFactory = Callable[[str, str | None], TextGenerator]


@dataclass(frozen=True, slots=True)
class Command:
    action: Action
    query: str | None
    prompt_id: int | None
    model: str | None
    code_only: bool
    env_file: Path
    database: Path | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt-client",
        description="Ask OpenAI and keep a searchable local SQLite history.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", type=Path)

    commands = parser.add_subparsers(dest="action")
    show = commands.add_parser("show", help="List history or show one entry.")
    show.add_argument("id", nargs="?", type=int)

    ask = commands.add_parser("ask", help="Send a prompt to the Responses API.")
    ask.add_argument("query")
    ask.add_argument("--model")

    search = commands.add_parser("search", help="Search prompts and responses.")
    search.add_argument("query")
    search.add_argument(
        "--code-only",
        action="store_true",
        help="Print only fenced or valid Python code from matching responses.",
    )

    commands.add_parser("clear", help="Delete all locally stored history.")
    return parser


def parse_command(argv: Sequence[str] | None = None) -> Command:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _uses_legacy_syntax(arguments):
        return _parse_legacy(arguments)

    parser = build_parser()
    namespace = parser.parse_args(arguments)
    action: Action = namespace.action or "show"
    return Command(
        action=action,
        query=getattr(namespace, "query", None),
        prompt_id=getattr(namespace, "id", None),
        model=getattr(namespace, "model", None),
        code_only=getattr(namespace, "code_only", False),
        env_file=namespace.env_file,
        database=namespace.database,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    environ: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
) -> int:
    try:
        command = parse_command(argv)
        settings = load_settings(
            env_file=command.env_file,
            environ=os.environ if environ is None else environ,
            database_override=command.database,
            model_override=command.model,
        )
        repository = PromptRepository(settings.database_path)
        repository.initialize()

        if command.action == "ask":
            api_key = settings.require_api_key()
            factory = client_factory or _create_client
            client = factory(api_key, settings.base_url)
            generated = client.generate(
                command.query or "",
                model=settings.model,
                store=settings.store_responses,
            )
            repository.add(
                NewPrompt(
                    response_id=generated.response_id,
                    prompt=command.query or "",
                    model=generated.model,
                    response=generated.text,
                )
            )
            print(generated.text, file=stdout)
            return 0

        if command.action == "clear":
            deleted = repository.clear()
            print(f"Deleted {deleted} prompt(s).", file=stdout)
            return 0

        if command.action == "search":
            rows = repository.search(command.query or "")
            if not rows:
                print("No matching rows.", file=stdout)
                return 0
            if command.code_only:
                return _print_code(rows, stdout)
            print(render_table(rows), file=stdout)
            return 0

        if command.prompt_id is not None:
            row = repository.get(command.prompt_id)
            if row is None:
                print(f"No prompt with id={command.prompt_id}.", file=stdout)
                return 0
            print(f"Q: {row.prompt}\nA: {row.response}", file=stdout)
            return 0

        rows = repository.list()
        if not rows:
            print("Empty database.", file=stdout)
            return 0
        print(render_table(rows), file=stdout)
        return 0
    except (ConfigurationError, ResponseGenerationError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


def _create_client(api_key: str, base_url: str | None) -> TextGenerator:
    return OpenAIResponsesClient(api_key, base_url=base_url)


def _print_code(rows: Sequence[StoredPrompt], stdout: TextIO) -> int:
    found = False
    for row in rows:
        snippets = code_snippets(row.response)
        for snippet in snippets:
            found = True
            print(f"# Prompt {row.id}: {row.prompt}\n\n{snippet}\n", file=stdout)
    if not found:
        print("No code snippets found in matching rows.", file=stdout)
    return 0


def _uses_legacy_syntax(arguments: Sequence[str]) -> bool:
    return any(
        argument == option or argument.startswith(f"{option}=")
        for argument in arguments
        for option in ("--action", "--query", "--id")
    )


def _parse_legacy(arguments: Sequence[str]) -> Command:
    parser = argparse.ArgumentParser(prog="chatgpt.py")
    parser.add_argument("--action", choices=("show", "ask", "clear", "search"), default="show")
    parser.add_argument("--query")
    parser.add_argument("--id", type=int)
    parser.add_argument("--model")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", type=Path)
    parser.add_argument("--code-only", action="store_true")
    namespace = parser.parse_args(arguments)
    if namespace.action in {"ask", "search"} and not namespace.query:
        parser.error(f"--query is required for {namespace.action}")
    return Command(
        action=namespace.action,
        query=namespace.query,
        prompt_id=namespace.id,
        model=namespace.model,
        code_only=namespace.code_only,
        env_file=namespace.env_file,
        database=namespace.database,
    )

