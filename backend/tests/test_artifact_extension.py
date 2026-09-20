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

from zett.agent.extensions import ArtifactExtension
from zett.infra.dao import artifact_storage, session_storage
from zett.schemas import AgentArtifactWrite, AgentSessionCreate, ArticleArtifactContent, CardArtifactContent


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
                assert str(_tool_payload(request)["draft_content"]["title"]) == "Rust ownership"
                message = AssistantMessage(
                    tool_calls=(ToolCall("get", "get_artifact", {"artifact_id": self.first_id}),)
                )
            case 3:
                fetched = _tool_payload(request)
                assert fetched["id"] == self.first_id
                assert fetched["content"] is None
                assert fetched["draft_content"]["title"] == "Python process"
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
                assert [item["draft_content"]["title"] for item in matched] == ["Rust ownership"]
                assert matched[0]["draft_content"]["content_preview"] == "Another idea"
                assert matched[0]["draft_content"]["content_truncated"] is False
                assert "raw_content" not in matched[0]
                assert "metadata" not in matched[0]
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "update",
                            "update_artifact",
                            {
                                "artifact_id": self.first_id,
                                # Partial edit: only the body changes.
                                "patch": {"artifact_type": "card", "content": "Updated idea"},
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
                assert latest["content"] is None
                assert latest["draft_content"]["content"] == "Updated idea"
                assert latest["draft_content"]["title"] == "Python process"
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
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    model = ArtifactQueryModel()
    agent = await Agent.create(model, config=AgentRunConfig(session_id=session_id), extensions=[ArtifactExtension()])

    result = await agent.run("Create cards and query them")

    assert result.content == "Artifact queries complete."
    assert model.step == 8
    written = await artifact_storage.list()
    assert len(written) == 2
    # The model proposes drafts only; nothing it wrote is published content.
    assert all(artifact.content is None for artifact in written)
    assert {artifact.draft_content.title for artifact in written if artifact.draft_content} == {
        "Python process",
        "Rust ownership",
    }


async def test_artifact_queries_are_scoped_to_the_owning_session() -> None:
    owner = (await session_storage.create(AgentSessionCreate())).session_id
    other = (await session_storage.create(AgentSessionCreate())).session_id
    secret = await artifact_storage.create(
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
                assert [item["published_content"]["title"] for item in matched] == ["Secret"]
                assert matched[0]["session_id"] == owner
                message = AssistantMessage(content="Global search found the artifact.")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = await Agent.create(
        CrossSessionModel(),
        config=AgentRunConfig(session_id=other),
        extensions=[ArtifactExtension()],
    )
    result = await agent.run("Read the other artifact")

    assert result.content == "Global search found the artifact."
    assert await artifact_storage.get_for_session(owner, secret.id) is not None


async def test_model_drafts_stay_unpublished_until_the_user_saves() -> None:
    """A draft write never becomes content; only the user's save publishes it."""
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    draft = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            draft_content=CardArtifactContent(title="Proposed card", content="Model draft"),
        )
    )

    assert draft.content is None
    assert draft.draft_content is not None
    assert draft.editable_content is not None
    assert draft.editable_content.title == "Proposed card"

    # The model can only propose again; publishing stays a user action.
    revised = await artifact_storage.update(
        draft.id,
        AgentArtifactWrite(
            session_id=session_id,
            content=draft.content,
            draft_content=CardArtifactContent(title="Proposed card", content="Second draft"),
            status=draft.status,
            metadata=draft.metadata,
        ),
    )

    assert revised.content is None
    assert revised.draft_content is not None and revised.draft_content.content == "Second draft"


async def test_artifact_workspace_is_not_reinjected_into_system_context() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    full_content = "Article intro.\n" + ("private body " * 200)
    await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ArticleArtifactContent(title="Private article", content=full_content),
            raw_content="RAW INPUT MUST NOT ENTER CONTEXT",
            metadata={"internal": "METADATA MUST NOT ENTER CONTEXT"},
        )
    )
    requests: list[ModelRequest] = []

    class Model:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            requests.append(request)
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="done")))

    agent = await Agent.create(Model(), config=AgentRunConfig(session_id=session_id), extensions=[ArtifactExtension()])
    await agent.run("Inspect the workspace")

    assert all(
        not (message.role == "system" and "Current Zett conversation workspace previews:" in str(message.content))
        for message in requests[0].messages
    )
