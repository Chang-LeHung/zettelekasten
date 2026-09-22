"""Agent tools for durable scheduled-task management."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from zett_agent import AgentExtension, AgentRunContext, ReasoningEffort, tool

from ...application.scheduled_tasks import scheduled_task_service
from ...schemas import (
    AGENT_PROMPT_ACTION_KIND,
    AgentPromptAction,
    CronSchedule,
    ScheduledTaskAction,
    ScheduledTaskCreate,
    ScheduledTaskEntity,
    ScheduledTaskListOptions,
)


class ScheduledTaskDraft(BaseModel):
    """Complete model-authored payload for one new Agent prompt schedule."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200, description="Short user-facing task name")
    schedule: CronSchedule = Field(description="Cron expression and IANA timezone")
    provider_id: str = Field(min_length=1, max_length=36, description="Provider used by the scheduled run")
    message: str = Field(min_length=1, max_length=100_000, description="Prompt sent in a fresh session")
    reasoning_effort: ReasoningEffort = Field(
        default=ReasoningEffort.MEDIUM,
        description="Reasoning effort for the scheduled Agent run",
    )
    enabled: bool = Field(default=True, description="Whether the task should run immediately after creation")
    timeout_seconds: int = Field(default=600, ge=1, le=86_400, description="Maximum runtime in seconds")


