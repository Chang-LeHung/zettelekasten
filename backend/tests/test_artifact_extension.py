"""End-to-end coverage for model-operated artifact queries."""

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

from zett.agent.extensions import ZettelkastenExtension
from zett.infra.dao import artifact_storage, session_storage
from zett.schemas import AgentArtifactWrite, AgentSessionCreate, CardArtifactContent


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


class ArtifactQueryModel:
    """Create two cards, then fetch and filter them with the query tools."""

    def __init__(self) -> None:
        self.step = 0
        self.first_id: str | None = None

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        names = {definition.name for definition in request.tools}
        assert names == {
            "create_artifact",
            "get_artifact",
            "query_artifacts",
            "update_artifact",
            "save_artifact",
            "delete_artifact",
        }
        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "create-process",
                            "create_artifact",
                            {"content": {"artifact_type": "card", "title": "Python process", "content": "One idea"}},
                        ),
                    )
                )
            case 1:
                created = _tool_payload(request)
                self.first_id = str(created["id"])
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "create-ownership",
                            "create_artifact",
                            {
                                "content": {
                                    "artifact_type": "card",
                                    "title": "Rust ownership",
                                    "content": "Another idea",
                                }
                            },
                        ),
                    )
                )
            case 2:
                assert str(_tool_payload(request)["content"]["title"]) == "Rust ownership"
                message = AssistantMessage(
                    tool_calls=(ToolCall("get", "get_artifact", {"artifact_id": self.first_id}),)
                )
            case 3:
                fetched = _tool_payload(request)
                assert fetched["id"] == self.first_id
                assert fetched["content"]["title"] == "Python process"
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "query",
                            "query_artifacts",
                            {"query": "rust", "artifact_types": ["card"], "limit": 10},
                        ),
                    )
                )
            case 4:
                matched = _tool_items(request)
                assert [item["content"]["title"] for item in matched] == ["Rust ownership"]
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "update",
                            "update_artifact",
                            {
                                "artifact_id": self.first_id,
                                "content": {
                                    "artifact_type": "card",
                                    "title": "Python process",
                                    "content": "Updated idea",
                                },
                            },
                        ),
                    )
                )
            case 5:
                message = AssistantMessage(
                    tool_calls=(ToolCall("get-latest", "get_artifact", {"artifact_id": self.first_id}),)
                )
            case 6:
                latest = _tool_payload(request)
                assert latest["content"]["content"] == "Updated idea"
                assert latest["version"] == 2
                message = AssistantMessage(
                    tool_calls=(ToolCall("query-saved", "query_artifacts", {"statuses": ["saved"]}),)
                )
            case _:
                assert _tool_items(request) == []
                message = AssistantMessage(content="Artifact queries complete.")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_artifact_query_tools_run_complete_session_scoped_lifecycle() -> None:
    session_id = session_storage.create(AgentSessionCreate()).session_id
    model = ArtifactQueryModel()
    agent = await Agent.create(
        model, config=AgentRunConfig(session_id=session_id), extensions=[ZettelkastenExtension()]
    )

    result = await agent.run("Create cards and query them")

    assert result.content == "Artifact queries complete."
    assert model.step == 8
    assert len(artifact_storage.list()) == 2


async def test_artifact_queries_are_scoped_to_the_owning_session() -> None:
    owner = session_storage.create(AgentSessionCreate()).session_id
    other = session_storage.create(AgentSessionCreate()).session_id
    secret = artifact_storage.create(
        AgentArtifactWrite(
            session_id=owner,
            content=CardArtifactContent(artifact_type="card", title="Secret", content="hidden"),
        )
    )

    class CrossSessionModel:
        def __init__(self) -> None:
            self.step = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            if self.step == 0:
                message = AssistantMessage(
                    tool_calls=(ToolCall("cross-get", "get_artifact", {"artifact_id": secret.id}),)
                )
            elif self.step == 1:
                tool_result = request.messages[-1]
                assert isinstance(tool_result, ToolMessage)
                assert not tool_result.success
                assert "hidden" not in tool_result.content
                message = AssistantMessage(
                    tool_calls=(ToolCall("cross-query", "query_artifacts", {"query": "Secret"}),)
                )
            elif self.step == 2:
                tool_result = request.messages[-1]
                assert isinstance(tool_result, ToolMessage)
                assert tool_result.success
                assert json.loads(tool_result.content) == []
                message = AssistantMessage(
                    tool_calls=(ToolCall("global-query", "query_artifacts", {"query": "Secret", "all_sessions": True}),)
                )
            else:
                tool_result = request.messages[-1]
                assert isinstance(tool_result, ToolMessage)
                assert tool_result.success
                matched = json.loads(tool_result.content)
                assert [item["content"]["title"] for item in matched] == ["Secret"]
                assert matched[0]["session_id"] == owner
                message = AssistantMessage(content="Global search found the artifact.")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = await Agent.create(
        CrossSessionModel(),
        config=AgentRunConfig(session_id=other),
        extensions=[ZettelkastenExtension()],
    )
    result = await agent.run("Read the other artifact")

    assert result.content == "Global search found the artifact."
    assert artifact_storage.get_for_session(owner, secret.id) is not None
