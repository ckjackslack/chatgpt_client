from __future__ import annotations

import ast
import re
from collections.abc import Iterable

from chatgpt_client.models import StoredPrompt


_FENCED_BLOCK = re.compile(r"```[^\n]*\n?(.*?)```", re.DOTALL)


def compact(value: str, width: int) -> str:
    text = " ".join(value.split())
    if len(text) <= width:
        return text
    return f"{text[: width - 3]}..."


def render_table(rows: Iterable[StoredPrompt]) -> str:
    headers = ("id", "created_at", "model", "prompt", "response")
    limits = (8, 19, 24, 40, 60)
    values = [
        (
            str(row.id),
            compact(row.created_at, limits[1]),
            compact(row.model, limits[2]),
            compact(row.prompt, limits[3]),
            compact(row.response, limits[4]),
        )
        for row in rows
    ]
    widths = [
        min(limit, max(len(header), *(len(row[index]) for row in values)))
        if values
        else len(header)
        for index, (header, limit) in enumerate(zip(headers, limits, strict=True))
    ]

    def render(row: tuple[str, ...]) -> str:
        return "| " + " | ".join(
            value.ljust(width) for value, width in zip(row, widths, strict=True)
        ) + " |"

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    rendered_rows = (render(row) for row in values)
    return "\n".join((separator, render(headers), separator, *rendered_rows, separator))


def code_snippets(value: str) -> list[str]:
    fenced = [match.strip() for match in _FENCED_BLOCK.findall(value) if match.strip()]
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
