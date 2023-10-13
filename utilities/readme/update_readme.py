"""Generate a README containing the current file mappings across repositories."""

from __future__ import annotations

from logging import StreamHandler, getLogger
from sys import stdout

from common import REPO_FILE_MAPPINGS, REPO_PATH, get_all_destinations, markdown_url

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
LOGGER.addHandler(StreamHandler(stdout))


IGNORED_FILES = (".DS_Store", "config.yml")


def generate_overview_table() -> str:
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

    for dest in get_all_destinations():
        readme_contents_structure += f"| **{dest}** |"
        for repo in all_repos:
            if (repo_dest := REPO_FILE_MAPPINGS[repo].get(dest)) is not None:
                readme_contents_structure += f" {markdown_url(repo_dest, repo_dest)} |"
            else:
                readme_contents_structure += " |"

        readme_contents_structure += "\n"

    return readme_contents_structure.rstrip()


def generate_readme() -> str:
    """Generate a README containing the current file mappings across repositories."""

    readme_contents_structure = "# GitHub Config Files\n\n"
    readme_contents_structure += "## Repository File Mappings\n\n"

    for repo, mappings in sorted(REPO_FILE_MAPPINGS.items()):
        repo_url = f"https://github.com/{repo}"

        header = f"### {markdown_url(repo.removeprefix('worgarside/'), repo_url)} "
        file_count = 0

        details_section = "<details>\n<summary>Mapping Table</summary>\n\n"
        details_section += "| Source | Destination |\n"
        details_section += "|--------|-------------|\n"
        for dest, source in sorted(mappings.items(), key=lambda x: x[1]):
            file_count += 1
            details_section += "|".join(
                (
                    "",
                    f" {markdown_url(source, source)} ",
                    f" {markdown_url(dest, repo_url + '/' + dest)} ",
                    "\n",
                )
            )
        details_section += "</details>\n\n"

        header += f"({file_count} files)\n\n"

        readme_contents_structure += header
        readme_contents_structure += details_section

    readme_contents_structure += generate_overview_table()

    return readme_contents_structure + "\n"


def main() -> None:
    """Generate a README containing the current file mappings across repositories."""

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
