"""Status of a todo, idea, or reference card: storage, upgrade, HTTP routes, and the model's tool."""

import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from sqlalchemy import text
from zett_agent.agent import Agent, AgentRunConfig
from zett_agent.messages import AssistantMessage, ToolCall, ToolMessage
from zett_agent.model import ModelEvent, ModelRequest, ModelResponse

from zett.agent.extensions import ArtifactExtension
from zett.infra.persistence import database
from zett.infra.persistence.dao import artifact_storage, session_storage
from zett.infra.persistence.database import init_db, session_scope
from zett.main import app
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArtifactListOptions,
    ArtifactStatus,
    CardArtifactContent,
    CardStatus,
)


async def _session_id() -> str:
    return (await session_storage.create(AgentSessionCreate())).session_id


def _card(title: str, card_type: str = "todo", body: str = "Do it") -> CardArtifactContent:
    return CardArtifactContent(title=title, content=body, card_type=card_type)


async def test_a_new_card_starts_at_its_types_first_status_and_notes_have_none() -> None:
    session_id = await _session_id()
    todo = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Ship it")))
    note = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Idea", "note")))

    idea = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Spark", "idea")))
    reference = await artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=_card("Paper", "reference"))
    )
    quote = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Q", "quote")))

    assert todo.card_status is CardStatus.OPEN
    assert idea.card_status is CardStatus.CAPTURED
    assert reference.card_status is CardStatus.UNREAD
    assert note.card_status is None and quote.card_status is None


async def test_a_todo_can_be_created_already_in_progress() -> None:
    created = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=await _session_id(),
            content=_card("Started"),
            card_status=CardStatus.IN_PROGRESS,
        )
    )

    assert created.card_status is CardStatus.IN_PROGRESS


async def test_progress_does_not_touch_content_draft_or_version() -> None:
    session_id = await _session_id()
    created = await artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=_card("Ship it"), draft_content=_card("Ship it", body="v2"))
    )

    closed = await artifact_storage.set_card_status(created.id, CardStatus.DONE)

    assert closed.card_status is CardStatus.DONE
    assert closed.version == created.version
    assert closed.content == created.content
    assert closed.draft_content == created.draft_content
    assert closed.updated_at >= created.updated_at


async def test_editing_a_todo_keeps_its_progress_unless_the_card_stops_being_a_todo() -> None:
    session_id = await _session_id()
    created = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Ship it")))
    await artifact_storage.set_card_status(created.id, CardStatus.ON_HOLD)

    # Every write path rebuilds the whole write model from the stored artifact
    # and never states the progress, so omitting it must mean "keep".
    edited = await artifact_storage.update(
        created.id,
        AgentArtifactWrite(
            session_id=session_id,
            content=_card("Ship it", body="Reworded"),
            draft_content=_card("Ship it", body="Reworded"),
            status=ArtifactStatus.SAVED,
        ),
    )
    assert edited.card_status is CardStatus.ON_HOLD

    as_note = await artifact_storage.update(
        created.id,
        AgentArtifactWrite(session_id=session_id, content=_card("Ship it", "note"), draft_content=None),
    )
    assert as_note.card_status is None

    back = await artifact_storage.update(
        created.id,
        AgentArtifactWrite(session_id=session_id, content=_card("Ship it"), draft_content=None),
    )
    assert back.card_status is CardStatus.OPEN


async def test_a_card_without_a_status_type_refuses_one() -> None:
    session_id = await _session_id()
    note = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Idea", "note")))
    quote = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Q", "quote")))

    for artifact in (note, quote):
        try:
            await artifact_storage.set_card_status(artifact.id, CardStatus.DONE)
        except ValueError as error:
            assert "no status" in str(error)
        else:
            raise AssertionError("a card whose type carries no status must refuse one")
    try:
        await artifact_storage.set_card_status("missing", CardStatus.DONE)
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown artifact must be reported")


