# pylint: disable=abstract-method
"""Map dependencies between GitHub Actions Workflows and their triggers."""
from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from collections.abc import Generator
from copy import deepcopy
from enum import StrEnum, auto
from functools import total_ordering
from itertools import count, product
from json import dumps
from logging import StreamHandler, getLogger
from pathlib import Path
from string import ascii_uppercase
from sys import stdout
from typing import Any, ClassVar, Literal

from common import REPO_FILE_MAPPINGS, REPO_NAME, REPO_PATH
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
)
from yaml import safe_load

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
LOGGER.addHandler(StreamHandler(stdout))


def mermaid(obj: Any) -> str:
    """Return a mermaid representation of the given object."""
    try:
        return obj.__mermaid__()  # type: ignore[no-any-return]
    except AttributeError:
        return str(obj)


class TriggerType(StrEnum):
    """TriggerType types for GitHub Actions Workflows."""

    _UNDEFINED = "<UNDEFINED>"

    PULL_REQUEST = auto()
    PUSH = auto()
    WORKFLOW_CALL = auto()
    WORKFLOW_DISPATCH = auto()


_mermaid_entity_ids = (
    "".join(letters) for n in count(1) for letters in product(ascii_uppercase, repeat=n)
)


class MermaidEntity(BaseModel):
    """Base class for mermaid entities."""

    ENTITIES: ClassVar[dict[str, MermaidEntity]] = {}

    entity_id: str = Field(default_factory=lambda: next(_mermaid_entity_ids))
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    @classmethod
    def by_entity_id(cls, /, entity_id: str) -> MermaidEntity:
        """Return the entity with the given entity_id."""
        return cls.ENTITIES[entity_id]

    def model_post_init(self, _: Any) -> None:
        """Add the entity to the ENTITIES dict."""
        self.ENTITIES[self.entity_id] = self

    def __mermaid__(self) -> str:
        """Return a mermaid representation of the entity."""
        raise NotImplementedError(self.__class__.__name__ + ".__mermaid__")


@total_ordering
class Trigger(MermaidEntity):
    """Trigger for a GitHub Actions Workflow."""

    # pylint: disable=protected-access
    trigger_type: TriggerType = TriggerType._UNDEFINED

    branches: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("branches", "paths", "tags", "types")
    @classmethod
    def sort_lists(cls, values: list[str]) -> list[str]:
        """Sort the given value lists.

        Ensures different list orders don't result in disparate entities.
        """
        return sorted(values)

    def __hash__(self) -> int:
        """Return a hash of the entity."""
        return hash(
            dumps(
                self.model_dump(
                    exclude_none=True,
                    exclude_defaults=True,
                    exclude_unset=True,
                    exclude={"inputs", "outputs"},
                ),
                sort_keys=True,
            ),
        )

    def __eq__(self, __value: object) -> bool:
        """Return whether the given object is equal to this object."""
        if not isinstance(__value, Trigger):
            return NotImplemented

        return self.model_dump(
            exclude_none=True,
            exclude_defaults=True,
            exclude_unset=True,
            exclude={"inputs", "outputs"},
        ) == __value.model_dump(
            exclude_none=True,
            exclude_defaults=True,
            exclude_unset=True,
            exclude={"inputs", "outputs"},
        )

    def __lt__(self, __value: Trigger) -> bool:
        """Sort by trigger_type, branches, paths, tags, types."""
        if not isinstance(__value, Trigger):
            return NotImplemented

        return (
            self.trigger_type,
            self.branches,
            self.paths,
            self.tags,
            self.types,
        ) < (
            __value.trigger_type,
            __value.branches,
            __value.paths,
            __value.tags,
            __value.types,
        )

    def __mermaid__(self) -> str:
        """Return a mermaid representation of the entity."""
        mermaid_str = self.entity_id + '{{"' + self.trigger_type.name.replace("_", " ")

        if not any((self.branches, self.paths, self.tags, self.types)):
            return mermaid_str + '"}}'

        mermaid_str += "\n"

        if self.branches:
            mermaid_str += "Branches: " + ", ".join(self.branches) + "\n"

        if self.paths:
            mermaid_str += "Paths: " + ", ".join(self.paths) + "\n"

        if self.tags:
            mermaid_str += "Tags: " + ", ".join(self.tags) + "\n"

        if self.types:
            mermaid_str += "Types: " + ", ".join(self.types) + "\n"

        return mermaid_str + '"}}'


