"""Cancel stale pending GitHub Actions deployments."""
from __future__ import annotations

from functools import lru_cache
from logging import getLevelNamesMapping, getLogger
from os import environ, getenv
from pathlib import Path

from httpx import Client

GH_TOKEN = environ["GH_TOKEN"]

CLIENT = Client(
    base_url="https://api.github.com",
    headers={"Authorization": f"token {GH_TOKEN}"},
)

LOGGER = getLogger(__name__)
LOGGER.setLevel(environ["LOG_LEVEL"])


def markdown_url(url: str, *, text: str | None = None) -> str:
    """Return a Markdown link."""
    if text is None:
        text = url

    return f"[{text}]({url})"


@lru_cache(maxsize=1)
def repo_name_markdown(repo_name: str, *, path: str | None = None) -> str:
    """Return a Markdown link to the repo."""
    path = "/" + path.strip("/") if path else ""

    return markdown_url(f"https://github.com/{repo_name}{path}", text=repo_name)


@lru_cache(maxsize=1)
def get_environments(repo_name: str) -> dict[str, str]:
    """Get a dict of environment names to IDs."""
    res = CLIENT.get(f"/repos/{repo_name}/environments")

    res.raise_for_status()

    LOGGER.debug(
        "Environments for %s are %s",
        repo_name_markdown(repo_name),
        ", ".join(
            f"`{env['name']}` (`{env['id']}`)" for env in res.json()["environments"]
        ),
    )

    return {env["name"]: env["id"] for env in res.json()["environments"]}


def get_deployment_shas(
    environment: str,
    repo_name: str,
) -> tuple[list[str], str | None]:
    """Get a list of deployment SHAs for the given environment."""
    deployments = CLIENT.get(
        f"repos/{repo_name}/deployments",
        params={"environment": environment, "per_page": 100},
    ).json()

    env_deployment_shas = []
    latest_deployment: dict[str, str] = {}

    for deployment in deployments:
        if deployment["created_at"] > latest_deployment.get("created_at", ""):
            latest_deployment = {
                "sha": deployment["sha"],
                "created_at": deployment["created_at"],
            }

        env_deployment_shas.append(deployment["sha"])

    return env_deployment_shas, latest_deployment.get("sha")


def reject_stale_pending_deployments(repo_name: str) -> int:
    """Reject pending deployments that are stale."""
    workflow_runs = CLIENT.get(
        f"/repos/{repo_name}/actions/runs",
        params={"status": "waiting", "per_page": 100},
    ).json()["workflow_runs"]

    env_deployment_shas = {}
    latest_deployment_shas = []

    for environment in get_environments(repo_name):
        (
            env_deployment_shas[environment],
            latest_env_deployment_sha,
        ) = get_deployment_shas(environment, repo_name)

        if latest_env_deployment_sha is None:
            LOGGER.warning(
                "No deployments found for %s on `%s`",
                repo_name_markdown(repo_name),
                markdown_url(
                    f"https://github.com/{repo_name}/deployments/{environment}",
                    text=environment,
                ),
            )
            continue

        LOGGER.debug(
            "Latest deployment SHA for %s on `%s` is `%s`",
            repo_name_markdown(repo_name),
            markdown_url(
                f"https://github.com/{repo_name}/deployments/{environment}",
                text=environment,
            ),
            latest_env_deployment_sha,
        )

        latest_deployment_shas.append(latest_env_deployment_sha)

    rejection_count = 0

    for run in workflow_runs:
        if run["head_sha"] in latest_deployment_shas:
            continue

        environment_ids = [
            get_environments(repo_name)[env_name]
            for env_name, deployment_shas in env_deployment_shas.items()
            if run["head_sha"] in deployment_shas
        ]

        res = CLIENT.post(
            f'/repos/{repo_name}/actions/runs/{run["id"]}/pending_deployments',
            json={
                "environment_ids": environment_ids,
                "state": "rejected",
                "comment": "Rejected because it's gone stale 😐",
            },
        )

        res.raise_for_status()

        rejection_count += 1

    return rejection_count


def main() -> None:
    """Main function."""
    for repo in CLIENT.get(
        "/user/repos",
        params={"affiliation": "owner", "visibility": "public", "per_page": 100},
    ).json():
        if repo["archived"]:
            continue

        try:
            rejected_deployments = reject_stale_pending_deployments(repo["full_name"])
        except Exception:  # pylint: disable=broad-exception-caught
            LOGGER.exception(
                "Failed to reject stale pending deployments for %s",
                repo_name_markdown(repo["full_name"]),
            )
        else:
            LOGGER.info(
                "Rejected %s stale pending deployments for %s",
                rejected_deployments,
                repo_name_markdown(repo["full_name"]),
            )


if __name__ == "__main__":
    if _step_summary_file := getenv("GITHUB_STEP_SUMMARY"):
        from wg_utilities.loggers import add_file_handler

        add_file_handler(
            LOGGER,
            logfile_path=Path(_step_summary_file),
            level=getLevelNamesMapping()[environ["LOG_LEVEL"]],
        )

    main()
