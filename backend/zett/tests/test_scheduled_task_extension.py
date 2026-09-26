"""Agent tools for scheduled-task management."""

import json
from collections.abc import AsyncIterator

from zett_agent import (
    Agent,
    AgentRunConfig,
    AssistantMessage,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolMessage,
)

from zett.agent.extensions import ScheduledTaskExtension
from zett.infra.persistence.dao import provider_storage, scheduled_task_storage
from zett.schemas import ProviderType, ProviderWrite


def _tool_payload(request: ModelRequest) -> dict[str, object]:
    """Decode the latest successful object result from a model request."""
    message = request.messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.success
    payload = json.loads(message.content)
    assert isinstance(payload, dict)
    return payload


def _tool_items(request: ModelRequest) -> list[dict[str, object]]:
    """Decode the latest successful list result from a model request."""
    message = request.messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.success
    payload = json.loads(message.content)
    assert isinstance(payload, list)
    return payload


class ScheduledTaskManagementModel:
    """Exercise create, read, update, and disable in one Agent run."""

    def __init__(self, provider_id: str) -> None:
        self.step = 0
        self.task_id: str | None = None
        self.provider_id = provider_id

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        names = {definition.name for definition in request.tools}
        assert names == {
            "create_scheduled_task",
            "list_scheduled_tasks",
            "list_providers",
            "get_scheduled_task",
            "update_scheduled_task",
            "disable_scheduled_task",
        }
        assert "delete_scheduled_task" not in names

        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "create",
                            "create_scheduled_task",
                            {
                                "task": {
                                    "name": "Daily review",
                                    "schedule": {"expression": "0 9 * * *", "timezone": "Asia/Shanghai"},
                                    "provider_id": self.provider_id,
                                    "message": "Review yesterday's notes.",
                                },
                            },
                        ),
                    )
                )
            case 1:
                created = _tool_payload(request)
                self.task_id = str(created["id"])
                assert created["enabled"] is True
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "update",
                            "update_scheduled_task",
                            {
                                "task_id": self.task_id,
                                "patch": {"name": "Morning review", "message": "Summarize yesterday."},
                            },
                        ),
                    )
                )
            case 2:
                updated = _tool_payload(request)
                assert updated["name"] == "Morning review"
                assert updated["action"]["payload"]["message"] == "Summarize yesterday."
                message = AssistantMessage(tool_calls=(ToolCall("list", "list_scheduled_tasks", {"enabled": True}),))
            case 3:
                listed = _tool_items(request)
                assert [item["id"] for item in listed] == [self.task_id]
                message = AssistantMessage(
                    tool_calls=(ToolCall("get", "get_scheduled_task", {"task_id": self.task_id}),)
                )
            case 4:
                fetched = _tool_payload(request)
                assert fetched["name"] == "Morning review"
                message = AssistantMessage(
                    tool_calls=(ToolCall("disable", "disable_scheduled_task", {"task_id": self.task_id}),)
                )
            case 5:
                disabled = _tool_payload(request)
                assert disabled["enabled"] is False
                message = AssistantMessage(content="Scheduled task lifecycle complete.")
            case _:
                raise AssertionError("Unexpected scheduled-task model step")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_scheduled_task_tools_manage_without_exposing_physical_delete() -> None:
    provider = await provider_storage.create(
        ProviderWrite(
            name="Scheduled provider",
            provider=ProviderType.OPENAI_COMPATIBLE,
            model="test-model",
        )
    )
    model = ScheduledTaskManagementModel(provider.id)
    agent = await Agent.create(
        model,
        config=AgentRunConfig(session_id="scheduled-task-tools"),
        extensions=[ScheduledTaskExtension()],
    )

    result = await agent.run("Create, inspect, update, and disable a scheduled task")

    assert result.content == "Scheduled task lifecycle complete."
    assert model.step == 6
    assert model.task_id is not None
    task = await scheduled_task_storage.get(model.task_id)
    assert task is not None
    assert task.name == "Morning review"
    assert task.enabled is False
    assert task.action.payload["message"] == "Summarize yesterday."


async def test_list_providers_offers_only_enabled_choices_and_pages() -> None:
    """A scheduled task needs a provider id, and the model chooses how many to read."""
    enabled = await provider_storage.create(
        ProviderWrite(name="Live", provider=ProviderType.OPENAI_COMPATIBLE, model="live-model")
    )
    second = await provider_storage.create(
        ProviderWrite(name="Second", provider=ProviderType.OPENAI_COMPATIBLE, model="second-model")
    )
    await provider_storage.create(
        ProviderWrite(name="Paused", provider=ProviderType.DEEPSEEK, model="paused-model", enabled=False)
    )

    class ProviderLookupModel:
        """Ask for the provider list, then finish."""

        def __init__(self) -> None:
            self.step = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            if self.step == 0:
                message = AssistantMessage(tool_calls=(ToolCall("providers", "list_providers", {"limit": 50}),))
            elif self.step == 1:
                found = _tool_items(request)
                assert {item["name"] for item in found} == {"Live", "Second"}
                assert found[0]["id"] == enabled.id
                assert found[0]["model"] == "live-model"
                # A provider row never leaks its endpoint or credentials into a prompt.
                assert set(found[0]) == {"id", "name", "provider", "model"}
                message = AssistantMessage(
                    tool_calls=(ToolCall("providers-page", "list_providers", {"limit": 1, "offset": 1}),)
                )
            else:
                page = _tool_items(request)
                # The model owns the window: one row here, starting at the second provider.
                assert [item["id"] for item in page] == [second.id]
                message = AssistantMessage(content="Provider list read.")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = await Agent.create(
        ProviderLookupModel(),
        config=AgentRunConfig(session_id="provider-lookup"),
        extensions=[ScheduledTaskExtension()],
    )

    assert (await agent.run("Which provider should the task use?")).content == "Provider list read."
