# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0rc1] - 2026-09-03

### Added

- A layered package architecture for CLI, application, configuration, OpenAI API, and SQLite.
- An official OpenAI SDK adapter using the Responses API.
- Versioned SQLite migrations and persisted OpenAI response/request identifiers.
- Secret-free verbose diagnostics, an opt-in live API test, and installed-wheel smoke testing.
- Reusable SQLite connection, transaction, and migration-plan infrastructure.
- Python 3.11–3.13 CI, strict mypy, Ruff, branch coverage, and trusted PyPI publishing.

### Changed

- Replaced the legacy `unittest` suite with pytest fixtures, helpers, and parametrized tests.
- Made destructive history clearing require explicit `--yes` confirmation.
- Improved Unicode search, database lock handling, configuration validation, and API errors.

[Unreleased]: https://github.com/ckjackslack/chatgpt_client/compare/v0.3.0rc1...HEAD
[0.3.0rc1]: https://github.com/ckjackslack/chatgpt_client/releases/tag/v0.3.0rc1