async def test_list_filters_by_progress_and_excludes_every_other_card() -> None:
    session_id = await _session_id()
    first = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("One")))
    second = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Two")))
    await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Idea", "note")))
    await artifact_storage.set_card_status(second.id, CardStatus.DONE)

    open_ids = [a.id for a in await artifact_storage.list(ArtifactListOptions(card_statuses=(CardStatus.OPEN,)))]
    done_ids = [a.id for a in await artifact_storage.list(ArtifactListOptions(card_statuses=(CardStatus.DONE,)))]
    both = await artifact_storage.count(ArtifactListOptions(card_statuses=(CardStatus.OPEN, CardStatus.DONE)))
    unfiltered = await artifact_storage.count(ArtifactListOptions())

    assert open_ids == [first.id]
    assert done_ids == [second.id]
    assert both == 2
    assert unfiltered == 3


async def test_init_db_gives_every_legacy_card_its_starting_status_once() -> None:
    await init_db()
    # Rows are written by `model_dump_json`, so the fixtures use the same compact encoding.
    legacy_todo = _card("Old task", body="x").model_dump_json()
    legacy_note = _card("Old note", "note", body="x").model_dump_json()
    legacy_idea = _card("Old idea", "idea", body="x").model_dump_json()
    legacy_reference = _card("Old paper", "reference", body="x").model_dump_json()
    async with session_scope() as session:
        for row_id, body in (
            ("legacy-todo", legacy_todo),
            ("legacy-note", legacy_note),
            ("legacy-idea", legacy_idea),
            ("legacy-reference", legacy_reference),
        ):
            await session.execute(
                text(
                    "INSERT INTO session_artifacts (id, session_id, artifact_type, status, title, content_json, "
                    "version, metadata, created_at, updated_at) "
                    "VALUES (:id, 's', 1, 2, 't', :body, 1, '{}', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"id": row_id, "body": body},
            )
    async with database.engine.begin() as connection:
        await connection.execute(text("DROP INDEX ix_session_artifacts_card_status"))
        await connection.execute(text("ALTER TABLE session_artifacts DROP COLUMN card_status"))

    await init_db()
    todo = await artifact_storage.get("legacy-todo")
    note = await artifact_storage.get("legacy-note")
    assert todo is not None and todo.card_status is CardStatus.OPEN
    assert note is not None and note.card_status is None
    idea = await artifact_storage.get("legacy-idea")
    reference = await artifact_storage.get("legacy-reference")
    assert idea is not None and idea.card_status is CardStatus.CAPTURED
    assert reference is not None and reference.card_status is CardStatus.UNREAD

    # A task the user already closed must survive the next start.
    await artifact_storage.set_card_status("legacy-todo", CardStatus.DONE)
    await init_db()
    again = await artifact_storage.get("legacy-todo")
    assert again is not None and again.card_status is CardStatus.DONE


def _library_card(title: str, card_type: str = "todo") -> dict[str, object]:
    return {
        "content": {"artifact_type": "card", "title": title, "content": "Body", "card_type": card_type},
        "status": "saved",
        "metadata": {"source": "test-suite"},
    }


def test_http_progress_route_filters_and_refuses_what_is_not_a_todo() -> None:
    with TestClient(app) as client:
        todo = client.post("/api/artifacts", json=_library_card("Write docs")).json()
        note = client.post("/api/artifacts", json=_library_card("Idea", "note")).json()
        assert todo["card_status"] == "open"
        assert note["card_status"] is None

        moved = client.put(
            f"/api/agent/{todo['session_id']}/artifacts/{todo['id']}/card-status", json={"status": "in_progress"}
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["card_status"] == "in_progress"
        assert moved.json()["version"] == todo["version"]

        listed = client.get("/api/artifacts", params={"card_statuses": ["in_progress"]}).json()
        counted = client.get("/api/artifacts/count", params={"card_statuses": ["in_progress"]}).json()
        none = client.get("/api/artifacts/count", params={"card_statuses": ["done"]}).json()
        assert [item["id"] for item in listed] == [todo["id"]]
        assert counted["count"] == 1
        assert none["count"] == 0

        refused = client.put(
            f"/api/agent/{note['session_id']}/artifacts/{note['id']}/card-status", json={"status": "done"}
        )
        assert refused.status_code == 409
        unknown = client.put(f"/api/agent/{note['session_id']}/artifacts/nope/card-status", json={"status": "done"})
        assert unknown.status_code == 404
        invalid = client.put(
            f"/api/agent/{todo['session_id']}/artifacts/{todo['id']}/card-status", json={"status": "later"}
        )
        assert invalid.status_code == 422


def test_http_content_edits_never_reset_progress() -> None:
    with TestClient(app) as client:
        todo = client.post("/api/artifacts", json=_library_card("Write docs")).json()
        base = f"/api/agent/{todo['session_id']}/artifacts/{todo['id']}"
        client.put(f"{base}/card-status", json={"status": "done"})

        content = {"artifact_type": "card", "title": "Write docs", "content": "Reworded", "card_type": "todo"}
        assert client.put(f"{base}/draft", json={"content": content}).json()["card_status"] == "done"
        assert client.post(f"{base}/save").json()["card_status"] == "done"
        assert client.put(base, json={"content": content}).json()["card_status"] == "done"


class TodoToolModel:
    """Create a todo, move it, then try the same on a note."""

    def __init__(self) -> None:
        self.step = 0
        self.todo_id = ""
        self.note_id = ""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        last = request.messages[-1]
        match self.step:
            case 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "a",
                            "create_artifact",
                            {
                                "content": {
                                    "artifact_type": "card",
                                    "title": "Task",
                                    "card_type": "todo",
                                    "content": "x",
                                }
                            },
                        ),
                        ToolCall(
                            "b",
                            "create_artifact",
                            {
                                "content": {
                                    "artifact_type": "card",
                                    "title": "Note",
                                    "card_type": "note",
                                    "content": "y",
                                }
                            },
                        ),
                    )
                )
            case 1:
                by_call = {m.tool_call_id: m for m in request.messages if isinstance(m, ToolMessage)}
                created = [json.loads(by_call[call_id].content) for call_id in ("a", "b")]
                assert created[0]["card_status"] == "open"
                assert created[1]["card_status"] is None
                self.todo_id, self.note_id = str(created[0]["id"]), str(created[1]["id"])
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall("c", "set_card_status", {"artifact_id": self.todo_id, "status": "done"}),
                        ToolCall("d", "set_card_status", {"artifact_id": self.note_id, "status": "done"}),
                    )
                )
            case 2:
                results = {m.tool_call_id: m for m in request.messages if isinstance(m, ToolMessage)}
                assert results["c"].success and json.loads(results["c"].content)["card_status"] == "done"
                assert not results["d"].success
                message = AssistantMessage(
                    tool_calls=(ToolCall("e", "query_artifacts", {"card_statuses": ["done"], "all_sessions": True}),)
                )
            case _:
                assert isinstance(last, ToolMessage)
                found = json.loads(last.content)
                assert [item["id"] for item in found] == [self.todo_id]
                assert found[0]["card_status"] == "done"
                message = AssistantMessage(content="done")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_the_model_closes_a_todo_with_a_tool_and_cannot_close_a_note() -> None:
    session_id = await _session_id()
    model = TodoToolModel()
    agent = await Agent.create(model, config=AgentRunConfig(session_id=session_id), extensions=[ArtifactExtension()])

    result = await agent.run("Create then close a task")

    assert result.content == "done"
    assert model.step == 4
    closed = await artifact_storage.get(model.todo_id)
    assert closed is not None and closed.card_status is CardStatus.DONE
    untouched = await artifact_storage.get(model.note_id)
    assert untouched is not None and untouched.card_status is None


