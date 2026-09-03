# chatgpt-client

A small Python 3.11+ command-line client for the OpenAI Responses API. It keeps a local,
searchable SQLite history while isolating API access, configuration, persistence, and CLI
presentation in separate modules.

## Highlights

- Uses the official `openai` Python SDK and the Responses API.
- Stores responses remotely only when explicitly enabled; local history is always kept in SQLite.
- Local commands (`show`, `search`, and `clear`) work without an API key or network access.
- Runs explicit, transactional SQLite schema migrations without discarding existing history.
- Records OpenAI response and request IDs for production diagnostics.
- Uses configurable SDK timeouts and bounded automatic retries.
- Supports both modern subcommands and the original `--action` syntax.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create `.env` in the working directory or export the values directly:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-5.6-sol
```

The process environment takes precedence over `.env`. Additional optional settings are:

| Variable | Default | Purpose |
|---|---|---|
| `CHATGPT_CLIENT_DB` | `prompts.db` | Path to local SQLite history |
| `OPENAI_STORE_RESPONSES` | `false` | Allow OpenAI-side response storage |
| `OPENAI_BASE_URL` | SDK default | Custom OpenAI-compatible base URL |
| `OPENAI_TIMEOUT_SECONDS` | `120` | Per-request SDK timeout |
| `OPENAI_MAX_RETRIES` | `2` | Bounded SDK retries with exponential backoff |
| `OPENAI_ORGANIZATION` | — | Optional organization identifier |
| `OPENAI_PROJECT` | — | Optional project identifier |
| `MODEL` | — | Backward-compatible alias for `OPENAI_MODEL` |

## Usage

```bash
# Ask a question and save the answer locally
chatgpt-client ask "How much is the fish?"

# Override the configured model for one request
chatgpt-client ask "Explain SQLite WAL mode" --model gpt-5.6-sol

# List history or show one full response
chatgpt-client show
chatgpt-client show 1

# Search both prompts and responses
chatgpt-client search "SQLite"

# Extract code only from matching responses
chatgpt-client search "SQLite" --code-only

# Delete local history
chatgpt-client clear --yes
```

You can also run `python -m chatgpt_client`. The original entry point remains available:

```bash
python chatgpt.py --action ask --query "How much is the fish?"
python chatgpt.py --action show --id 1
python chatgpt.py --action search --query "fish"
```

Use `--database PATH` or `--env-file PATH` before a modern subcommand to override those paths.

## Development

The test suite uses the standard library and never calls the live API:

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
mypy
python -m build
```

Pytest runs with branch coverage and fails below 95%. The suite uses shared fixtures and fake SDK
adapters; it never calls the live OpenAI API.

## Architecture

| Module | Responsibility |
|---|---|
| `config.py` | `.env` parsing and immutable settings |
| `api.py` | Official SDK / Responses API adapter |
| `application.py` | Use cases and dependency inversion |
| `repository.py` | SQLite schema migration and prompt persistence |
| `formatting.py` | Tables and code extraction |
| `cli.py` | Argument parsing and application orchestration |

CI tests Python 3.11, 3.12, and 3.13, then runs Ruff, mypy, coverage, and package builds.
