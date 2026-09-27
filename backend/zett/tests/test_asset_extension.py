"""End-to-end coverage for model-operated session assets."""

import base64
import json
from collections.abc import AsyncIterator

import pytest
from zett_agent.agent import (
    Agent,
    AgentRunConfig,
    AgentRunContext,
    AgentState,
)
from zett_agent.messages import (
    AssistantMessage,
    ToolCall,
    ToolMessage,
)
from zett_agent.model import (
    ModelEvent,
    ModelRequest,
    ModelResponse,
)

from zett.agent import AssetExtension
from zett.agent.extensions.assets import UploadedAsset, _read_upload
from zett.application.files.object_store import session_directory_key
from zett.infra.files.object_store import get_object_store
from zett.infra.persistence.dao import artifact_storage, session_asset_storage, session_storage
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArtifactStatus,
    ImageArtifactContent,
    SessionAssetCreate,
    SessionAssetListOptions,
    SessionAssetType,
)


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
        assert names == {"create_asset", "upload_asset", "get_asset", "update_asset", "delete_asset", "list_assets"}
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


async def test_asset_extension_rejects_payloads_above_the_configured_limit() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id

    class OversizedBinaryModel:
        def __init__(self) -> None:
            self.step = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            if self.step == 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "oversized-binary",
                            "create_asset",
                            {
                                "asset": {
                                    "asset_type": "file",
                                    "name": "large.bin",
                                    "content_base64": base64.b64encode(b"1234").decode("ascii"),
                                }
                            },
                        ),
                    )
                )
            else:
                tool_result = request.messages[-1]
                assert isinstance(tool_result, ToolMessage)
                assert not tool_result.success
                assert "3 byte size limit" in tool_result.content
                message = AssistantMessage(content="Rejected oversized content.")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = await Agent.create(
        OversizedBinaryModel(),
        config=AgentRunConfig(session_id=session_id),
        extensions=[AssetExtension(max_asset_size_bytes=3)],
    )
    result = await agent.run("Create an oversized file")

    assert result.content == "Rejected oversized content."
    assert await session_asset_storage.list(SessionAssetListOptions(session_id=session_id)) == []


async def test_upload_asset_stores_a_file_the_model_wrote(tmp_path) -> None:
    """The model writes a file, uploads it, and points an image artifact at it."""
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    directory = get_object_store().resolve(session_directory_key(session_id))
    directory.mkdir(parents=True, exist_ok=True)
    payload = b"\x89PNG\r\n\x1a\n" + b"pixels" * 4
    (directory / "generated.png").write_bytes(payload)

    context = AgentRunContext(
        config=AgentRunConfig(session_id=session_id),
        state=AgentState(),
        tools={},
    )
    await AssetExtension().on_tool(context)

    uploaded = await context.tools["upload_asset"].handler(path=str(directory / "generated.png"))

    # The tool answers with the next step's key and URL, not the whole row: the
    # model never acts on a session id, a hash, or a timestamp.
    assert isinstance(uploaded, UploadedAsset)
    assert set(UploadedAsset.model_fields) == {"name", "mime_type", "storage_path", "content_url"}
    assert uploaded.name == "generated.png"
    assert uploaded.mime_type == "image/png"
    assert uploaded.storage_path.startswith(f"assets/sessions/{session_id}/")
    assert uploaded.content_url == f"/api/files/{uploaded.storage_path}"

    # The uploaded key is exactly what an image artifact needs, and the artifact
    # renders it through the same file URL the upload reported.
    artifact = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED,
            content=ImageArtifactContent(title="Generated chart", asset_path=uploaded.storage_path),
        )
    )
    assert artifact.content_url == uploaded.content_url
    assets = await session_asset_storage.list(SessionAssetListOptions(session_id=session_id))
    assert [asset.name for asset in assets] == ["generated.png"]
    assert assets[0].asset_type is SessionAssetType.IMAGE
    assert assets[0].size_bytes == len(payload)
    stored_bytes = await session_asset_storage.content_path(session_id, assets[0].id)
    assert stored_bytes is not None and stored_bytes.read_bytes() == payload


async def test_read_upload_refuses_paths_outside_the_conversation_and_oversized_files() -> None:
    """An upload tool that could read any file would turn a mistake into a leak."""
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    directory = get_object_store().resolve(session_directory_key(session_id))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "big.bin").write_bytes(b"x" * 101)

    with pytest.raises(ValueError, match="must be absolute"):
        _read_upload(session_id, "big.bin", max_bytes=100)
    with pytest.raises(ValueError, match="stay inside this conversation"):
        _read_upload(session_id, "/etc/hosts", max_bytes=100)
    with pytest.raises(ValueError, match="File not found"):
        _read_upload(session_id, str(directory / "missing.png"), max_bytes=100)
    with pytest.raises(ValueError, match="the asset limit is 100"):
        _read_upload(session_id, str(directory / "big.bin"), max_bytes=100)

    name, content, media_type = _read_upload(session_id, str(directory / "big.bin"), max_bytes=200)
    assert (name, len(content), media_type) == ("big.bin", 101, "application/octet-stream")