class Step(MermaidEntity):
    """Step for a GitHub Actions Workflow."""

    name: str
    uses: str
    with_: dict[str, Any]
    if_: str = Field(alias="if")


class Job(MermaidEntity):
    """Job for a GitHub Actions Workflow."""

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


class Concurrency(MermaidEntity):
    """Concurrency config for a GitHub Actions Workflow."""

    group: str
    cancel_in_progress: bool = Field(alias="cancel-in-progress")


@total_ordering
class Workflow(MermaidEntity):
    """GitHub Actions Workflow."""

    INSTANCES: ClassVar[dict[Path, Workflow]] = {}

    local_path: Path = Field(exclude=True)

    name: str
    run_name: str | None = Field(None, alias="run-name")
    on: dict[TriggerType, Trigger]
    permissions: dict[str, str] | None = None
    env: dict[str, float | str] | None = None
    defaults: dict[str, str] | None = None
    concurrency: str | Concurrency | None = None
    jobs: OrderedDict[str, Job]

    @field_validator("on", mode="before")
    @classmethod
    def add_trigger_types(
        cls,
        on: dict[str, dict[str, str] | None],
    ) -> dict[str, dict[str, str]]:
        """Add the trigger type to the trigger data."""
        on_typed = {}

        for trigger_type in on:
            if isinstance(trigger := on[trigger_type], dict):
                trigger["trigger_type"] = trigger_type
            else:
                trigger = {"trigger_type": trigger_type}

            on_typed[trigger_type] = trigger

        return on_typed

    @classmethod
    def by_reference(cls, /, reference: str) -> Workflow:
        """Return the workflow with the given reference."""
        reference = reference.split("@")[0]

        if reference.startswith(REPO_NAME + "/"):
            return cls.import_file(REPO_PATH / reference.removeprefix(REPO_NAME + "/"))

        if reference.startswith("./"):
            return cls.import_file(REPO_PATH / reference)

        raise ValueError(reference)

    @classmethod
    def import_file(cls, /, f: Path, *, force_parse: bool = False) -> Workflow:
        """Import the workflow from the given file.

        Args:
            f (Path): The file to import the workflow from.
            force_parse (bool, optional): Whether to force parsing the file. Defaults to False.

        Returns:
            Workflow: The workflow imported from the file.
        """
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
            LOGGER.exception("Error parsing %s", f.as_posix())
            raise

        return cls.INSTANCES[rel_path]

    @computed_field  # type: ignore[misc]
    @property
    def reusable_workflows(self) -> list[Workflow]:
        """Return the reusable workflows used by this workflow."""
        return sorted(
            ReusableWorkflow.by_reference(job.uses)
            for job in self.jobs.values()
            if job.uses is not None
        )

    @computed_field  # type: ignore[misc]
    @property
    def calling_workflows(self) -> list[Workflow]:
        """Return the workflows that call this workflow."""
        return sorted(
            workflow
            for workflow in Workflow.INSTANCES.values()
            if self in workflow.reusable_workflows
        )

    @property
    def real_path(self) -> Path:
        """Return the real path of the workflow."""
        return NotImplemented

    @computed_field  # type: ignore[misc]
    @property
    def rel_path(self) -> Path:
        """Return the path of the workflow relative to the GHCF repo."""
        return self.local_path.relative_to(REPO_PATH)

    def __eq__(self, o: object) -> bool:
        """Return whether the given object is equal to this object."""
        if not isinstance(o, Workflow):
            return NotImplemented

        return self.real_path == o.real_path

    def __lt__(self, o: Workflow) -> bool:
        """Sort by real_path."""
        return self.real_path < o.real_path

    def __hash__(self) -> int:
        """Return a hash of the entity."""
        return hash(self.real_path)


class PatriarchWorkflow(Workflow):
    """A GitHub Actions Workflow which is synced to another repo."""

    @computed_field  # type: ignore[misc]
    @property
    def real_path(self) -> Path:
        """Return the real path of the workflow."""
        for repo_mappings in REPO_FILE_MAPPINGS.values():
            for dest, source in repo_mappings.items():
                if self.rel_path.as_posix() == source:
                    return Path(dest)

        raise RuntimeError(  # noqa: TRY003
            f"Could not find real path for {self.rel_path.as_posix()}",
        )

    def __mermaid__(self) -> str:
        """Return a mermaid representation of the entity."""
        return self.entity_id + '("' + self.name + '")'