async def test_each_type_takes_only_its_own_values() -> None:
    session_id = await _session_id()
    idea = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Spark", "idea")))
    reference = await artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=_card("Paper", "reference"))
    )

    assert (await artifact_storage.set_card_status(idea.id, CardStatus.ADOPTED)).card_status is CardStatus.ADOPTED
    assert (await artifact_storage.set_card_status(reference.id, CardStatus.READ)).card_status is CardStatus.READ
    for artifact, wrong in ((idea, CardStatus.DONE), (reference, CardStatus.ADOPTED)):
        try:
            await artifact_storage.set_card_status(artifact.id, wrong)
        except ValueError as error:
            assert wrong.value in str(error)
        else:
            raise AssertionError(f"{wrong.value} must not apply to this card type")

    # A status from another type cannot be requested at creation either.
    try:
        await artifact_storage.create(
            AgentArtifactWrite(session_id=session_id, content=_card("Spark", "idea"), card_status=CardStatus.READ)
        )
    except ValueError:
        pass
    else:
        raise AssertionError("a request must belong to the card's type")


async def test_changing_the_card_type_restarts_the_status_only_when_the_old_one_no_longer_fits() -> None:
    session_id = await _session_id()
    created = await artifact_storage.create(AgentArtifactWrite(session_id=session_id, content=_card("Spark", "idea")))
    await artifact_storage.set_card_status(created.id, CardStatus.EXPLORING)

    def rewrite(card_type: str):
        return artifact_storage.update(
            created.id,
            AgentArtifactWrite(session_id=session_id, content=_card("Spark", card_type), draft_content=None),
        )

    assert (await rewrite("idea")).card_status is CardStatus.EXPLORING
    assert (await rewrite("reference")).card_status is CardStatus.UNREAD
    assert (await rewrite("quote")).card_status is None
    assert (await rewrite("todo")).card_status is CardStatus.OPEN


