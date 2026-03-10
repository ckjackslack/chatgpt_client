import argparse
import ast
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
import tabulate

DB_FILE = "prompts.db"
DEFAULT_MODEL = "gpt-3.5-turbo-0301"


@dataclass(frozen=True)
class Prompt:
    key: str
    prompt: str
    model: str
    response: str


def cli(**kwargs) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query")
    parser.add_argument("--action", default="show", choices={"show", "ask", "clear", "search"})
    parser.add_argument("--id", nargs="?", type=int)

    if not kwargs:
        return parser.parse_args()

    flat_args = []
    for key, value in kwargs.items():
        flat_args.extend((f"--{key}", value))
    return parser.parse_args(flat_args)


def load_env(filename: str = ".env") -> dict[str, str]:
    filepath = Path(__file__).with_name(filename)
    if not filepath.is_file():
        return {}

    env: dict[str, str] = {}
    with filepath.open() as file:
        for line in file:
            stripped = line.strip()
            if not stripped or "=" not in stripped:
                continue
            key, value = map(str.strip, stripped.split("=", maxsplit=1))
            env[key] = value

    os.environ.update(env)
    return env


def get_auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_recent_model(headers: dict[str, str], list_all: bool = False) -> str:
    url = "https://api.openai.com/v1/models"
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json().get("data", [])
    available_models = sorted(((row["id"], row["created"]) for row in data), key=lambda item: -item[1])

    if list_all:
        print(available_models)

    if not available_models:
        raise RuntimeError("No models returned by the API.")

    return available_models[0][0]


def make_query(query: str, model: str, headers: dict[str, str], show_response: bool = False) -> list[Prompt]:
    url = "https://api.openai.com/v1/chat/completions"
    request_data = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "temperature": 0.7,
    }

    request_headers = {**headers, "Content-Type": "application/json"}
    response = requests.post(url, headers=request_headers, json=request_data, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if show_response:
        print(json.dumps(payload, indent=4, sort_keys=True))
        print()

    prompts: list[Prompt] = []
    for choice in payload.get("choices", []):
        if choice.get("finish_reason") != "stop":
            continue

        content = choice["message"]["content"]
        print(content)
        prompts.append(
            Prompt(
                key=payload.get("id", ""),
                prompt=query,
                model=model,
                response=content,
            )
        )
    return prompts


def setup_db(cur: sqlite3.Cursor) -> None:
    cur.execute("DROP TABLE IF EXISTS prompts")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prompts(
            id INTEGER PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            key TEXT,
            prompt TEXT,
            model TEXT,
            response TEXT
        );
        """.strip()
    )


def show_code(row: dict[str, str]) -> None:
    text = row["response"]
    token = "```"
    indexes = []
    index = 0

    while (index := text.find(token, index)) != -1:
        indexes.append(index)
        index += 1

    if len(indexes) % 2 != 0:
        return

    for start, stop in zip(indexes[::2], indexes[1::2]):
        print(text[start : stop + len(token)])
        print()


def is_valid_python(value: str) -> bool:
    try:
        ast.parse(value)
    except SyntaxError:
        return False
    return True


def fmt_snippet(row: dict[str, str], raw: bool = False) -> None:
    print("-" * 80)
    print(row["prompt"])
    print()
    if raw:
        print(row["response"])
    else:
        show_code(row)
    print("-" * 80)


def ensure_prompts_table(cur: sqlite3.Cursor) -> None:
    cur.execute("SELECT name FROM sqlite_master WHERE type=? AND name=?", ["table", "prompts"])
    if cur.fetchone() is None:
        setup_db(cur)


def sanitize_rows(rows: Iterable[dict]) -> list[dict]:
    shortened = []
    translate_table = str.maketrans({"\n": "", "\r": "", "\t": ""})

    for row in rows:
        new_row = dict(row)
        response = new_row["response"].translate(translate_table)
        response = re.sub(r"(\s)+", r"\1", response)
        new_row["response"] = f"{response[:30]}..." if len(response) > 30 else response
        shortened.append(new_row)

    return shortened


def resolve_model(headers: dict[str, str]) -> str:
    env_model = os.environ.get("MODEL", DEFAULT_MODEL)
    if env_model:
        return env_model
    return get_recent_model(headers)


def main() -> None:
    load_env()
    api_key = os.environ.get("OPENAI_API_KEY")
    assert api_key, "No .env file or missing key."

    headers = get_auth_header(api_key)
    model = resolve_model(headers)

    args = cli()

    with sqlite3.connect(DB_FILE) as db_connection:
        db_connection.row_factory = sqlite3.Row
        cur = db_connection.cursor()
        ensure_prompts_table(cur)

        if args.action == "clear":
            setup_db(cur)
            return

        if args.action == "ask":
            prompts = make_query(args.query, model, headers)
            cur.executemany(
                "INSERT INTO prompts (key, prompt, model, response) VALUES (?, ?, ?, ?)",
                ((item.key, item.prompt, item.model, item.response) for item in prompts),
            )
            return

        if args.action == "show":
            if isinstance(args.id, int):
                cur.execute("SELECT prompt, response FROM prompts WHERE id = ?", [args.id])
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    print("Q:", result["prompt"])
                    print("A:", result["response"])
                else:
                    print(f"No prompt with given id={args.id}.")
                return

            cur.execute("SELECT * FROM prompts ORDER BY created_at DESC")
            rows = [dict(row) for row in cur.fetchall()]
            if not rows:
                print("Empty database.")
                return

            print(tabulate.tabulate(sanitize_rows(rows), tablefmt="grid", headers="keys"))
            return

        if args.action == "search":
            cur.execute("SELECT created_at, prompt, response FROM prompts")
            rows = [dict(row) for row in cur.fetchall()]
            if not rows:
                print("No matching rows.")
                return

            for row in rows:
                if "```" in row["response"]:
                    fmt_snippet(row)
                elif is_valid_python(row["response"]):
                    fmt_snippet(row, raw=True)


if __name__ == "__main__":
    main()
