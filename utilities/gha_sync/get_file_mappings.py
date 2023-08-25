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


def markdown_url(text: str, url: str) -> str:
    """Return a markdown link."""
    return f"[{text}]({url})"


def _process_entry(entry: str | dict[str, str]) -> dict[str, str]:
    if isinstance(entry, str):
        return {entry: entry}

    if isinstance(entry, dict):
        if (REPO_PATH / entry["source"]).is_file():
            return {entry["dest"]: entry["source"]}

        return {
            entry["dest"] + file.name: file.relative_to(REPO_PATH).as_posix()
            for file in (REPO_PATH / entry["source"]).rglob("*")
            if file.name not in entry.get("exclude", "").strip().split("\n")
        }

    raise TypeError(f"Invalid entry type: {type(entry)}")  # noqa: TRY003


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

        REPO_FILE_MAPPINGS[repo].update(group_file_mapping)


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
            REPO_FILE_MAPPINGS[repo_key].update(processed_entry)


def _get_all_destinations() -> list[str]:
    all_destinations = set()

    for mappings in REPO_FILE_MAPPINGS.values():
        all_destinations.update(list(mappings.keys()))

    for file in (REPO_PATH / "gha_sync/workflows").rglob("*"):
        if file.is_file():
            all_destinations.add(f".github/workflows/{file.name}")

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

    readme = generate_readme()

    (REPO_PATH / "README.md").write_text(readme)


if __name__ == "__main__":
    main()
