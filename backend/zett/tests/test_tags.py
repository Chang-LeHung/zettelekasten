"""Persistent tag taxonomy, assignment, API, and Agent tool tests."""

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from zett_agent.agent import (
    Agent,
    AgentRunConfig,
    AgentRunContext,
    AgentState,
)
from zett_agent.messages import AssistantMessage, ToolCall, ToolMessage
from zett_agent.model import ModelEvent, ModelRequest, ModelResponse

from zett.agent.extensions import TagExtension
from zett.application.tags.tagging import tag_service
from zett.infra.persistence.dao import artifact_storage, session_storage, static_asset_storage, tag_storage
from zett.main import app
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArtifactStatus,
    CardArtifactContent,
    StaticAssetCreate,
    SuggestedTag,
    TagTargetType,
)


async def tagged_card(session_id: str, *, saved: bool = True):
    return await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED if saved else ArtifactStatus.DRAFT,
            content=CardArtifactContent(
                title="Asyncio",
                content="Structured concurrency",
                suggested_tags=[SuggestedTag(path="Engineering/Python/Asyncio", existing=False, confidence=0.9)],
            ),
        )
    )


async def test_hierarchical_paths_create_stable_nodes_and_aggregate_counts() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)

    tagged = await tag_service.sync_confirmed_suggestions(artifact)
    tree = await tag_service.list_tree()

    assert [tag.path for tag in await tag_storage.list()] == [
        "Engineering",
        "Engineering/Python",
        "Engineering/Python/Asyncio",
    ]
    assert [tag.path for tag in tagged.tags] == ["Engineering/Python/Asyncio"]
    assert tree[0].path == "Engineering"
    assert tree[0].direct_count == 0
    assert tree[0].total_count == 1
    assert tree[0].children[0].children[0].direct_count == 1

    same = await tag_service.create_path("engineering/python/asyncio")
    assert same.id == tagged.tags[0].id
    assert len(await tag_storage.list()) == 3

    # Assigning the same artifact to an ancestor must not inflate the ancestor's subtree count.
    await tag_service.replace_artifact_tags(artifact.id, ["Engineering", "Engineering/Python/Asyncio"])
    assert (await tag_service.list_tree())[0].direct_count == 1
    assert (await tag_service.list_tree())[0].total_count == 1


async def test_tag_deletion_protects_children_and_assignments() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    tagged = await tag_service.sync_confirmed_suggestions(await tagged_card(session_id))
    root = await tag_storage.get_by_normalized_path("engineering")
    assert root is not None

    with pytest.raises(ValueError, match="children"):
        await tag_service.delete(root.id)
    with pytest.raises(ValueError, match="assigned"):
        await tag_service.delete(root.id, recursive=True)

    assert await tag_service.delete(root.id, recursive=True, force=True)
    assert await tag_storage.list() == []
    refreshed = await artifact_storage.get(tagged.id)
    assert refreshed is not None and refreshed.tags == []


async def test_library_tag_api_filters_a_parent_subtree_and_blocks_its_deletion() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)
    confirmed = await tag_service.sync_confirmed_suggestions(artifact)
    assert [tag.path for tag in confirmed.tags] == ["Engineering/Python/Asyncio"]

    with TestClient(app) as client:
        tree = client.get("/api/library/tags").json()
        root_id = tree[0]["id"]
        assert tree[0]["path"] == "Engineering"
        assert tree[0]["children"][0]["children"][0]["total_count"] == 1

        filtered = client.get(f"/api/artifacts?statuses=saved&tag_ids={root_id}").json()
        assert [item["id"] for item in filtered] == [artifact.id]
        assert filtered[0]["tags"][0]["path"] == "Engineering/Python/Asyncio"

        blocked = client.delete(f"/api/library/tags/{root_id}?recursive=true")
        assert blocked.status_code == 409

        # Clearing a confirmed assignment removes the assignment for good.
        assert client.put(f"/api/library/tags/artifacts/{artifact.id}", json={"paths": []}).status_code == 200
        assert client.get("/api/library/tags").json()[0]["total_count"] == 0
        assert client.delete(f"/api/library/tags/{root_id}?recursive=true").json() == {"ok": True}


