from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from enum import StrEnum, auto
from json import dumps
from logging import StreamHandler, getLogger
from pathlib import Path
from sys import stdout
from typing import Any, ClassVar, Literal

from common import REPO_FILE_MAPPINGS, REPO_NAME, REPO_PATH
from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field
from yaml import safe_load

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
LOGGER.addHandler(StreamHandler(stdout))


class TriggerType(StrEnum):
    """TriggerType types for GitHub Actions Workflows."""

    PULL_REQUEST = auto()
    PUSH = auto()
    WORKFLOW_CALL = auto()
    WORKFLOW_DISPATCH = auto()

    @property
    def real_path(self) -> Path:
        return Path(self.name)


class Trigger(BaseModel):
    branches: list[str] | None = None
    paths: list[str] | None = None
    tags: list[str] | None = None
    types: list[str] | None = None
    tags: list[str] | None = None
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    def __mermaid__(self) -> str:
        return self.model_dump_json(
            exclude_none=True, exclude_defaults=True, exclude_unset=True
        )


class Step(BaseModel):
    name: str
    uses: str
    with_: dict[str, Any]
    if_: str = Field(alias="if")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class Job(BaseModel):
    name: str
    runs_on: str | None = Field(None, alias="runs-on")
    steps: list[dict[str, Any]] | None = None
    uses: str | None = None
    outputs: dict[str, Any] | None = None
    needs: str | list[str] | None = None
    if_: str | None = Field(None, alias="if")
    continue_on_error: bool | None = Field(None, alias="continue-on-error")
    timeout_minutes: int | None = Field(None, alias="timeout-minutes")
    env: dict[str, str] | None = None
    environment: str | None = None
    with_: dict[str, Any] | None = Field(None, alias="with")
    secrets: Literal["inherit"] | dict[str, str] | None = None
    permissions: dict[str, str] | None = None
    strategy: dict[str, Any] | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class Concurrency(BaseModel):
    group: str
    cancel_in_progress: bool = Field(alias="cancel-in-progress")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class Workflow(BaseModel):
    INSTANCES: ClassVar[dict[Path, Workflow]] = {}

    local_path: Path = Field(exclude=True)

    name: str
    run_name: str | None = Field(None, alias="run-name")
    on: dict[TriggerType, Trigger | None]
    permissions: dict[str, str] | None = None
    env: dict[str, float | str] | None = None
    defaults: dict[str, str] | None = None
    concurrency: str | Concurrency | None = None
    jobs: OrderedDict[str, Job]

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    @classmethod
    def by_reference(cls, /, reference: str) -> Workflow:
        reference = reference.split("@")[0]

        if reference.startswith(REPO_NAME + "/"):
            rel_path = REPO_PATH / reference.removeprefix(REPO_NAME + "/")

            return cls.import_file(rel_path)

        if reference.startswith("./"):
            rel_path = REPO_PATH / reference

            return cls.import_file(rel_path)

        raise ValueError(f"Invalid reference: {reference}")

    @classmethod
    def import_file(cls, /, f: Path, force_parse: bool = False) -> Workflow:
        rel_path = f.relative_to(REPO_PATH)

        if not force_parse and rel_path in cls.INSTANCES:
            return cls.INSTANCES[rel_path]

        with f.open("r") as file:
            data = safe_load(file)

        # `on: ...` is parsed as a boolean key
        if trigger := data.pop(True, None):
            data["on"] = trigger

        try:
            cls.INSTANCES[rel_path] = cls(local_path=f, **data)
        except ValidationError:
            LOGGER.error("Error parsing %s", f.as_posix())
            raise

        return cls.INSTANCES[rel_path]

    @computed_field  # type: ignore[misc]
    @property
    def is_reusable_wrapper(self) -> bool:
        if len(self.jobs) == 1:
            job = list(self.jobs.values())[0]

            return job.steps is None and job.uses is not None

        return all(
            job.steps is None and job.uses is not None for job in self.jobs.values()
        )

    @computed_field  # type: ignore[misc]
    @property
    def reusable_workflows(self) -> list[Workflow]:
        return [
            ReusableWorkflow.by_reference(job.uses)
            for job in self.jobs.values()
            if job.uses is not None
        ]

    @computed_field  # type: ignore[misc]
    @property
    def trigger_conditions(self) -> tuple[Trigger, ...]:
        cond = deepcopy(self.on)

        output = []
        for trigger, config in cond.items():
            if isinstance(config, dict):
                config.pop("inputs", None)
                config.pop("outputs", None)

            if not config:
                output.append(
                    {
                        TriggerType.WORKFLOW_CALL: "Reusable Workflow Call",
                        TriggerType.WORKFLOW_DISPATCH: "Manual Run",
                        TriggerType.PULL_REQUEST: "Pull Request: Default",
                        TriggerType.PUSH: "Push: Default",
                    }[trigger]
                )
                continue

            if trigger == TriggerType.PULL_REQUEST:
                string = "Pull Request"
                if config.get("branches"):
                    string += "\\nBranches: " + ", ".join(config["branches"])
                if config.get("paths"):
                    string += "\\nPaths: " + ", ".join(config["paths"])
                if config.get("types"):
                    string += "\\nTypes: " + ", ".join(config["types"])
                output.append(string)
                continue

            output.append(dumps({trigger: config}, sort_keys=True))

        return tuple(output)

    @computed_field
    @property
    def calling_workflows(self) -> list[Workflow]:
        return [
            workflow
            for workflow in Workflow.INSTANCES.values()
            if self in workflow.reusable_workflows
        ]

    @computed_field
    @property
    def real_path(self) -> Path:
        return NotImplemented

    @computed_field
    @property
    def rel_path(self) -> Path:
        return self.local_path.relative_to(REPO_PATH)

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Workflow):
            return NotImplemented

        return self.real_path == o.real_path

    def __hash__(self) -> int:
        return hash(self.real_path)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.real_path.as_posix()!r})"

    def __str__(self) -> str:
        return self.real_path.as_posix()


