"""Persistent tag taxonomy, assignment, API, and Agent tool tests."""

import pytest
from fastapi.testclient import TestClient
from zett_agent import AgentRunConfig, AgentRunContext, AgentState

from zett.agent.extensions import TagExtension
from zett.application.tagging import tag_service
from zett.infra.dao import artifact_storage, session_storage, tag_storage
from zett.main import app
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArtifactStatus,
    CardArtifactContent,
    SuggestedTag,
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


async def test_library_tag_api_backfills_old_artifacts_and_filters_a_parent_subtree() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)
    assert artifact.tags == []

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

        # Clearing a confirmed assignment must not let legacy suggestions recreate it.
        assert client.put(f"/api/library/tags/artifacts/{artifact.id}", json={"paths": []}).status_code == 200
        assert client.get("/api/library/tags").json()[0]["total_count"] == 0
        assert client.delete(f"/api/library/tags/{root_id}?recursive=true").json() == {"ok": True}


async def test_library_tag_api_force_delete_removes_all_artifact_assignments() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await tagged_card(session_id)

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