async def test_library_tag_api_force_delete_removes_all_artifact_assignments() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)
    await tag_service.sync_confirmed_suggestions(artifact)

    with TestClient(app) as client:
        tree = client.get("/api/library/tags").json()
        root_id = tree[0]["id"]

        # The management UI makes both destructive choices explicit. Storage then
        # removes assignment rows before deleting the tag subtree; no DB cascade is used.
        response = client.delete(f"/api/library/tags/{root_id}?recursive=true&force=true")

        assert response.json() == {"ok": True}
        refreshed = await artifact_storage.get(artifact.id)
        assert refreshed is not None and refreshed.tags == []
        assert client.get("/api/library/tags").json() == []


async def test_tag_extension_registers_real_taxonomy_tools() -> None:
    extension = TagExtension()
    context = AgentRunContext(
        config=AgentRunConfig(session_id="tag-tools"),
        state=AgentState(),
        tools={},
    )

    await extension.on_tool(context)

    assert set(context.tools) >= {
        "create_tag",
        "list_tags",
        "update_tag",
        "delete_tag",
        "set_artifact_tags",
    }


def tool_payload(request: ModelRequest) -> dict[str, object]:
    """Decode the latest successful object result from a model request."""
    message = request.messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.success
    payload = json.loads(message.content)
    assert isinstance(payload, dict)
    return payload


def tool_result(request: ModelRequest) -> object:
    """Decode the latest successful tool result, whatever its JSON shape."""
    message = request.messages[-1]
    assert isinstance(message, ToolMessage)
    assert message.success
    return json.loads(message.content)


class TagToolModel:
    """Run the tag tools the way a model does, over one real artifact."""

    def __init__(self, artifact_id: str) -> None:
        self.step = 0
        self.artifact_id = artifact_id
        self.tag_id = ""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(ToolCall("create", "create_tag", {"path": "Engineering/Python", "color": "#3b82f6"}),)
                )
            case 1:
                self.tag_id = str(tool_payload(request)["id"])
                message = AssistantMessage(tool_calls=(ToolCall("list", "list_tags", {}),))
            case 2:
                paths = [node["path"] for node in json.loads(request.messages[-1].content)]
                assert paths == ["Engineering"], paths
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "set-tags",
                            "set_artifact_tags",
                            {"artifact_id": self.artifact_id, "paths": ["Engineering/Python"]},
                        ),
                    )
                )
            case 3:
                # The write answers with a bounded receipt, not the stored row.
                receipt = tool_payload(request)
                assert receipt["tags"] == ["Engineering/Python"]
                assert "content" not in receipt
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall("rename", "update_tag", {"tag_id": self.tag_id, "path": "Engineering/Asyncio"}),
                    )
                )
            case 4:
                assert tool_payload(request)["path"] == "Engineering/Asyncio"
                message = AssistantMessage(tool_calls=(ToolCall("guard", "delete_tag", {"tag_id": self.tag_id}),))
            case 5:
                refused = request.messages[-1]
                assert isinstance(refused, ToolMessage)
                assert not refused.success and "assigned" in refused.content
                message = AssistantMessage(
                    tool_calls=(ToolCall("force", "delete_tag", {"tag_id": self.tag_id, "force": True}),)
                )
            case _:
                assert tool_result(request) is True
                message = AssistantMessage(content="Classification complete.")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_tag_tools_run_a_complete_classification_lifecycle() -> None:
    """Every tag tool a model can call works against a real artifact.

    Registration alone proves nothing: the tools resolve the artifact, write
    through ``tag_storage``, honour the assignment guard, and answer with the
    bounded receipt the artifact tools use.
    """
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)
    model = TagToolModel(artifact.id)
    agent = await Agent.create(model, config=AgentRunConfig(session_id=session_id), extensions=[TagExtension()])

    result = await agent.run("Classify this card")

    assert result.content == "Classification complete."
    assert model.step == 7
    stored = await artifact_storage.get(artifact.id)
    assert stored is not None and stored.tags == []
    # The forced delete removed the leaf and its assignment; the parent it was
    # created under stays, because nothing asked for that one to go.
    assert [tag.path for tag in await tag_storage.list()] == ["Engineering"]


