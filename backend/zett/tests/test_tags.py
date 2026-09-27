"""Persistent tag taxonomy, assignment, API, and Agent tool tests."""

import pytest
from fastapi.testclient import TestClient
from zett_agent.agent import (
    AgentRunConfig,
    AgentRunContext,
    AgentState,
)

from zett.agent.extensions import TagExtension
from zett.application.tags.tagging import tag_service
from zett.infra.persistence.dao import artifact_storage, session_storage, tag_storage
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
        await tag_storage.replace_artifact_tags(artifact.id, (keeper.id, "missing-tag"))

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
