"""Pin distributed actions and reusable workflows to the new release."""

from __future__ import annotations

import re
from os import environ
from pathlib import Path
from sys import stdout
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$",
)
ACTION_PIN_PATTERN = re.compile(
    r"(?P<prefix>\buses:\s*[\"']?"
    r"worgarside/github-config-files/\.github/(?:actions|workflows)/[^@\s\"'#]+@)"
    r"[^\s\"'#]+",
)
SYNC_SOURCE_DIRECTORY = Path(__file__).parents[2] / "gha_sync"


def get_release_version(environment: Mapping[str, str]) -> str:
    """Return the valid semantic release version from the environment."""
    version = environment.get("NEW_VERSION", "")
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("NEW_VERSION must contain a valid semantic version")

    return version


def update_action_pins(source_directory: Path, version: str) -> int:
    """Update this repository's action and workflow pins in YAML source files."""
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("version must be a valid semantic version")

    replacement_count = 0
    yaml_files = (*source_directory.rglob("*.yml"), *source_directory.rglob("*.yaml"))

    for yaml_file in yaml_files:
        original_content = yaml_file.read_text()
        updated_content, file_replacement_count = ACTION_PIN_PATTERN.subn(
            rf"\g<prefix>{version}",
            original_content,
        )

        if file_replacement_count:
            yaml_file.write_text(updated_content)
            replacement_count += file_replacement_count

    return replacement_count


def main() -> None:
    """Update release pins using the version supplied by semantic-release."""
    version = get_release_version(environ)
    replacement_count = update_action_pins(SYNC_SOURCE_DIRECTORY, version)
    stdout.write(
        f"Pinned {replacement_count} action/workflow references to {version}\n",
    )


if __name__ == "__main__":
    main()