async def test_replacing_assignments_rolls_back_when_a_tag_is_missing() -> None:
    """The delete and the inserts share one transaction, so a failure keeps the old set.

    ``replace_artifact_tags`` deletes every assignment for the artifact and then
    inserts the new set. That is only safe because both halves commit together:
    an exception mid-way — a tag that vanished between resolving it and writing
    it — must leave the artifact with the tags it already had instead of none.
    """
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)
    await tag_service.replace_artifact_tags(artifact.id, ["Engineering/Python"])
    keeper = await tag_service.create_path("Projects/Zett")
    await tag_service.replace_artifact_tags(artifact.id, ["Engineering/Python", "Projects/Zett"])

    with pytest.raises(KeyError):
        await tag_storage.replace_tags(TagTargetType.ARTIFACT, artifact.id, (keeper.id, "missing-tag"))

    refreshed = await artifact_storage.get(artifact.id)
    assert refreshed is not None
    assert sorted(tag.path for tag in refreshed.tags) == ["Engineering/Python", "Projects/Zett"]
    assignment = await tag_storage.assignment_count(keeper.id)
    assert assignment == 1


def test_tag_api_serves_one_tag_and_edits_one_assignment() -> None:
    """A shell adds or removes one tag without rewriting the artifact's whole set."""
    with TestClient(app) as client:
        artifact = client.post(
            "/api/artifacts",
            json={
                "content": {"artifact_type": "card", "title": "Asyncio", "content": "Structured concurrency"},
                "status": "saved",
                "metadata": {"source": "test-suite"},
            },
        ).json()
        first = client.post("/api/library/tags", json={"path": "Engineering/Python"}).json()
        second = client.post("/api/library/tags", json={"path": "Projects/Zett"}).json()

        # Read one tag by id; an unknown id is a 404 rather than an empty answer.
        fetched = client.get(f"/api/library/tags/{second['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["path"] == "Projects/Zett"
        assert client.get("/api/library/tags/does-not-exist").status_code == 404

        # Attaching keeps every tag the artifact already carries, and repeating
        # the same assignment changes nothing.
        assert [
            tag["path"]
            for tag in client.put(f"/api/library/tags/{first['id']}/artifacts/{artifact['id']}").json()["tags"]
        ] == ["Engineering/Python"]
        attached = client.put(f"/api/library/tags/{second['id']}/artifacts/{artifact['id']}")
        assert sorted(tag["path"] for tag in attached.json()["tags"]) == ["Engineering/Python", "Projects/Zett"]
        again = client.put(f"/api/library/tags/{second['id']}/artifacts/{artifact['id']}")
        assert len(again.json()["tags"]) == 2

        # Detaching removes exactly that assignment, and repeating it is safe.
        detached = client.delete(f"/api/library/tags/{second['id']}/artifacts/{artifact['id']}")
        assert [tag["path"] for tag in detached.json()["tags"]] == ["Engineering/Python"]
        assert client.delete(f"/api/library/tags/{second['id']}/artifacts/{artifact['id']}").status_code == 200

        # Unknown tags and artifacts are 404; a draft is refused like the UI's save path.
        assert client.put(f"/api/library/tags/does-not-exist/artifacts/{artifact['id']}").status_code == 404
        assert client.put(f"/api/library/tags/{first['id']}/artifacts/does-not-exist").status_code == 404
        draft = client.post(
            "/api/artifacts",
            json={
                "content": {"artifact_type": "card", "title": "Draft", "content": "Not saved"},
                "status": "draft",
                "metadata": {"source": "test-suite"},
            },
        ).json()
        assert client.put(f"/api/library/tags/{first['id']}/artifacts/{draft['id']}").status_code == 422

        # The whole-set endpoint still replaces everything the editor saved.
        replaced = client.put(f"/api/library/tags/artifacts/{artifact['id']}", json={"paths": ["Projects/Zett"]})
        assert [tag["path"] for tag in replaced.json()["tags"]] == ["Projects/Zett"]


async def test_saving_keeps_tags_attached_outside_the_suggestion_list() -> None:
    """A save confirms suggestions; it does not reset the artifact's taxonomy.

    Regression: saving an artifact whose published content carried no suggested
    tags replaced the whole assignment set with that empty list. Tags the model
    attached with ``set_artifact_tags`` — or the Library's tag editor, or
    ``zett tag add`` — silently disappeared, so the Library showed the artifact
    untagged even though the tool had answered with the tags it just attached.
    """
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED,
            content=CardArtifactContent(title="Memory layout", content="Body"),
        )
    )
    attached = await tag_service.replace_artifact_tags(artifact.id, ["操作系统/内存管理", "操作系统/进程"])
    assert sorted(tag.path for tag in attached.tags) == ["操作系统/内存管理", "操作系统/进程"]

    with TestClient(app) as client:
        saved = client.post(f"/api/agent/{session_id}/artifacts/{artifact.id}/save")
        listed = client.get("/api/artifacts?statuses=saved").json()

    assert saved.status_code == 200
    assert sorted(tag["path"] for tag in saved.json()["tags"]) == ["操作系统/内存管理", "操作系统/进程"]
    assert sorted(tag["path"] for tag in listed[0]["tags"]) == ["操作系统/内存管理", "操作系统/进程"]