class ScheduledTaskPatch(BaseModel):
    """Partial replacement for one scheduled task; omitted fields stay unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    schedule: CronSchedule | None = None
    provider_id: str | None = Field(default=None, min_length=1, max_length=36)
    message: str | None = Field(default=None, min_length=1, max_length=100_000)
    reasoning_effort: ReasoningEffort | None = None
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=86_400)

    @model_validator(mode="after")
    def require_change(self) -> Self:
        """Reject an empty patch so updates always express a real intent."""
        if not self.model_fields_set:
            raise ValueError("At least one scheduled-task field must be supplied")
        return self


def _agent_action(
    *,
    provider_id: str,
    message: str,
    reasoning_effort: ReasoningEffort,
) -> ScheduledTaskAction:
    """Build the validated action carried by one scheduled Agent prompt."""
    validated = AgentPromptAction(
        provider_id=provider_id,
        message=message,
        reasoning_effort=reasoning_effort.value,
    )
    return ScheduledTaskAction(
        kind=AGENT_PROMPT_ACTION_KIND,
        payload=validated.model_dump(mode="json"),
    )


def _create_from_draft(draft: ScheduledTaskDraft) -> ScheduledTaskCreate:
    """Translate one model-authored draft into the service write model."""
    return ScheduledTaskCreate(
        name=draft.name,
        schedule=draft.schedule,
        action=_agent_action(
            provider_id=draft.provider_id,
            message=draft.message,
            reasoning_effort=draft.reasoning_effort,
        ),
        enabled=draft.enabled,
        timeout_seconds=draft.timeout_seconds,
    )


def _merge_patch(task: ScheduledTaskEntity, patch: ScheduledTaskPatch) -> ScheduledTaskCreate:
    """Merge a partial model patch into the complete task write model."""
    current = AgentPromptAction.model_validate(task.action.payload)
    provider_id = patch.provider_id if patch.provider_id is not None else current.provider_id
    message = patch.message if patch.message is not None else current.message
    reasoning_effort = patch.reasoning_effort or ReasoningEffort(current.reasoning_effort)
    return ScheduledTaskCreate(
        name=patch.name if patch.name is not None else task.name,
        schedule=patch.schedule if patch.schedule is not None else task.schedule,
        action=_agent_action(
            provider_id=provider_id,
            message=message,
            reasoning_effort=reasoning_effort,
        ),
        enabled=patch.enabled if patch.enabled is not None else task.enabled,
        timeout_seconds=patch.timeout_seconds if patch.timeout_seconds is not None else task.timeout_seconds,
        overlap_policy=task.overlap_policy,
    )


class ScheduledTaskExtension(AgentExtension):
    """Expose create, read, update, and disable operations for scheduled tasks."""

    # Do not add an on_state() scheduled-task snapshot. Task definitions are
    # global rather than conversation state, and every mutation stays visible
    # through the tool call and result in the model's context.

    async def on_tool(self, context: AgentRunContext) -> None:
        @tool
        async def create_scheduled_task(task: ScheduledTaskDraft) -> ScheduledTaskEntity:
            """Create one durable Agent prompt schedule.

            Args:
                task: Complete task definition, including Cron schedule and prompt.

            Snippet:
                create_scheduled_task(task={"name": "Daily review", "schedule": {"expression": "0 9 * * *", "timezone": "Asia/Shanghai"}, "provider_id": "...", "message": "Summarize yesterday."})

            Guidelines:
                - Create a task only when the user explicitly asks to schedule recurring work.
                - Preserve the user's exact timezone and confirm ambiguous Cron expressions before creating.
                - The task runs headlessly in a new session; write the prompt as a complete instruction.
            """
            return await scheduled_task_service.create(_create_from_draft(task))

        @tool
        async def list_scheduled_tasks(
            enabled: bool | None = None,
            limit: Annotated[int, Field(ge=1, le=500)] = 100,
            offset: Annotated[int, Field(ge=0)] = 0,
        ) -> list[ScheduledTaskEntity]:
            """List scheduled tasks, optionally filtering by enabled state.

            Args:
                enabled: True for active tasks, False for disabled tasks, or None for all.
                limit: Maximum number of tasks returned.
                offset: Number of tasks skipped.

            Snippet:
                list_scheduled_tasks(enabled=True)

            Guidelines:
                - Inspect existing task IDs before updating or disabling a task.
                - Never infer a task ID after listing; use the exact ID returned.
            """
            return await scheduled_task_service.list(
                ScheduledTaskListOptions(enabled=enabled, limit=limit, offset=offset)
            )

        @tool
        async def get_scheduled_task(task_id: str) -> ScheduledTaskEntity:
            """Return one scheduled task by its stable ID.

            Args:
                task_id: Exact task UUID returned by list_scheduled_tasks.

            Guidelines:
                - Use the exact ID returned by the task tools; never reconstruct or guess it.
                - Read a task before updating when its current prompt or schedule matters.
            """
            task = await scheduled_task_service.get(task_id)
            if task is None:
                raise ValueError(f"Scheduled task not found: {task_id}")
            return task

        @tool
        async def update_scheduled_task(task_id: str, patch: ScheduledTaskPatch) -> ScheduledTaskEntity:
            """Update only the supplied fields of one scheduled task.

            Args:
                task_id: Exact task UUID returned by list_scheduled_tasks.
                patch: Fields to replace; omitted fields stay unchanged.

            Guidelines:
                - Read the task first when the exact current schedule or prompt is needed.
                - Use enabled=false to pause a task.
            """
            current = await scheduled_task_service.get(task_id)
            if current is None:
                raise ValueError(f"Scheduled task not found: {task_id}")
            return await scheduled_task_service.update(task_id, _merge_patch(current, patch))

        @tool
        async def disable_scheduled_task(task_id: str) -> ScheduledTaskEntity:
            """Disable a scheduled task without deleting its definition or history.

            Args:
                task_id: Exact task UUID returned by list_scheduled_tasks.

            Guidelines:
                - This is the destructive-looking operation exposed to the model: it disables only.
                - Do not claim that history or the task definition was deleted.
                - Enable the task again with update_scheduled_task when the user reverses the request.
            """
            current = await scheduled_task_service.get(task_id)
            if current is None:
                raise ValueError(f"Scheduled task not found: {task_id}")
            return await scheduled_task_service.set_enabled(task_id, False)

        for registered in (
            create_scheduled_task,
            list_scheduled_tasks,
            get_scheduled_task,
            update_scheduled_task,
            disable_scheduled_task,
        ):
            context.register_tool(registered)
