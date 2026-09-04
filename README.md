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
| `CHATGPT_CLIENT_DB_TIMEOUT_SECONDS` | `5` | Maximum wait for a SQLite lock |
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
Add `--verbose` before the subcommand to print effective secret-free settings and request IDs to
standard error:

```bash
chatgpt-client --verbose ask "Explain SQLite WAL mode"
```

## Development

The default test suite never calls the live API:

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
mypy
python -m pip_audit --local --skip-editable
python -m build
```

Pytest runs with branch coverage and fails below 95%. Unit tests use shared fixtures and fake SDK
adapters. A single opt-in live contract test is available separately:

```bash
RUN_OPENAI_INTEGRATION_TESTS=1 OPENAI_API_KEY=... pytest \
  -o addopts="--strict-config --strict-markers -ra" \
  -m integration tests/integration
```

This request uses `store=false`, disables retries, and still incurs a small API charge. GitHub's
manual `Live OpenAI integration` workflow runs the same test through a protected environment.

## Architecture

| Module | Responsibility |
|---|---|
| `database.py` | SQLite connections, transactions, pragmas, and migration execution |
| `config.py` | `.env` parsing and immutable settings |
| `api.py` | Official SDK / Responses API adapter |
| `application.py` | Use cases and dependency inversion |
| `repository.py` | Prompt-specific SQL, schema definitions, and row mapping |
| `formatting.py` | Tables and code extraction |
| `diagnostics.py` | Secret-free runtime and request diagnostics |
| `cli.py` | Argument parsing and application orchestration |

CI tests Python 3.11, 3.12, and 3.13, then runs Ruff, mypy, package validation, and an
installed-wheel smoke test. Releases are published from GitHub Releases through PyPI trusted
publishing, provided that the release tag exactly matches the package version (for example,
`v0.3.0rc1`). See [CHANGELOG.md](CHANGELOG.md) for release notes.
