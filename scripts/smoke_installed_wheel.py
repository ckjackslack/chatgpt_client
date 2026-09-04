from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import venv
from pathlib import Path

from chatgpt_client import __version__


def _run(command: list[str], *, expected: str | None = None) -> None:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    if expected is not None and expected not in result.stdout:
        raise RuntimeError(
            f"expected {expected!r} in stdout from {command!r}; got {result.stdout!r}"
        )


def smoke_test(wheel: Path) -> None:
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError(f"not a wheel file: {wheel}")

    with tempfile.TemporaryDirectory(prefix="chatgpt-client-smoke-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        executable_directory = "Scripts" if os.name == "nt" else "bin"
        python = environment / executable_directory / (
            "python.exe" if os.name == "nt" else "python"
        )
        cli = environment / executable_directory / (
            "chatgpt-client.exe" if os.name == "nt" else "chatgpt-client"
        )
        database = root / "history.db"

        _run([str(python), "-m", "pip", "install", str(wheel.resolve())])
        _run(
            [str(python), "-m", "chatgpt_client", "--version"],
            expected=__version__,
        )
        _run([str(cli), "--version"], expected=__version__)
        _run([str(cli), "--database", str(database), "show"], expected="Empty database.")
        _run(
            [str(cli), "--database", str(database), "search", "missing"],
            expected="No matching rows.",
        )
        _run(
            [str(cli), "--database", str(database), "clear", "--yes"],
            expected="Deleted 0 prompt(s).",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    smoke_test(args.wheel)


if __name__ == "__main__":
    main()
