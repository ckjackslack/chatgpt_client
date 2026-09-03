from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TextIO, TypeAlias

from chatgpt_client import __version__
from chatgpt_client.application import ChatGPTApplication, GeneratorFactory
from chatgpt_client.config import Settings, load_settings
from chatgpt_client.diagnostics import (
    configuration_diagnostics,
    render_diagnostics,
    response_diagnostics,
)
from chatgpt_client.errors import ChatGPTClientError, UsageError
from chatgpt_client.formatting import code_snippets, render_table
from chatgpt_client.models import StoredPrompt
from chatgpt_client.repository import PromptRepository


class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    USAGE = 2
    INTERRUPTED = 130


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    env_file: Path
    database: Path | None
    verbose: bool = False


@dataclass(frozen=True, slots=True)
class ShowCommand:
    options: RuntimeOptions
    prompt_id: int | None = None


@dataclass(frozen=True, slots=True)
class AskCommand:
    options: RuntimeOptions
    query: str
    model: str | None = None


@dataclass(frozen=True, slots=True)
class SearchCommand:
    options: RuntimeOptions
    query: str
    code_only: bool = False


@dataclass(frozen=True, slots=True)
class ClearCommand:
    options: RuntimeOptions
    confirmed: bool = False


Command: TypeAlias = ShowCommand | AskCommand | SearchCommand | ClearCommand


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt-client",
        description="Ask OpenAI and keep a searchable local SQLite history.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_runtime_options(parser)

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

    clear = commands.add_parser("clear", help="Delete all locally stored history.")
    clear.add_argument("--yes", action="store_true", help="Confirm deletion.")
    return parser


def parse_command(argv: Sequence[str] | None = None) -> Command:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _uses_legacy_syntax(arguments):
        return _parse_legacy(arguments)

    namespace = build_parser().parse_args(arguments)
    options = _runtime_options(namespace)
    match namespace.action:
        case "ask":
            return AskCommand(options, namespace.query, namespace.model)
        case "search":
            return SearchCommand(options, namespace.query, namespace.code_only)
        case "clear":
            return ClearCommand(options, namespace.yes)
        case "show" | None:
            return ShowCommand(options, getattr(namespace, "id", None))
        case action:  # pragma: no cover - argparse restricts this value
            raise AssertionError(f"Unexpected action: {action}")


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    environ: Mapping[str, str] | None = None,
    generator_factory: GeneratorFactory | None = None,
) -> int:
    try:
        command = parse_command(argv)
        settings = _settings(command, os.environ if environ is None else environ)
        if command.options.verbose:
            _print_diagnostics(configuration_diagnostics(settings), stderr)
        application = ChatGPTApplication(
            PromptRepository(
                settings.database_path,
                timeout_seconds=settings.database_timeout_seconds,
            ),
            generator_factory=generator_factory,
        )
        application.initialize()
        return int(_execute(command, settings, application, stdout, stderr))
    except UsageError as exc:
        print(f"error: {exc}", file=stderr)
        return int(ExitCode.USAGE)
    except ChatGPTClientError as exc:
        print(f"error: {exc}", file=stderr)
        return int(ExitCode.ERROR)
    except KeyboardInterrupt:
        print("error: interrupted.", file=stderr)
        return int(ExitCode.INTERRUPTED)


def main() -> None:
    raise SystemExit(run())


def _execute(
    command: Command,
    settings: Settings,
    application: ChatGPTApplication,
    stdout: TextIO,
    stderr: TextIO,
) -> ExitCode:
    match command:
        case AskCommand(query=query):
            stored = application.ask(query, settings)
            print(stored.response, file=stdout)
            if command.options.verbose:
                _print_diagnostics(response_diagnostics(stored), stderr)
        case ClearCommand(confirmed=False):
            raise UsageError("Refusing to delete history without --yes.")
        case ClearCommand():
            print(f"Deleted {application.clear()} prompt(s).", file=stdout)
        case SearchCommand(query=query, code_only=True):
            _print_code(application.search(query), stdout)
        case SearchCommand(query=query):
            _print_rows(application.search(query), stdout, empty="No matching rows.")
        case ShowCommand(prompt_id=prompt_id) if prompt_id is not None:
            _print_prompt(application.get(prompt_id), prompt_id, stdout)
        case ShowCommand():
            _print_rows(application.history(), stdout, empty="Empty database.")
    return ExitCode.SUCCESS


def _settings(command: Command, environ: Mapping[str, str]) -> Settings:
    model = command.model if isinstance(command, AskCommand) else None
    return load_settings(
        env_file=command.options.env_file,
        environ=environ,
        database_override=command.options.database,
        model_override=model,
    )


def _print_prompt(row: StoredPrompt | None, prompt_id: int, stdout: TextIO) -> None:
    if row is None:
        print(f"No prompt with id={prompt_id}.", file=stdout)
        return
    print(f"Q: {row.prompt}\nA: {row.response}", file=stdout)


def _print_rows(rows: Sequence[StoredPrompt], stdout: TextIO, *, empty: str) -> None:
    print(render_table(rows) if rows else empty, file=stdout)


def _print_code(rows: Sequence[StoredPrompt], stdout: TextIO) -> None:
    snippets = [
        (row, snippet)
        for row in rows
        for snippet in code_snippets(row.response)
    ]
    if not snippets:
        print("No code snippets found in matching rows.", file=stdout)
        return
    for row, snippet in snippets:
        print(f"# Prompt {row.id}: {row.prompt}\n\n{snippet}\n", file=stdout)


def _print_diagnostics(values: Sequence[str], stderr: TextIO) -> None:
    print(render_diagnostics(values), file=stderr)


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", type=Path)
    parser.add_argument("--verbose", action="store_true")


def _runtime_options(namespace: argparse.Namespace) -> RuntimeOptions:
    return RuntimeOptions(namespace.env_file, namespace.database, namespace.verbose)


def _uses_legacy_syntax(arguments: Sequence[str]) -> bool:
    return any(
        argument == option or argument.startswith(f"{option}=")
        for argument in arguments
        for option in ("--action", "--query", "--id")
    )


def _parse_legacy(arguments: Sequence[str]) -> Command:
    parser = argparse.ArgumentParser(prog="chatgpt.py")
    parser.add_argument(
        "--action",
        choices=("show", "ask", "clear", "search"),
        default="show",
    )
    parser.add_argument("--query")
    parser.add_argument("--id", type=int)
    parser.add_argument("--model")
    parser.add_argument("--code-only", action="store_true")
    parser.add_argument("--yes", action="store_true")
    _add_runtime_options(parser)
    namespace = parser.parse_args(arguments)
    options = _runtime_options(namespace)
    match namespace.action:
        case "ask":
            if not namespace.query:
                parser.error("--query is required for ask")
            return AskCommand(options, namespace.query, namespace.model)
        case "search":
            if not namespace.query:
                parser.error("--query is required for search")
            return SearchCommand(options, namespace.query, namespace.code_only)
        case "clear":
            return ClearCommand(options, namespace.yes)
        case "show":
            return ShowCommand(options, namespace.id)
        case action:  # pragma: no cover - argparse restricts this value
            raise AssertionError(f"Unexpected action: {action}")
