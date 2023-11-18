"""Cancel stale pending GitHub Actions deployments."""
from __future__ import annotations

from functools import lru_cache
from logging import getLogger
from os import environ

from httpx import Client

GH_TOKEN = environ["GH_TOKEN"]
REPOSITORY_OWNER = environ["REPOSITORY_OWNER"]

CLIENT = Client(
    base_url="https://api.github.com",
    headers={"Authorization": f"token {GH_TOKEN}"},
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")


@lru_cache(maxsize=1)
def get_environments(repo_name: str) -> dict[str, str]:
    """Get a dict of environment names to IDs."""
    res = CLIENT.get(f"/repos/{repo_name}/environments")

    res.raise_for_status()

    return {env["name"]: env["id"] for env in res.json()["environments"]}


def get_deployment_shas(environment: str, repo_name: str) -> tuple[list[str], str]:
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

    return env_deployment_shas, latest_deployment["sha"]


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
    for repo in CLIENT.get("/user/repos").json():
        if repo["owner"]["login"] != REPOSITORY_OWNER:
            continue

        rejected_deployments = reject_stale_pending_deployments(repo["full_name"])

        LOGGER.info(
            "Rejected %s stale pending deployments for %s",
            rejected_deployments,
            repo["full_name"],
        )


if __name__ == "__main__":
    main()
