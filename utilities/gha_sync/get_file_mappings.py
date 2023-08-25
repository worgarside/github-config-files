"""Generate a README containing the current file mappings across repositories."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from yaml import safe_load

REPO_PATH = Path(__file__).parents[2]
SYNC_CONFIG = Path(__file__).parents[2] / "gha_sync/config.yml"

REPO_FILE_MAPPINGS: dict[str, set[tuple[str, str]]] = {}


def markdown_url(text: str, url: str) -> str:
    """Return a markdown link."""
    return f"[{text}]({url})"


def _process_entry(entry: str | dict[str, str]) -> list[tuple[str, str]]:
    if isinstance(entry, str):
        return [(entry, entry)]

    if isinstance(entry, dict):
        return [
            (
                file.relative_to(REPO_PATH).as_posix(),
                entry["dest"] + file.name,
            )
            for file in (REPO_PATH / entry["source"]).rglob("*")
            if file.relative_to(REPO_PATH).as_posix()
            not in entry.get("exclude", "").strip().split("\n")
        ]

    raise TypeError(f"Invalid entry type: {type(entry)}")  # noqa: TRY003


class GroupMappingTypeDef(TypedDict):
    """Type definition for a group mapping."""

    files: list[str]
    repos: str


def process_group_mapping(group_mapping: GroupMappingTypeDef) -> None:
    """Process a group mapping."""
    group_file_mapping = set()

    for file_entry in group_mapping["files"]:
        group_file_mapping.update(_process_entry(file_entry))

    for repo in group_mapping["repos"].strip().split("\n"):
        REPO_FILE_MAPPINGS.setdefault(repo, set())

        REPO_FILE_MAPPINGS[repo].update(group_file_mapping)


def generate_readme() -> str:
    """Generate a README containing the current file mappings across repositories."""
    config_data = safe_load(SYNC_CONFIG.read_text())

    readme_contents_structure = "# GitHub Config Files\n\n"
    readme_contents_structure += "## Repository File Mappings\n\n"

    for group in config_data.pop("group", []):
        process_group_mapping(group)

    for repo_key, entries in config_data.items():
        REPO_FILE_MAPPINGS.setdefault(repo_key, set())

        for file_entry in entries:
            REPO_FILE_MAPPINGS[repo_key].update(_process_entry(file_entry))

    for repo, mappings in sorted(REPO_FILE_MAPPINGS.items()):
        repo_url = f"https://github.com/{repo}"

        readme_contents_structure += (
            f"### {markdown_url(repo.removeprefix('worgarside/'), repo_url)}\n\n"
        )
        readme_contents_structure += "| Source | Destination |\n"
        readme_contents_structure += "|--------|-------------|\n"
        for source, dest in sorted(mappings, key=lambda x: x[1]):
            readme_contents_structure += f"| {markdown_url(source, source)} | {markdown_url(dest, repo_url + '/' + dest)} |\n"  # noqa: E501
        readme_contents_structure += "\n"

    return readme_contents_structure


def main() -> None:
    """Generate a README containing the current file mappings across repositories."""
    readme = generate_readme()

    (REPO_PATH / "README.md").write_text(readme)


if __name__ == "__main__":
    main()