async def test_status_is_derived_from_the_published_content() -> None:
    """A draft that retypes the card cannot move its status before it is saved."""
    session_id = await _session_id()
    created = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id, content=_card("Paper", "reference"), draft_content=_card("Paper", "idea")
        )
    )

    assert created.card_status is CardStatus.UNREAD
    try:
        await artifact_storage.set_card_status(created.id, CardStatus.ADOPTED)
    except ValueError:
        pass
    else:
        raise AssertionError("the published type decides which statuses apply")


def test_the_status_tables_cover_every_status_exactly_once() -> None:
    from zett.infra.persistence.tables import CARD_STATUS_TO_CODE, CODE_TO_CARD_STATUS
    from zett.schemas import CARD_STATUSES, CardType, default_status, statuses_for

    listed = [status for statuses in CARD_STATUSES.values() for status in statuses]
    assert sorted(listed) == sorted(CardStatus)
    assert len(CODE_TO_CARD_STATUS) == len(CardStatus) == len(set(CARD_STATUS_TO_CODE.values()))
    assert default_status(CardType.NOTE) is None and statuses_for(CardType.QUOTE) == ()
    assert [default_status(kind) for kind in (CardType.TODO, CardType.IDEA, CardType.REFERENCE)] == [
        CardStatus.OPEN,
        CardStatus.CAPTURED,
        CardStatus.UNREAD,
    ]


def test_the_command_line_mirrors_the_statuses_the_server_accepts() -> None:
    """The CLI cannot import the schemas, so a drift would only show at runtime."""
    from zett.cli.artifact import CARD_STATUS_CHOICES

    assert set(CARD_STATUS_CHOICES) == {status.value for status in CardStatus}


def test_http_library_route_moves_a_card_by_id_alone_and_checks_its_type() -> None:
    with TestClient(app) as client:
        reference = client.post("/api/artifacts", json=_library_card("A paper", "reference")).json()
        assert reference["card_status"] == "unread"

        moved = client.put(f"/api/artifacts/{reference['id']}/card-status", json={"status": "reading"})
        assert moved.status_code == 200, moved.text
        assert moved.json()["card_status"] == "reading"
        assert moved.json()["version"] == reference["version"]

        wrong = client.put(f"/api/artifacts/{reference['id']}/card-status", json={"status": "done"})
        assert wrong.status_code == 422
        assert client.put("/api/artifacts/nope/card-status", json={"status": "read"}).status_code == 404
        note = client.post("/api/artifacts", json=_library_card("Plain", "note")).json()
        assert client.put(f"/api/artifacts/{note['id']}/card-status", json={"status": "read"}).status_code == 409

        listed = client.get("/api/artifacts", params={"card_statuses": ["reading", "adopted"]}).json()
        assert [item["id"] for item in listed] == [reference["id"]]
