from __future__ import annotations

import pytest

from chatgpt_client.formatting import code_snippets, compact, is_valid_python, render_table
from chatgpt_client.models import StoredPrompt


def row(**overrides: object) -> StoredPrompt:
    values: dict[str, object] = {
        "id": 1,
        "created_at": "2026-09-03 20:00:00",
        "response_id": "resp_test",
        "request_id": "req_test",
        "prompt": "question",
        "model": "test-model",
        "response": "answer",
    }
    values.update(overrides)
    return StoredPrompt(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "width", "expected"),
    [
        ("short", 10, "short"),
        ("many\n\tspaces", 20, "many spaces"),
        ("abcdefghij", 7, "abcd..."),
    ],
)
def test_compact(value: str, width: int, expected: str) -> None:
    assert compact(value, width) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("```python\nprint('one')\n```", ["print('one')"]),
        ("before\n```py\na = 1\n```\nafter\n```\nb = 2\n```", ["a = 1", "b = 2"]),
        ("x = 1\nprint(x)", ["x = 1\nprint(x)"]),
        ("ordinary prose", []),
        ("```python\nunclosed", []),
    ],
)
def test_code_snippets(value: str, expected: list[str]) -> None:
    assert code_snippets(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("x = 1", True), ("x =", False), ("", False)])
def test_is_valid_python(value: str, expected: bool) -> None:
    assert is_valid_python(value) is expected


def test_render_table_truncates_values_and_keeps_aligned_borders() -> None:
    table = render_table(
        [
            row(id=1234567890, prompt="p" * 100, response="r" * 100),
            row(id=2, prompt="short"),
        ]
    )
    lines = table.splitlines()
    assert all(len(line) == len(lines[0]) for line in lines)
    assert "12345..." in table
    assert "p" * 37 + "..." in table
    assert "r" * 57 + "..." in table

