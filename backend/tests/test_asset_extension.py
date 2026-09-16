"""End-to-end coverage for model-operated session assets."""

import base64
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

from zett.agent import AssetExtension
from zett.infra.dao import session_asset_storage, session_storage
from zett.models import SessionAssetListOptions
from zett.schemas import AgentSessionCreate, SessionAssetCreate


def _tool_payload(request: ModelRequest) -> dict[str, object]:
    """Decode the latest successful tool result from a model request."""
    message = request.messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.success
    payload = json.loads(message.content)
    assert isinstance(payload, dict)
    return payload


class AssetCrudModel:
    """Drive a complete text-asset lifecycle using only model tool calls."""

    def __init__(self) -> None:
        self.step = 0
        self.asset_id: str | None = None
        self.observed: list[dict[str, object]] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        names = {definition.name for definition in request.tools}
        assert names == {"create_asset", "get_asset", "update_asset", "delete_asset", "list_assets"}
        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "create",
                            "create_asset",
                            {"asset": {"asset_type": "text", "name": "idea.md", "text_content": "First"}},
                        ),
                    )
                )
            case 1:
                created = _tool_payload(request)
                self.observed.append(created)
                self.asset_id = str(created["id"])
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "update",
                            "update_asset",
                            {
                                "asset_id": self.asset_id,
                                "asset": {
                                    "asset_type": "text",
                                    "name": "idea.md",
                                    "text_content": "Revised",
                                    "metadata": {"topic": "agents"},
                                },
                            },
                        ),
                    )
                )
            case 2:
                self.observed.append(_tool_payload(request))
                message = AssistantMessage(tool_calls=(ToolCall("get", "get_asset", {"asset_id": self.asset_id}),))
            case 3:
                self.observed.append(_tool_payload(request))
                message = AssistantMessage(tool_calls=(ToolCall("list", "list_assets", {"asset_types": ["text"]}),))
            case 4:
                listed = request.messages[-1]
                assert isinstance(listed, ToolMessage)
                items = json.loads(listed.content)
                assert [item["id"] for item in items] == [self.asset_id]
                message = AssistantMessage(
                    tool_calls=(ToolCall("delete", "delete_asset", {"asset_id": self.asset_id}),)
                )
            case _:
                deleted = request.messages[-1]
                assert isinstance(deleted, ToolMessage)
                assert json.loads(deleted.content) is True
                message = AssistantMessage(content="Asset lifecycle completed.")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


class BinaryAssetModel:
    """Create and explicitly read binary content through Base64."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.step = 0
        self.asset_id: str | None = None

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "create-binary",
                            "create_asset",
                            {
                                "asset": {
                                    "asset_type": "image",
                                    "name": "pixel.png",
                                    "mime_type": "image/png",
                                    "content_base64": base64.b64encode(self.payload).decode("ascii"),
                                }
                            },
                        ),
                    )
                )
            case 1:
                self.asset_id = str(_tool_payload(request)["id"])
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "read-binary",
                            "get_asset",
                            {"asset_id": self.asset_id, "include_binary_content": True},
                        ),
                    )
                )
            case _:
                details = _tool_payload(request)
                assert base64.b64decode(str(details["content_base64"])) == self.payload
                message = AssistantMessage(content="Binary asset read.")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_asset_extension_runs_complete_session_scoped_crud() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    model = AssetCrudModel()
    agent = await Agent.create(model, config=AgentRunConfig(session_id=session_id), extensions=[AssetExtension()])

    result = await agent.run("Manage my text asset")

    assert result.content == "Asset lifecycle completed."
    assert model.step == 6
    assert model.observed[0]["text_content"] == "First"
    assert model.observed[1]["text_content"] == "Revised"
    assert model.observed[2]["metadata"] == {"topic": "agents"}
    assert await session_asset_storage.list(SessionAssetListOptions(session_id=session_id)) == []


async def test_asset_extension_reads_binary_only_when_explicitly_requested() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    model = BinaryAssetModel(b"\x89PNG\r\n")
    agent = await Agent.create(model, config=AgentRunConfig(session_id=session_id), extensions=[AssetExtension()])

    result = await agent.run("Store and inspect this image")

    assert result.content == "Binary asset read."
    assert model.asset_id is not None
    stored = await session_asset_storage.get_for_session(session_id, model.asset_id)
    assert stored is not None and stored.asset_type == "image"


async def test_asset_extension_rejects_cross_session_reads_without_leaking_data() -> None:
    owner = (await session_storage.create(AgentSessionCreate())).session_id
    other = (await session_storage.create(AgentSessionCreate())).session_id
    secret = await session_asset_storage.create(
        SessionAssetCreate(session_id=owner, asset_type="text", name="private.txt", text_content="secret")
    )

    class CrossSessionModel:
        def __init__(self) -> None:
            self.step = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            if self.step == 0:
                message = AssistantMessage(
                    tool_calls=(ToolCall("cross-session", "get_asset", {"asset_id": secret.id}),)
                )
            else:
                tool_result = request.messages[-1]
                assert isinstance(tool_result, ToolMessage)
                assert not tool_result.success
                assert "secret" not in tool_result.content
                message = AssistantMessage(content="Asset unavailable.")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = await Agent.create(
        CrossSessionModel(),
        config=AgentRunConfig(session_id=other),
        extensions=[AssetExtension()],
    )
    result = await agent.run("Read the other asset")

    assert result.content == "Asset unavailable."
    stored = await session_asset_storage.get_for_session(owner, secret.id)
    assert stored is not None and stored.text_content == "secret"


async def test_asset_extension_rejects_invalid_base64_without_creating_an_asset() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id

    class InvalidBinaryModel:
        def __init__(self) -> None:
            self.step = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            if self.step == 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "invalid-binary",
                            "create_asset",
                            {
                                "asset": {
                                    "asset_type": "file",
                                    "name": "bad.bin",
                                    "content_base64": "not-base64!",
                                }
                            },
                        ),
                    )
                )
            else:
                tool_result = request.messages[-1]
                assert isinstance(tool_result, ToolMessage)
                assert not tool_result.success
                assert "valid Base64" in tool_result.content
                message = AssistantMessage(content="Rejected invalid content.")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = await Agent.create(
        InvalidBinaryModel(),
        config=AgentRunConfig(session_id=session_id),
        extensions=[AssetExtension()],
    )
    result = await agent.run("Create an invalid file")

    assert result.content == "Rejected invalid content."
    assert await session_asset_storage.list(SessionAssetListOptions(session_id=session_id)) == []