class ReusableWorkflow(Workflow):
    """A reusable GitHub Actions Workflow, stored in the GHCF repo."""

    @computed_field  # type: ignore[misc]
    @property
    def real_path(self) -> Path:
        """Return the real path of the workflow."""
        return self.rel_path

    def __mermaid__(self) -> str:
        """Return a mermaid representation of the entity."""
        if match := re.fullmatch(r"^\"(.+)\" Runner$", self.name):
            return self.entity_id + '[["' + match.group(1) + '"]]'

        raise ValueError(self.name)


def _get_workflow_dependencies() -> list[tuple[Workflow, Workflow]]:
    for file in sorted((REPO_PATH / ".github/workflows/").rglob("__*.yml")):
        ReusableWorkflow.import_file(file)

    for file in sorted((REPO_PATH / "gha_sync/workflows/").rglob("*.yml")):
        PatriarchWorkflow.import_file(file)

    dependency_tuples = set()

    workflows: dict[int, str] = {}

    for workflow in Workflow.INSTANCES.values():
        if actual_entity_id := workflows.get(hash(workflow)):
            workflow.entity_id = actual_entity_id
        else:
            workflows[hash(workflow)] = workflow.entity_id

        for reusable_workflow in workflow.reusable_workflows:
            if actual_reusable_entity_id := workflows.get(hash(reusable_workflow)):
                reusable_workflow.entity_id = actual_reusable_entity_id
            else:
                workflows[hash(reusable_workflow)] = reusable_workflow.entity_id

            dependency_tuples.add((workflow, reusable_workflow))

        for calling_workflow in workflow.calling_workflows:
            if actual_calling_entity_id := workflows.get(hash(calling_workflow)):
                calling_workflow.entity_id = actual_calling_entity_id
            else:
                workflows[hash(calling_workflow)] = calling_workflow.entity_id

            dependency_tuples.add((calling_workflow, workflow))

    return sorted(dependency_tuples)


def _get_workflow_triggers() -> Generator[tuple[Trigger, Workflow], None, None]:
    triggers: dict[int, str] = {}
    for workflow in sorted(Workflow.INSTANCES.values()):
        for trigger in sorted(workflow.on.values()):
            if trigger is None:
                continue

            if actual_entity_id := triggers.get(hash(trigger)):
                trigger.entity_id = actual_entity_id
            else:
                triggers[hash(trigger)] = trigger.entity_id

            yield trigger, workflow


@total_ordering
class Relationship:
    """Relationship between two entities."""

    def __init__(self, start: MermaidEntity, end: MermaidEntity):
        """Initialise the relationship."""
        self.start = start
        self.end = end

        self.label = {
            ReusableWorkflow: "calls",
            Trigger: "triggers",
            Workflow: "invokes",
        }.get(type(start), "invokes")

    @classmethod
    def topological_sort(
        cls,
        relationships: list[Relationship],
        entity_graph: defaultdict[str, set[str]],
    ) -> tuple[Relationship, ...]:
        """Perform a topological sort on the given relationships.

        Args:
            relationships (list): The relationships to sort.
            entity_graph (defaultdict): The graph of entities.
        """
        visited = set()
        stack = []

        def dfs(node: str) -> None:
            visited.add(node)
            for neighbor in sorted(entity_graph[node], reverse=True):
                if neighbor not in visited:
                    dfs(neighbor)
            stack.append(node)

        # Perform DFS
        for node in sorted(entity_graph.keys()):
            if node not in visited:
                dfs(node)

        # Extract the sorted relationships based on the stack
        sorted_relationships = []
        for entity_id in stack:
            for rel in relationships:
                if rel.start.entity_id == entity_id:
                    sorted_relationships.append(rel)

        return tuple(sorted_relationships)

    def __eq__(self, other: Any) -> bool:
        """Return whether the given object is equal to this object."""
        if not isinstance(other, Relationship):
            return False

        return (self.label, self.end.entity_id, self.start.entity_id) == (
            other.label,
            other.end.entity_id,
            other.start.entity_id,
        )

    def __hash__(self) -> int:
        """Return a hash of the entity."""
        return hash((self.start.entity_id, self.end.entity_id, self.label))

    def __lt__(self, other: Any) -> bool:
        """Sort by relationship type, end.entity_id, start.entity_id.

        Sorting rules are:
            - 'triggers' comes first
            - end.entity_id is sorted Z-A
            - start.entity_id is sorted A-Z
        """
        if not isinstance(other, Relationship):
            return NotImplemented

        if self.label != other.label:
            return self.label != "triggers"  # 'triggers' comes first, all else equal

        if self.end.entity_id != other.end.entity_id:
            return self.end.entity_id < other.end.entity_id

        return self.start.entity_id < other.start.entity_id

    def __str__(self) -> str:
        """Return a string representation of the relationship."""
        return f"{self.start.entity_id}-->{self.end.entity_id}"


