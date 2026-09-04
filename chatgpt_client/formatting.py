from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from chatgpt_client.models import StoredPrompt


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    width: int
    value: Callable[[StoredPrompt], str]


_COLUMNS = (
    Column("id", 8, lambda row: str(row.id)),
    Column("created_at", 19, lambda row: row.created_at),
    Column("model", 24, lambda row: row.model),
    Column("prompt", 40, lambda row: row.prompt),
    Column("response", 60, lambda row: row.response),
)


def compact(value: str, width: int) -> str:
    text = " ".join(value.split())
    if len(text) <= width:
        return text
    return f"{text[: width - 3]}..."


def render_table(rows: Iterable[StoredPrompt]) -> str:
    headers = tuple(column.name for column in _COLUMNS)
    values = [
        tuple(compact(column.value(row), column.width) for column in _COLUMNS)
        for row in rows
    ]
    widths = [
        min(column.width, max(len(column.name), *(len(row[index]) for row in values)))
        if values
        else len(column.name)
        for index, column in enumerate(_COLUMNS)
    ]

    def render(row: tuple[str, ...]) -> str:
        return "| " + " | ".join(
            value.ljust(width) for value, width in zip(row, widths, strict=True)
        ) + " |"

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    rendered_rows = (render(row) for row in values)
    return "\n".join((separator, render(headers), separator, *rendered_rows, separator))


def code_snippets(value: str) -> list[str]:
    fenced = _fenced_code_blocks(value)
    if fenced:
        return fenced
    if is_valid_python(value):
        return [value.strip()]
    return []


def is_valid_python(value: str) -> bool:
    try:
        ast.parse(value)
    except SyntaxError:
        return False
    return bool(value.strip())


def _fenced_code_blocks(value: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in value.splitlines():
        stripped = line.strip()
        if current is None:
            if stripped.startswith("```") and "`" not in stripped[3:]:
                current = []
            continue
        if stripped == "```":
            code = "\n".join(current).strip()
            if code:
                blocks.append(code)
            current = None
        else:
            current.append(line)
    return blocks
