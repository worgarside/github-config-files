"""Generate a README containing the current file mappings across repositories."""

from __future__ import annotations

from logging import StreamHandler, getLogger
from sys import stdout

from utils.common import REPO_FILE_MAPPINGS, REPO_PATH
from utils.mermaid_chart import generate_mermaid_chart
from utils.repo_sync_table import generate_config_mappings

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
LOGGER.addHandler(StreamHandler(stdout))


IGNORED_FILES = (".DS_Store", "config.yml")


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
            raise RuntimeError(
                f"Unused file: {file.relative_to(REPO_PATH).as_posix()}",
            )

    readme = "# GitHub Config Files\n\n"

    readme += generate_config_mappings()

    readme += generate_mermaid_chart(use_subgraphs=True)

    readme = readme.rstrip() + "\n"

    (REPO_PATH / "README.md").write_text(readme)


if __name__ == "__main__":
    main()