def group_relationships(
    relationships: list[Relationship],
) -> list[tuple[Relationship, ...]]:
    """Group the given relationships by their connected components.

    Args:
        relationships (list): The relationships to group.

    Returns:
        list: A list of tuples of relationships, grouped by their connected components.
    """
    entity_graph = defaultdict(set)
    for rel in relationships:
        entity_graph[rel.start.entity_id].add(rel.end.entity_id)
        entity_graph[rel.end.entity_id].add(rel.start.entity_id)

    visited = set()
    relationship_groups = []

    def dfs(node: str, component: list[str]) -> None:
        """Perform a DFS on the graph, adding the nodes to the component.

        Args:
            node (str): The node to start the DFS from.
            component (list): The component to add the nodes to.
        """
        visited.add(node)
        for neighbor in sorted(entity_graph[node]):
            if neighbor not in visited:
                dfs(neighbor, component)
        component.append(node)

    for _rel_node in sorted(entity_graph.keys()):
        if _rel_node not in visited:
            _rel_grp: list[str] = []
            dfs(_rel_node, _rel_grp)

            # Convert component to a tuple of Relationships
            component_rels = sorted(
                {
                    rel
                    for rel in relationships
                    if rel.start.entity_id in _rel_grp and rel.end.entity_id in _rel_grp
                },
            )
            relationship_groups.append(
                Relationship.topological_sort(component_rels, deepcopy(entity_graph)),
            )

    return sorted(relationship_groups)


def generate_mermaid_chart(*, use_subgraphs: bool = False) -> str:
    """Generate a mermaid chart of the workflow dependencies."""
    relationships = set()
    displayed_entities = set()

    for caller, callee in _get_workflow_dependencies():
        relationships.add(Relationship(caller, callee))

        displayed_entities.add(caller.entity_id)
        displayed_entities.add(callee.entity_id)

    for trigger, workflow in _get_workflow_triggers():
        if trigger.trigger_type in (
            TriggerType.WORKFLOW_CALL,
            TriggerType.WORKFLOW_DISPATCH,
        ):
            continue

        relationships.add(Relationship(trigger, workflow))

        displayed_entities.add(trigger.entity_id)
        displayed_entities.add(workflow.entity_id)

    if use_subgraphs:
        graph_markup = "flowchart LR\n"

        for grp in group_relationships(sorted(relationships)):
            subgraph_id = next(_mermaid_entity_ids)

            graph_markup += f'subgraph {subgraph_id}[" "]\ndirection LR\n'
            graph_markup += "\n".join(map(mermaid, grp))
            graph_markup += "\nend\n"

        graph_markup += "\n".join(
            mermaid(MermaidEntity.by_entity_id(e)) for e in sorted(displayed_entities)
        )

        return "## Workflow Dependencies\n\n```mermaid\n" + graph_markup + "\n```"

    content = "## Workflow Dependencies\n\n"

    for grp in group_relationships(sorted(relationships)):
        group_entities = set()
        for rel in grp:
            group_entities.add(rel.start.entity_id)
            group_entities.add(rel.end.entity_id)

        content += "```mermaid\nflowchart TB\n"
        content += "\n".join(map(mermaid, grp))
        content += "\n"
        content += "\n".join(
            mermaid(MermaidEntity.by_entity_id(e)) for e in sorted(group_entities)
        )
        content += "\n```\n\n"

    return content
