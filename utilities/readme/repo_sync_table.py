"""Generate a section for the current file mappings across repositories."""

from __future__ import annotations

from common import REPO_FILE_MAPPINGS, get_all_destinations, markdown_url


def generate_overview_table() -> str:
    """Generate a single table containing all the file mappings."""
    all_repos = sorted(REPO_FILE_MAPPINGS.keys())

    readme_contents_structure = "## All Mappings\n\n"

    readme_contents_structure += "| Destination |"
    for repo in all_repos:
        url = markdown_url(
            repo.removeprefix("worgarside/"),
            f"https://github.com/{repo}",
        )
        readme_contents_structure += f" {url} |"

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
    readme_contents_structure = "## Repository File Mappings\n\n"

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
                ),
            )
        details_section += "</details>\n\n"

        header += f"({file_count} files)\n\n"

        readme_contents_structure += header
        readme_contents_structure += details_section

    return readme_contents_structure


def generate_config_mappings() -> str:
    """Generate the file mappings section."""
    return generate_readme() + generate_overview_table() + "\n"
