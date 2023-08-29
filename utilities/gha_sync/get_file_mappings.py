"""Generate a README containing the current file mappings across repositories."""

from __future__ import annotations

from json import dumps
from logging import StreamHandler, getLogger
from pathlib import Path
from sys import stdout
from typing import TypedDict

from yaml import safe_load

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
LOGGER.addHandler(StreamHandler(stdout))

REPO_PATH = Path(__file__).parents[2]
SYNC_CONFIG = Path(__file__).parents[2] / "gha_sync/config.yml"

REPO_FILE_MAPPINGS: dict[str, dict[str, str]] = {}

IGNORED_FILES = (".DS_Store", "config.yml")


class InvalidMappingError(Exception):
    """Raised when an invalid file mapping is found."""

    def __init__(self, mapping: dict[str, str], *, reason: str | None = None) -> None:
        """Initialise the exception."""
        msg = "Invalid file mapping"

        if reason:
            msg += f" ({reason})"

        msg += f": {dumps(mapping, default=str, sort_keys=True)}"

        super().__init__()


def markdown_url(text: str, url: str) -> str:
    """Return a markdown link."""
    return f"[{text}]({url})"


def _process_entry(entry: str | dict[str, str]) -> dict[str, str]:
    if isinstance(entry, str):
        mapping = {entry: entry}
    elif isinstance(entry, dict):
        source = REPO_PATH / entry["source"]
        excluded_files = [
            file for file in entry.get("exclude", "").strip().split("\n") if file
        ]

        if source.is_file():
            if excluded_files:
                raise InvalidMappingError(
                    entry, reason="Cannot exclude files from a single file"
                )

            mapping = {entry["dest"]: entry["source"]}
        elif source.is_dir():
            for efile in excluded_files:
                if not (source / efile).is_file():
                    raise InvalidMappingError(
                        entry, reason=f"Excluded file `{efile}` does not exist"
                    )

            mapping = {
                entry["dest"] + file.name: file.relative_to(REPO_PATH).as_posix()
                for file in source.rglob("*")
                if file.name not in excluded_files
            }
        else:
            raise InvalidMappingError(entry, reason=f"Source `{source}` does not exist")
    else:
        raise InvalidMappingError(entry, reason="Invalid mapping type")

    if any(not (REPO_PATH / source).is_file() for source in mapping.values()):
        raise InvalidMappingError(mapping, reason="One or more sources do not exist")

    return mapping


class GroupMappingTypeDef(TypedDict):
    """Type definition for a group mapping."""

    files: list[str]
    repos: str


def process_group_mapping(group_mapping: GroupMappingTypeDef) -> None:
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


def generate_mappings() -> None:
    """Generate the file mappings."""
    config_data = safe_load(SYNC_CONFIG.read_text())

    for group in config_data.pop("group", []):
        process_group_mapping(group)

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


def _get_all_destinations() -> list[str]:
    all_destinations = set()

    for mappings in REPO_FILE_MAPPINGS.values():
        all_destinations.update(list(mappings.keys()))

    for file in (REPO_PATH / "gha_sync/workflows").rglob("*"):
        if file.is_file():
            all_destinations.add(
                f".github/workflows/{file.name.replace('.template.', '.')}"
            )

    return sorted(all_destinations)


def generate_single_table() -> str:
    """Generate a single table containing all the file mappings."""
    all_repos = sorted(REPO_FILE_MAPPINGS.keys())

    readme_contents_structure = "## All Mappings\n\n"

    readme_contents_structure += "| Destination |"
    for repo in all_repos:
        readme_contents_structure += f" {markdown_url(repo.removeprefix('worgarside/'), f'https://github.com/{repo}')} |"  # noqa: E501

    readme_contents_structure += "\n|-------------|"

    for _ in all_repos:
        readme_contents_structure += "--------|"

    readme_contents_structure += "\n"

    for dest in _get_all_destinations():
        readme_contents_structure += f"| **{dest}** |"
        for repo in all_repos:
            if (repo_dest := REPO_FILE_MAPPINGS[repo].get(dest)) is not None:
                readme_contents_structure += f" {markdown_url(repo_dest, repo_dest)} |"
            else:
                readme_contents_structure += " |"

        readme_contents_structure += "\n"

    return readme_contents_structure


def generate_readme() -> str:
    """Generate a README containing the current file mappings across repositories."""

    readme_contents_structure = "# GitHub Config Files\n\n"
    readme_contents_structure += "## Repository File Mappings\n\n"

    for repo, mappings in sorted(REPO_FILE_MAPPINGS.items()):
        repo_url = f"https://github.com/{repo}"

        readme_contents_structure += (
            f"### {markdown_url(repo.removeprefix('worgarside/'), repo_url)}\n\n"
        )
        readme_contents_structure += "<details>\n<summary>Mapping Table</summary>\n\n"
        readme_contents_structure += "| Source | Destination |\n"
        readme_contents_structure += "|--------|-------------|\n"
        for dest, source in sorted(mappings.items(), key=lambda x: x[1]):
            readme_contents_structure += f"| {markdown_url(source, source)} | {markdown_url(dest, repo_url + '/' + dest)} |\n"  # noqa: E501
        readme_contents_structure += "</details>\n"
        readme_contents_structure += "\n"

    readme_contents_structure += generate_single_table()

    return readme_contents_structure.rstrip() + "\n"


def main() -> None:
    """Generate a README containing the current file mappings across repositories."""

    generate_mappings()

    all_used_sources = set()

    for mappings in REPO_FILE_MAPPINGS.values():
        all_used_sources.update(list(mappings.values()))

    for file in (REPO_PATH / "gha_sync/").rglob("*"):
        if (
            file.is_file()
            and file.name not in IGNORED_FILES
            and file.relative_to(REPO_PATH).as_posix() not in all_used_sources
        ):
            raise RuntimeError(  # noqa: TRY003
                f"Unused file: {file.relative_to(REPO_PATH).as_posix()}"
            )

    readme = generate_readme()

    (REPO_PATH / "README.md").write_text(readme)


if __name__ == "__main__":
    main()
