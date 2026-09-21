"""Shared action execution contracts for scheduler workers."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ...schemas import JsonValue, ScheduledTaskTrigger


class ActionExecutionStatus(StrEnum):
    """Terminal result returned by a successful executor invocation."""

    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Identity and timing information for one executor invocation."""

    task_id: str
    task_name: str
    run_id: str
    scheduled_for: datetime
    trigger_kind: ScheduledTaskTrigger


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Typed executor outcome stored in the run's output field."""

    status: ActionExecutionStatus = ActionExecutionStatus.SUCCEEDED
    output: dict[str, JsonValue] | None = None


class ActionExecutor(ABC):
    """One action implementation registered by kind."""

    action_kind: str

    @abstractmethod
    def validate_payload(self, payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        """Validate and normalize one persisted action payload."""

    @abstractmethod
    async def execute(
        self,
        context: ExecutionContext,
        payload: Mapping[str, JsonValue],
    ) -> ActionResult:
        """Execute one claimed run."""


class ActionExecutorRegistry:
    """Resolve action kinds without coupling workers to feature code."""

    def __init__(self, executors: tuple[ActionExecutor, ...] = ()) -> None:
        self._executors: dict[str, ActionExecutor] = {}
        for executor in executors:
            self.register(executor)

    def register(self, executor: ActionExecutor) -> None:
        kind = executor.action_kind.strip()
        if not kind:
            raise ValueError("Action executor kind cannot be empty")
        if kind in self._executors:
            raise ValueError(f"Action executor is already registered: {kind}")
        self._executors[kind] = executor

    def get(self, kind: str) -> ActionExecutor | None:
        return self._executors.get(kind)
