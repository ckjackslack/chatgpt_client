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
    """
    Parse and return the program's command-line arguments.
    
    When called with no keyword arguments, parses the actual process argv; when provided keyword arguments, constructs an argument list from each key/value pair (as `--key value`) and parses that instead.
    
    Parameters:
        **kwargs: Optional mapping of CLI option names to values used to simulate command-line input.
    
    Returns:
        argparse.Namespace: Parsed arguments with attributes `query` (str | None), `action` (str), and `id` (int | None).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--query")
    parser.add_argument("--action", default="show", choices={"show", "ask", "clear", "search"})
    parser.add_argument("--id", nargs="?", type=int)

    if not kwargs:
        return parser.parse_args()

    flat_args = []
    for key, value in kwargs.items():
        flat_args.extend((f"--{key}", str(value)))
    return parser.parse_args(flat_args)


def load_env(filename: str = ".env") -> dict[str, str]:
    """
    Load environment variables from a .env file located alongside this script, populate os.environ with them, and return the parsed mapping.
    
    Parameters:
        filename (str): Name of the .env file to read (default ".env").
    
    Returns:
        dict[str, str]: Mapping of keys to values parsed from the file. Empty dict if the file does not exist or contains no valid KEY=VALUE lines.
    
    Notes:
        - Lines without an '=' or that are empty are ignored.
        - Existing environment variables are overwritten by values from the file.
    """
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
    """
    Build an HTTP Authorization header using a Bearer token.
    
    Parameters:
        token (str): The API key or token to include in the header (e.g., OpenAI API key).
    
    Returns:
        dict[str, str]: Mapping with the `Authorization` header set to `Bearer <token>`.
    """
    return {"Authorization": f"Bearer {token}"}


def get_recent_model(headers: dict[str, str], list_all: bool = False) -> str:
    """
    Selects the most recently created OpenAI model by querying the models API.
    
    Parameters:
        headers (dict[str, str]): HTTP headers to send with the request (must include authorization).
        list_all (bool): If True, prints the list of available models as (id, created) tuples.
    
    Returns:
        str: The model ID of the most recently created model.
    
    Raises:
        RuntimeError: If the API returns no models.
    """
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
    """
    Send a chat completion request to OpenAI and collect each finished response as a Prompt.
    
    Sends the provided query to the Chat Completions API using the specified model and headers. If show_response is True, prints the raw JSON payload; always prints each accepted choice's content and returns a list of Prompt objects built from choices whose `finish_reason` is "stop".
    
    Parameters:
        query (str): The user message to send to the model.
        model (str): The model identifier to use for the request.
        headers (dict[str, str]): HTTP headers to include (must contain any required authorization).
        show_response (bool): If True, print the raw JSON response payload before printing choices.
    
    Returns:
        list[Prompt]: A list of Prompt instances for each choice with `finish_reason == "stop"`.
    """
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
    """
    Initialize the database schema for storing prompts.
    
    Creates the `prompts` table (dropping any existing one) with columns:
    `id` (primary key), `created_at` (defaults to current timestamp),
    `key`, `prompt`, `model`, and `response`.
    
    Parameters:
        cur (sqlite3.Cursor): SQLite cursor used to execute the schema statements.
    """
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
    """
    Prints fenced code blocks found in the row's response.
    
    Searches the value at row["response"] for code fences delimited by triple backticks (```). For each complete opening/closing pair, prints the block including the backtick delimiters and separates blocks with a blank line. If an unmatched fence is present, nothing is printed.
    
    Parameters:
        row (dict[str, str]): A mapping that must contain the key "response" with the text to scan for fenced code blocks.
    """
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
    """
    Determines whether a string contains syntactically valid Python code.
    
    Parameters:
        value (str): The source code to validate.
    
    Returns:
        `true` if the string parses as valid Python code, `false` otherwise.
    """
    try:
        ast.parse(value)
    except SyntaxError:
        return False
    return True


def fmt_snippet(row: dict[str, str], raw: bool = False) -> None:
    """
    Prints a formatted snippet showing the prompt and either the raw response or its fenced code blocks.
    
    Parameters:
        row (dict[str, str]): Mapping with keys "prompt" and "response". The "prompt" value is printed verbatim; the "response" value is printed either raw or parsed for fenced code blocks.
        raw (bool): If True, print the full response as-is. If False, extract and print fenced code blocks from the response using show_code.
    """
    print("-" * 80)
    print(row["prompt"])
    print()
    if raw:
        print(row["response"])
    else:
        show_code(row)
    print("-" * 80)


def ensure_prompts_table(cur: sqlite3.Cursor) -> None:
    """
    Ensure the "prompts" table exists in the SQLite database, creating it if absent.
    
    Checks sqlite_master for a table named "prompts" and calls setup_db(cur) to create the schema when missing.
    
    Parameters:
        cur (sqlite3.Cursor): SQLite cursor open on the target database.
    """
    cur.execute("SELECT name FROM sqlite_master WHERE type=? AND name=?", ["table", "prompts"])
    if cur.fetchone() is None:
        setup_db(cur)


def sanitize_rows(rows: Iterable[dict]) -> list[dict]:
    """
    Normalize and truncate the 'response' field in each row dictionary for compact display.
    
    Each input row is shallow-copied; its "response" value has newline, carriage return,
    and tab characters removed, consecutive whitespace collapsed to single spaces, and
    is truncated to 30 characters with an appended ellipsis ("...") when longer.
    
    Parameters:
        rows (Iterable[dict]): An iterable of mapping-like objects where each dict contains a
            "response" key with a string value.
    
    Returns:
        list[dict]: A new list of dicts with the same keys as input rows and a cleaned,
            possibly truncated "response" value in each dict.
    """
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
    """
    Select the model identifier to use for requests, preferring the MODEL environment variable.
    
    Returns:
        model (str): The model id from the `MODEL` environment variable if set, otherwise `DEFAULT_MODEL`.
    """
    env_model = os.environ.get("MODEL", DEFAULT_MODEL)
    if env_model:
        return env_model
    return get_recent_model(headers)


def main() -> None:
    """
    Run the command-line interface: load environment variables, resolve the OpenAI model, and dispatch user-specified actions that query and manage the prompts database.
    
    Supported actions:
    - "clear": reinitialize the prompts database schema.
    - "ask": send the provided query to the resolved model, store returned prompts and responses in the database.
    - "show": print either a single prompt/response by id or a tabulated list of stored prompts ordered by creation time.
    - "search": print formatted snippets or raw Python code extracted from stored responses.
    
    Requires OPENAI_API_KEY to be present in the environment; observable effects include network calls to the OpenAI API, modifications to the SQLite database at DB_FILE, and output printed to standard output.
    """
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