async def test_unchecking_a_suggestion_removes_it_when_the_artifact_is_saved() -> None:
    """The one removal a save owns: a suggestion the user dropped in the editor."""
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED,
            content=CardArtifactContent(
                title="Asyncio",
                content="Structured concurrency",
                suggested_tags=[SuggestedTag(path="Engineering/Python", existing=False, confidence=0.9)],
            ),
        )
    )
    applied = await tag_service.sync_confirmed_suggestions(artifact)
    assert [tag.path for tag in applied.tags] == ["Engineering/Python"]

    with TestClient(app) as client:
        # The editor saves a draft whose suggestion list no longer carries the tag.
        drafted = client.put(
            f"/api/agent/{session_id}/artifacts/{artifact.id}/draft",
            json={"content": {"artifact_type": "card", "title": "Asyncio", "content": "Structured concurrency"}},
        )
        assert drafted.status_code == 200
        saved = client.post(f"/api/agent/{session_id}/artifacts/{artifact.id}/save")

    assert saved.status_code == 200
    assert saved.json()["tags"] == []


async def _library_file(name: str = "reference.txt", *, content: bytes = b"file body"):
    return await static_asset_storage.create(StaticAssetCreate(name=name, mime_type="text/plain", content=content))


async def test_a_static_asset_carries_the_same_taxonomy_as_an_artifact() -> None:
    """One tag table classifies both kinds, and each link names which kind it is.

    The link's ``target_type`` is what keeps the two apart: the same path may
    classify a card and the file it was built from, and the tree counts every
    resource a tag carries.
    """
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    asset = await _library_file()
    artifact = await tagged_card(session_id)

    tagged = await tag_service.replace_asset_tags(asset.id, ["Engineering/Python"])
    assert [tag.path for tag in tagged.tags] == ["Engineering/Python"]

    confirmed = await tag_service.sync_confirmed_suggestions(artifact)
    assert [tag.path for tag in confirmed.tags] == ["Engineering/Python/Asyncio"]

    parent = next(node for node in await tag_service.list_tree() if node.path == "Engineering")
    assert parent.total_count == 2
    python = next(node for node in parent.children if node.path == "Engineering/Python")
    assert python.direct_count == 1
    assert python.total_count == 2
    # Both reads group by the resource that carries the tag.
    assert [tag.path for tag in (await static_asset_storage.get(asset.id)).tags] == ["Engineering/Python"]
    assert [tag.path for tag in (await artifact_storage.get(artifact.id)).tags] == ["Engineering/Python/Asyncio"]


