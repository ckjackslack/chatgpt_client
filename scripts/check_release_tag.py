from __future__ import annotations

import argparse

from chatgpt_client import __version__


def expected_release_tag() -> str:
    return f"v{__version__}"


def validate_release_tag(tag: str) -> None:
    expected = expected_release_tag()
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match package version {expected!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    args = parser.parse_args()
    try:
        validate_release_tag(args.tag)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
