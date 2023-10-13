from __future__ import annotations

from functools import lru_cache
from json import dumps
from logging import StreamHandler, getLogger
from pathlib import Path
from sys import stdout
from typing import TYPE_CHECKING, Final, TypedDict

from yaml import safe_load

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
LOGGER.addHandler(StreamHandler(stdout))

REPO_NAME: Final[str] = "worgarside/github-config-files"

REPO_PATH = Path(__file__).parents[2]

IGNORED_FILES = (".DS_Store", "config.yml")


REPO_FILE_MAPPINGS: dict[str, dict[str, str]] = {}

SYNC_CONFIG = Path(__file__).parents[2] / "gha_sync/config.yml"


class GroupMappingTypeDef(TypedDict):
    """Type definition for a group mapping."""

    files: list[str]
    repos: str


class InvalidMappingError(Exception):
    """Raised when an invalid file mapping is found."""

    def __init__(self, mapping: dict[str, str], *, reason: str | None = None) -> None:
        """Initialise the exception."""
        msg = "Invalid file mapping"

        if reason:
            msg += f" ({reason})"

        msg += f": {dumps(mapping, default=str, sort_keys=True)}"

        super().__init__(msg)


def markdown_url(text: str, url: str) -> str:
    """Return a markdown link."""
    return f"[{text}]({url})"


@lru_cache(maxsize=4)
def get_all_destinations(ext: str = "*") -> list[str]:
    all_destinations: set[str] = set()

    for mappings in REPO_FILE_MAPPINGS.values():
        if ext.startswith("."):
            all_destinations.update(
                dest for dest in mappings.keys() if dest.endswith(ext)
            )
        else:
            all_destinations.update(list(mappings.keys()))

    for file in (REPO_PATH / "gha_sync/workflows").rglob(ext):
        if file.is_file():
            all_destinations.add(
                f".github/workflows/{file.name.replace('.template.', '.')}"
            )

    return sorted(all_destinations)


def _process_complex_entry(entry: dict[str, str]) -> dict[str, str]:
    source = REPO_PATH / entry["source"]
    excluded_files = [
        file for file in entry.get("exclude", "").strip().split("\n") if file
    ]

    if source.is_file():
        if excluded_files:
            raise InvalidMappingError(
                entry, reason="Cannot exclude files from a single file"
            )

        return {entry["dest"]: entry["source"]}

    if source.is_dir():
        for efile in excluded_files:
            if not (source / efile).is_file():
                raise InvalidMappingError(
                    entry, reason=f"Excluded file `{efile}` does not exist"
                )

        return {
            entry["dest"] + file.name: file.relative_to(REPO_PATH).as_posix()
            for file in source.rglob("*")
            if file.name not in excluded_files
        }

    raise InvalidMappingError(entry, reason=f"Source `{source}` does not exist")


def _process_entry(entry: str | dict[str, str]) -> dict[str, str]:
    if isinstance(entry, str):
        mapping = {entry: entry}
    elif isinstance(entry, dict):
        mapping = _process_complex_entry(entry)
    else:
        raise InvalidMappingError(entry, reason="Invalid mapping type")

    if any(not (REPO_PATH / source).is_file() for source in mapping.values()):
        raise InvalidMappingError(mapping, reason="One or more sources do not exist")

    return mapping


def _process_group_mapping(group_mapping: GroupMappingTypeDef) -> None:
    """Process a group mapping."""
    group_file_mapping = {}

    for file_entry in group_mapping["files"]:
        group_file_mapping.update(_process_entry(file_entry))

    for repo in group_mapping["repos"].strip().split("\n"):
        REPO_FILE_MAPPINGS.setdefault(repo, {})

        LOGGER.debug("Adding group mapping to %s: %r", repo, group_file_mapping)

        for dest, source in group_file_mapping.items():
            if REPO_FILE_MAPPINGS[repo].get(dest) is not None:
                raise InvalidMappingError(
                    group_file_mapping,
                    reason=f"Duplicate destination `{dest}` in group mapping for {repo}",
                )

            REPO_FILE_MAPPINGS[repo][dest] = source


@lru_cache
def _generate_mappings() -> None:
    """Generate the file mappings."""
    if REPO_FILE_MAPPINGS:
        raise RuntimeError("Mappings have already been generated")

    config_data = safe_load(SYNC_CONFIG.read_text())

    for group in config_data.pop("group", []):
        _process_group_mapping(group)

    for repo_key, entries in config_data.items():
        REPO_FILE_MAPPINGS.setdefault(repo_key, {})

        for file_entry in entries:
            if not (processed_entry := _process_entry(file_entry)):
                continue

            LOGGER.debug(
                "Adding mapping to %s: %s",
                repo_key,
                dumps(processed_entry, indent=2, default=sorted, sort_keys=True),
            )

            for dest, source in processed_entry.items():
                if REPO_FILE_MAPPINGS[repo_key].get(dest) is not None:
                    raise InvalidMappingError(
                        processed_entry,
                        reason=f"Duplicate destination `{dest}` in mapping for {repo_key}",
                    )

                REPO_FILE_MAPPINGS[repo_key][dest] = source


if not TYPE_CHECKING:
    _generate_mappings()

__all__ = ["REPO_FILE_MAPPINGS", "REPO_PATH", "get_all_destinations", "markdown_url"]