async def test_static_asset_tagging_attaches_detaches_and_replaces() -> None:
    asset = await _library_file("notes.pdf")
    first = await tag_service.create_path("Projects/Zett")

    attached = await tag_service.assign_asset_tag(asset.id, first.id)
    assert [tag.path for tag in attached.tags] == ["Projects/Zett"]
    # Attaching the same tag twice changes nothing.
    assert len((await tag_service.assign_asset_tag(asset.id, first.id)).tags) == 1

    replaced = await tag_service.replace_asset_tags(asset.id, ["Engineering/Python", "Projects/Zett"])
    assert sorted(tag.path for tag in replaced.tags) == ["Engineering/Python", "Projects/Zett"]

    detached = await tag_service.unassign_asset_tag(asset.id, first.id)
    assert [tag.path for tag in detached.tags] == ["Engineering/Python"]
    assert await tag_service.replace_asset_tags(asset.id, [])
    assert (await static_asset_storage.get(asset.id)).tags == []

    with pytest.raises(KeyError):
        await tag_service.replace_asset_tags("missing-asset", ["Engineering/Python"])


async def test_deleting_a_static_asset_removes_the_links_it_carried() -> None:
    """No foreign key cleans this up, so the delete path has to."""
    asset = await _library_file("doomed.txt")
    tagged = await tag_service.replace_asset_tags(asset.id, ["Engineering/Python"])
    tag_id = tagged.tags[0].id

    assert await static_asset_storage.delete(asset.id) is True

    assert await tag_storage.assignment_count(tag_id) == 0
    # With the resource gone, the tag it carried is unused and can be deleted.
    assert await tag_service.delete(tag_id) is True


def test_asset_tag_api_attaches_detaches_and_replaces() -> None:
    with TestClient(app) as client:
        asset = client.post(
            "/api/assets/upload?name=notes.txt",
            content=b"file body",
            headers={"content-type": "text/plain"},
        ).json()
        first = client.post("/api/library/tags", json={"path": "Engineering/Python"}).json()
        second = client.post("/api/library/tags", json={"path": "Projects/Zett"}).json()

        attached = client.put(f"/api/library/tags/{first['id']}/assets/{asset['id']}")
        assert attached.status_code == 200
        assert [tag["path"] for tag in attached.json()["tags"]] == ["Engineering/Python"]

        replaced = client.put(f"/api/library/tags/assets/{asset['id']}", json={"paths": ["Projects/Zett"]})
        assert [tag["path"] for tag in replaced.json()["tags"]] == ["Projects/Zett"]

        detached = client.delete(f"/api/library/tags/{second['id']}/assets/{asset['id']}")
        assert detached.status_code == 200
        assert detached.json()["tags"] == []

        # The uploaded asset lists its tags, and unknown ids are 404s.
        listed = client.get("/api/assets").json()
        assert listed[0]["id"] == asset["id"] and listed[0]["tags"] == []
        assert client.put(f"/api/library/tags/{first['id']}/assets/missing").status_code == 404
        assert client.put(f"/api/library/tags/missing/assets/{asset['id']}").status_code == 404
        assert client.put("/api/library/tags/assets/missing", json={"paths": []}).status_code == 404
