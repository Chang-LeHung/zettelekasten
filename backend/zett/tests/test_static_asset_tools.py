"""The agent can publish a file and classify it in the static asset library."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from zett_agent.agent import Agent, AgentRunConfig, AgentRunContext, AgentState
from zett_agent.messages import AssistantMessage, ToolCall, ToolMessage
from zett_agent.model import ModelEvent, ModelRequest, ModelResponse

from zett.agent.extensions import StaticAssetExtension, TagExtension
from zett.application.assets.static_assets import static_asset_service
from zett.application.tags.tagging import tag_service
from zett.infra.persistence.dao import static_asset_storage
from zett.schemas import TagTargetType


def tool_payload(request: ModelRequest) -> dict[str, object]:
    """Decode the latest successful tool result."""
    message = request.messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.success
    payload = json.loads(message.content)
    assert isinstance(payload, dict)
    return payload


@pytest.fixture
def published(tmp_path: Path) -> Path:
    """Write the file the model would have produced before publishing it."""
    path = tmp_path / "cover.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\ncovers")
    return path


class PublishingModel:
    """Publish a file, create a file collection, and put the file in it."""

    def __init__(self, source: Path) -> None:
        self.step = 0
        self.source = source
        self.asset_id = ""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(ToolCall("publish", "upload_static_asset", {"path": str(self.source)}),)
                )
            case 1:
                published = tool_payload(request)
                self.asset_id = str(published["id"])
                # The answer is bounded: the id the next call needs, the name,
                # the media type, the URL, and the (empty) collection set.
                assert published["name"] == "cover.png"
                assert published["mime_type"] == "image/png"
                assert published["tags"] == []
                assert "storage_path" not in published and "sha256" not in published
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "collection",
                            "create_asset_tag",
                            {"path": "Assets/Covers", "description": "Book covers"},
                        ),
                    )
                )
            case 2:
                assert tool_payload(request)["path"] == "Assets/Covers"
                message = AssistantMessage(tool_calls=(ToolCall("tree", "list_asset_tags", {}),))
            case 3:
                tree = json.loads(request.messages[-1].content)
                assert [node["path"] for node in tree] == ["Assets"]
                assert tree[0]["children"][0]["path"] == "Assets/Covers"
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "classify",
                            "set_asset_tags",
                            {"asset_id": self.asset_id, "paths": ["Assets/Covers"]},
                        ),
                    )
                )
            case _:
                receipt = tool_payload(request)
                assert receipt["tags"] == ["Assets/Covers"]
                assert receipt["id"] == self.asset_id
                message = AssistantMessage(content="Cover published.")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_the_model_publishes_and_classifies_a_static_asset(published: Path) -> None:
    model = PublishingModel(published)
    agent = await Agent.create(
        model,
        config=AgentRunConfig(session_id="static-asset-tools"),
        extensions=[StaticAssetExtension(), TagExtension()],
    )

    result = await agent.run("Publish the cover and file it under Assets/Covers")

    assert result.content == "Cover published."
    assert model.step == 5
    stored = await static_asset_storage.list()
    assert [asset.name for asset in stored] == ["cover.png"]
    assert [tag.path for tag in stored[0].tags] == ["Assets/Covers"]
    assert await static_asset_service.content_path(stored[0].id) is not None
    path = await static_asset_service.content_path(stored[0].id)
    assert path is not None and path.read_bytes() == published.read_bytes()
    # The collection lives in the file library; the artifact tree stays empty.
    assert [node.path for node in await tag_service.list_tree(TagTargetType.ASSET)] == ["Assets"]
    assert await tag_service.list_tree(TagTargetType.ARTIFACT) == []


async def test_publish_refuses_a_relative_path_a_missing_file_and_an_oversized_one(tmp_path: Path) -> None:
    context = AgentRunContext(config=AgentRunConfig(session_id="publish-guards"), state=AgentState(), tools={})
    await StaticAssetExtension().on_tool(context)
    publish = context.tools["upload_static_asset"].handler

    with pytest.raises(ValueError, match="must be absolute"):
        await publish(path="cover.png")
    with pytest.raises(ValueError, match="File not found"):
        await publish(path=str(tmp_path / "missing.png"))

    limit = await static_asset_service.max_upload_size()
    oversized = tmp_path / "huge.bin"
    oversized.write_bytes(b"x" * (limit + 1))
    with pytest.raises(ValueError, match="the asset limit"):
        await publish(path=str(oversized))
    assert await static_asset_storage.list() == []


async def test_classifying_a_missing_file_is_refused() -> None:
    context = AgentRunContext(config=AgentRunConfig(session_id="tag-guards"), state=AgentState(), tools={})
    await TagExtension().on_tool(context)
    classify = context.tools["set_asset_tags"].handler

    with pytest.raises(ValueError, match="Static asset not found"):
        await classify(asset_id="missing-asset", paths=["Assets/Covers"])
