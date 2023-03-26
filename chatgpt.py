import argparse
import ast
import json
import os
import re
import sqlite3
from typing import NamedTuple
from pprint import pp

import requests
import tabulate

# --------------------------------------

DB_FILE = 'prompts.db'


class Prompt(NamedTuple):
    id: str
    prompt: str
    model: str
    response: str


def cli(**kwargs):
    parser = argparse.ArgumentParser()
    parser.add_argument('--query')
    parser.add_argument('--action', default='show', choices={
        'show', 'ask', 'clear', 'search',
    })
    parser.add_argument('--id', nargs='?', type=int)
    if len(kwargs) == 0:
        return parser.parse_args()
    flat = []
    for tup in [(f"--{k}", v) for k, v in kwargs.items()]:
        flat.extend(tup)
    return parser.parse_args(flat)


def load_env(filename='.env'):
    filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))
    if os.path.isfile(filepath):
        env = {}
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    key, value = map(str.strip, line.split("="))
                    env[key] = value
        for k, v in env.items():
            globals()[k] = v


def get_recent_model(headers, list_all=False):
    url = 'https://api.openai.com/v1/models'
    response = requests.get(url, headers=headers)
    data = json.loads(response.text).get("data")
    available_models = [
        (row["id"], row["created"])
        for row
        in data
    ]
    available_models = sorted(available_models, key=lambda tup: -tup[1])
    if list_all:
        pp(available_models)
    recent_model = available_models[0][0]
    return recent_model


def make_query(query, model, headers, show_response=False):
    url = 'https://api.openai.com/v1/chat/completions'

    request_data = {
        'model': model,
        'messages': [
            {
                'role': 'user',
                'content': query,
            }
        ],
        'temperature': 0.7,
    }

    headers.update(**{"Content-Type": 'application/json'})

    response = requests.post(url, headers=headers, data=json.dumps(request_data))
    response = json.loads(response.text)
    if show_response:
        print(json.dumps(response, indent=4, sort_keys=True))
        print()

    prompts = []
    for choice in response.get("choices"):
        assert choice["finish_reason"] == "stop"
        content = choice["message"]["content"]
        print(content)
        prompts.append(
            Prompt(
                id=response.get("id"),
                prompt=query,
                model=model,
                response=content,
            )
        )
    return prompts


def setup_db(cur):
    cur.execute("DROP TABLE IF EXISTS prompts")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prompts(
            id INTEGER PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            key TEXT,
            prompt TEXT,
            model TEXT,
            response TEXT
        );
        """.strip())


def show_code(row):
    s = row["response"]
    tok = '```'
    index = 0
    positions = []
    while (index := s.find(tok, index)) != -1:
        positions.append(index)
        index += 1
    assert len(positions) % 2 == 0
    for pair in zip(positions[::2], positions[1::2]):
        start, stop = pair
        print(s[start:stop+len(tok)])
        print()


def is_valid_python(string):
   try:
       ast.parse(string)
   except SyntaxError:
       return False
   return True


def fmt_snippet(row, raw=False):
    print('-' * 80)
    print(row["prompt"])
    print()
    if not raw:
        show_code(row)
    else:
        print(row["response"])
    print('-' * 80)


get_auth_header = lambda tok: {"Authorization": f"Bearer {tok}"}

# --------------------------------------

def main():
    load_env()
    assert "OPENAI_API_KEY" in globals(), "No .env file or missing key."
    headers = {}
    headers.update(**get_auth_header(OPENAI_API_KEY))

    if "MODEL" not in globals():
        recent_model = 'gpt-3.5-turbo-0301'
    elif MODEL is None:
        recent_model = get_recent_model(headers)
    else:
        recent_model = MODEL

    args = cli()
    query = args.query
    action = args.action

    with sqlite3.connect(DB_FILE) as db_connection:
        db_connection.row_factory = sqlite3.Row
        cur = db_connection.cursor()

        try:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type=? AND name=?",
                ["table", "prompts"],
            )
            result = cur.fetchone()
            assert result is not None
        except AssertionError:
            setup_db(cur)

        if action == 'clear':
            setup_db(cur)

        if action == 'ask':
            ret = make_query(query, recent_model, headers)
            for e in ret:
                d = e._asdict()
                d['key'] = d['id']
                del d['id']
            cur.executemany(
               "INSERT INTO prompts (key, prompt, model, response) VALUES (?, ?, ?, ?)",
                ret,
            )
        elif action == 'show':
            if "id" in args and isinstance(args.id, int):
                cur.execute("SELECT prompt, response FROM prompts WHERE id = ?", [args.id])
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    result = iter(result.items())
                    print("Q:", next(result)[1])
                    print("A:", next(result)[1])
                else:
                    print(f"No prompt with given id={args.id}.")
            else:
                cur.execute("SELECT * FROM prompts ORDER BY created_at DESC")
                rows = [dict(row) for row in cur.fetchall()]
                if rows:
                    fmt_response = lambda s, n=30: f"{s[:n]}..." if len(s) > n else s
                    table = str.maketrans({"\n": "", "\r": "", "\t": ""})
                    for row in rows:
                        response = row["response"]
                        response = response.translate(table)
                        response = re.sub(r"(\s)+", r"\1", response)
                        response = fmt_response(response)
                        row["response"] = response
                    print(tabulate.tabulate(
                        rows,
                        tablefmt='grid',
                        headers='keys',
                    ))
                else:
                    print("Empty database.")
        elif action == 'search':
            cur.execute("SELECT created_at, prompt, response FROM prompts")
            rows = [dict(row) for row in cur.fetchall()]
            if len(rows) > 0:
                for row in rows:
                    if '```' in row["response"]:
                        fmt_snippet(row)
                    elif is_valid_python(row["response"]):
                        fmt_snippet(row, raw=True)
            else:
                print("No matching rows.")

if __name__ == '__main__':
    main()
