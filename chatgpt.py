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
    Parse and return CLI arguments for the application.
    
    When no keyword arguments are provided, parses arguments from the process command line. When keyword arguments are provided, each key/value pair is treated as an option name and value (e.g., query="text" -> ["--query", "text"]) and those constructed arguments are parsed instead.
    
    Parameters:
        kwargs: Optional mapping of argument names to values used to construct arguments for parsing (commonly used in tests).
    
    Returns:
        argparse.Namespace: Parsed arguments with attributes `query` (str|None), `action` (one of "show", "ask", "clear", "search"), and `id` (int|None).
    """
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
    """
    Load environment variables from a .env-style file located next to the module and return the parsed key/value pairs.
    
    Reads the specified file (relative to this module). Lines containing a single `KEY=VALUE` pair are parsed and collected; empty lines or lines without `=` are ignored. The parsed mappings are merged into os.environ as a side effect.
    
    Parameters:
        filename (str): Name of the env file to read (defaults to ".env").
    
    Returns:
        dict[str, str]: Mapping of parsed environment variables. Returns an empty dict if the file does not exist or no valid pairs are found.
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
    Builds an HTTP Authorization header using a bearer token.
    
    Parameters:
        token (str): The bearer token (for example, an OpenAI API key) to include in the header.
    
    Returns:
        dict[str, str]: A dictionary with the `Authorization` header set to `Bearer <token>`.
    """
    return {"Authorization": f"Bearer {token}"}


def get_recent_model(headers: dict[str, str], list_all: bool = False) -> str:
    """
    Return the most recently created model id from the OpenAI Models API.
    
    Parameters:
        headers (dict[str, str]): Authorization and other HTTP headers to use for the API request.
        list_all (bool): If True, print the list of available models with their creation timestamps.
    
    Returns:
        str: The id of the most recently created model.
    
    Raises:
        requests.HTTPError: If the HTTP request to the API fails.
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
    Send a chat completion request to the OpenAI Chat Completions API and return prompts built from the response choices.
    
    Parameters:
        query (str): The user message to send as the chat prompt.
        model (str): The model identifier to use for the completion (e.g., "gpt-3.5-turbo").
        headers (dict[str, str]): HTTP headers including authorization required for the API request.
        show_response (bool): If True, print the raw JSON payload returned by the API before processing choices.
    
    Returns:
        list[Prompt]: A list of Prompt objects created from response choices whose `finish_reason` is "stop".
    
    Raises:
        requests.HTTPError: If the HTTP request returns a non-success status (propagated from response.raise_for_status()).
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
    Ensure the SQLite database contains a `prompts` table with the expected schema, recreating it if it already exists.
    
    The resulting table has columns:
    - id: INTEGER PRIMARY KEY
    - created_at: DATETIME with default CURRENT_TIMESTAMP
    - key: TEXT
    - prompt: TEXT
    - model: TEXT
    - response: TEXT
    
    Parameters:
        cur (sqlite3.Cursor): An open SQLite cursor against the target database.
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
    Print each fenced code block found in row['response'].
    
    Scans the string at row['response'] for fenced code blocks delimited by triple backticks (```) and prints each complete code block followed by a blank line. If an unmatched (odd) number of backtick delimiters is present, nothing is printed.
    
    Parameters:
        row (dict[str, str]): A mapping containing a 'response' key whose value is the text to scan for fenced code blocks.
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
    Determine whether a string is syntactically valid Python source code.
    
    Parameters:
        value (str): The source code to check.
    
    Returns:
        True if `value` can be parsed as valid Python, False otherwise.
    """
    try:
        ast.parse(value)
    except SyntaxError:
        return False
    return True


def fmt_snippet(row: dict[str, str], raw: bool = False) -> None:
    """
    Prints a prompt and its response framed by separator lines, optionally showing the raw response.
    
    Parameters:
        row (dict[str, str]): A mapping containing at least the keys "prompt" and "response". "prompt" is printed as the question; "response" is shown either raw or formatted.
        raw (bool): If True, prints the response text verbatim; if False, extracts and prints code blocks from the response when available.
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
    Ensure the SQLite database contains a table named "prompts"; create the table if it does not exist.
    
    Parameters:
        cur (sqlite3.Cursor): Cursor bound to the target SQLite database connection.
    """
    cur.execute("SELECT name FROM sqlite_master WHERE type=? AND name=?", ["table", "prompts"])
    if cur.fetchone() is None:
        setup_db(cur)


def sanitize_rows(rows: Iterable[dict]) -> list[dict]:
    """
    Sanitize and truncate the "response" field of each row.
    
    Parameters:
        rows (Iterable[dict]): Iterable of row-like dictionaries that must contain a "response" string.
    
    Returns:
        list[dict]: A new list of row dictionaries where each "response" has newlines, carriage returns,
        and tabs removed; consecutive whitespace collapsed to a single character; and values longer
        than 30 characters truncated to the first 30 characters followed by an ellipsis ("...").
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
    Select the model identifier to use for API requests.
    
    Prefers the MODEL environment variable when set; otherwise queries the OpenAI models endpoint using the provided HTTP headers to determine a recent model.
    
    Parameters:
        headers (dict[str, str]): HTTP headers (including authorization) used when querying the OpenAI models API if no MODEL environment variable is set.
    
    Returns:
        model_id (str): The selected model identifier.
    """
    env_model = os.environ.get("MODEL", DEFAULT_MODEL)
    if env_model:
        return env_model
    return get_recent_model(headers)


def main() -> None:
    """
    Run the command-line interface: load environment variables, resolve OpenAI credentials and model, and perform the selected action against the local prompts database.
    
    Supported actions:
    - "clear": reset the prompts table.
    - "ask": send the provided query to the API, print responses, and insert returned Prompt records into the prompts database.
    - "show": if an integer --id is provided, print that prompt's question and answer; otherwise list all stored prompts in a tabulated grid.
    - "search": iterate stored prompts and print formatted code or raw Python snippets when detected.
    
    This function requires OPENAI_API_KEY to be present in the environment (loaded from .env if available) and operates on the database file defined by DB_FILE. Outputs are written to stdout; database changes are persisted to the SQLite database.
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