class PatriarchWorkflow(Workflow):
    @computed_field
    @property
    def real_path(self) -> Path:
        for repo_mappings in REPO_FILE_MAPPINGS.values():
            for dest, source in repo_mappings.items():
                if self.rel_path.as_posix() == source:
                    return Path(dest)

        raise RuntimeError(f"Could not find real path for {self.rel_path.as_posix()}")

    def __str__(self) -> str:
        return "Patriarch Workflow: " + super().__str__()


class ReusableWorkflow(Workflow):
    @computed_field
    @property
    def real_path(self) -> Path:
        return self.rel_path

    def __str__(self) -> str:
        return "Reusable Workflow: " + super().__str__()


def _get_workflow_dependencies() -> list[tuple[Workflow, Workflow]]:
    for file in (REPO_PATH / ".github/workflows/").rglob("__*.yml"):
        ReusableWorkflow.import_file(file)

    for file in (REPO_PATH / "gha_sync/workflows/").rglob("*.yml"):
        PatriarchWorkflow.import_file(file)

    dependency_tuples = set()

    for workflow in Workflow.INSTANCES.values():
        for reusable_workflow in workflow.reusable_workflows:
            dependency_tuples.add((workflow, reusable_workflow))

        for calling_workflow in workflow.calling_workflows:
            dependency_tuples.add((calling_workflow, workflow))

    return list(dependency_tuples)


def _get_workflow_triggers() -> list[tuple[str, Workflow]]:
    triggers = set()
    for workflow in Workflow.INSTANCES.values():
        for trigger in workflow.trigger_conditions:
            triggers.add((trigger, workflow))

    return list(triggers)


def main():
    markup = "graph LR\n"

    dependencies = _get_workflow_dependencies()

    triggers = _get_workflow_triggers()

    # markup += "\n".join(map(lambda x: "-->".join(map(lambda y: y.real_path.as_posix(), x)), dependencies ))
    #
    # print(markup)
    print(dumps(triggers, default=str, indent=2))


if __name__ == "__main__":
    main()
