"""Container ``@`` commands: listing, registration, and Agent handoff."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from zett_agent import (
    AgentRunConfig,
    AssistantMessage,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ReasoningEffort,
    UserMessage,
)

from zett.agent import (
    AtCommandInvocation,
    AtCommandItem,
    AtCommandSource,
    SessionAssetAtCommandSource,
    ZettelkastenAgent,
    ZettelkastenAgentConfig,
    at_command_message,
    stable_at_command_id,
)
from zett.application.routes import agent as agent_routes
from zett.infra.dao import artifact_storage, session_asset_storage, session_storage
from zett.main import app
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    CardArtifactContent,
    SessionAssetCreate,
)


async def _session() -> str:
    return (await session_storage.create(AgentSessionCreate())).session_id


async def _container(session_id: str) -> ZettelkastenAgent:
    return await ZettelkastenAgent(
        ZettelkastenAgentConfig(session_id, extensions=(), mcp_config_path=None)
    ).initialize()


def _provider_payload() -> dict[str, object]:
    return {
        "name": "Probe",
        "provider": "openai_compatible",
        "model": "gpt-5",
        "base_url": "http://127.0.0.1:9/v1",
        "api_key": "sk-test",
        "temperature": 0.2,
        "response": False,
        "enabled": True,
    }


class _Source(AtCommandSource):
    """One inert ``@`` source used by registration tests."""

    def __init__(self, *, owner: str = "example", kind: str = "example") -> None:
        self.owner = owner
        self.kind = kind

    async def items(self, session_id: str):
        return ()

    async def verify(self, session_id: str, item) -> bool:
        return False


async def _ignoring_handler(container, invocation) -> AsyncIterator[object]:
    del container, invocation
    if False:  # pragma: no cover - never yields; keeps the handler an async generator
        yield None


def _item(*, name: str, target_id: str, kind: str = "asset", label: str | None = None) -> AtCommandItem:
    """Build one listed reference without touching the database."""
    return AtCommandItem(
        id=f"{kind}-{target_id}",
        kind=kind,
        name=name,
        label=label or name,
        description=f"{kind} reference",
        target_id=target_id,
    )


async def test_container_lists_session_assets_and_artifacts_with_unique_names() -> None:
    session_id = await _session()
    await session_asset_storage.create(
        SessionAssetCreate(session_id=session_id, asset_type="text", name="Report.md", text_content="# Body")
    )
    await session_asset_storage.create(
        SessionAssetCreate(session_id=session_id, asset_type="text", name="report.md", text_content="second")
    )
    await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="Report Draft", content="One idea."),
        )
    )

    first = await (await _container(session_id)).at_commands(session_id)
    second = await (await _container(session_id)).at_commands(session_id)

    assert [(item.kind, item.name) for item in first] == [
        ("artifact", "report-draft"),
        ("asset", "report-md"),
        ("asset", "report-md-2"),
    ]
    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].label == "Report Draft"
    assert first[1].target_id != first[2].target_id


async def test_container_lists_only_the_owning_session() -> None:
    session_id = await _session()
    await session_asset_storage.create(
        SessionAssetCreate(session_id=session_id, asset_type="link", name="Docs", source_url="https://example.com")
    )
    container = await _container(session_id)

    assert [item.label for item in await container.at_commands(session_id)] == ["Docs"]
    assert await container.at_commands(await _session()) == ()


async def test_sources_stamp_item_identity_and_reject_unusable_items() -> None:
    source = SessionAssetAtCommandSource()

    item = source.item(target_id="asset-1", label="  Report.md  ", description="text asset · 4 B")

    assert item.kind == source.kind
    assert item.name == "report-md"
    assert item.label == "Report.md"
    assert item.id == stable_at_command_id(owner="assets", kind="asset", target_id="asset-1")

    for invalid in (
        {"id": "", "target_id": "asset-1"},
        {"label": "   "},
        {"description": "   "},
        {"name": "Report MD"},
        {"kind": "Asset"},
    ):
        with pytest.raises(ValueError):
            AtCommandItem(
                **{
                    "id": "item-1",
                    "kind": "asset",
                    "name": "report-md",
                    "label": "Report.md",
                    "description": "text asset · 4 B",
                    "target_id": "asset-1",
                    **invalid,
                }
            )


async def test_at_command_lookup_rejects_unknown_and_deleted_references() -> None:
    session_id = await _session()
    asset = await session_asset_storage.create(
        SessionAssetCreate(session_id=session_id, asset_type="text", name="notes.md", text_content="Body")
    )
    container = await _container(session_id)
    item = (await container.at_commands(session_id))[0]

    assert await container.at_command(session_id, item.id) == item
    assert await container.at_command(session_id, "missing-id") is None

    await session_asset_storage.delete(asset.id)
    assert await container.at_command(session_id, item.id) is None


async def test_injected_message_names_kind_and_id_without_copying_content() -> None:
    secret = "Body text the model must read with a tool"
    message = UserMessage(content="summarize @notes-md")
    item = _item(name="notes-md", target_id="asset-id", label="notes.md")

    injected = at_command_message(message, (item,))

    assert injected.text.startswith("The user referenced resources from this conversation with @ tokens.")
    assert "- @notes-md: asset asset-id" in injected.text
    assert secret not in injected.text
    assert injected.text.endswith("User request:\nsummarize @notes-md")
    assert injected.attributes["at_command"]["references"] == [
        {
            "id": item.id,
            "kind": "asset",
            "name": "notes-md",
            "label": "notes.md",
            "target_id": "asset-id",
        }
    ]
    assert injected.attributes["at_command"]["raw_parts"] == [{"type": "text", "text": "summarize @notes-md"}]


async def test_execute_at_command_runs_the_registered_handler() -> None:
    session_id = await _session()
    await session_asset_storage.create(
        SessionAssetCreate(session_id=session_id, asset_type="text", name="notes.md", text_content="Body")
    )
    container = await _container(session_id)
    item = (await container.at_commands(session_id))[0]
    captured: list[UserMessage] = []

    class FakeClient:
        async def stream(self, message: UserMessage, **options) -> AsyncIterator[ModelEvent]:
            del options
            captured.append(message)
            if False:  # pragma: no cover - keeps this method an async generator
                yield ModelEvent.completed(ModelResponse(AssistantMessage(content="")))

    invocation = AtCommandInvocation(
        session_id=session_id,
        client=FakeClient(),  # type: ignore[arg-type]
        message=UserMessage(content="summarize @notes-md"),
        model=None,  # type: ignore[arg-type]
        config=AgentRunConfig(session_id=session_id),
        reasoning_effort=ReasoningEffort.MEDIUM,
        metadata={},
        tags={},
        item=item,
    )

    events = [event async for event in container.execute_at_command(invocation)]

    assert events == []
    assert captured[0].text.endswith("User request:\nsummarize @notes-md")
    assert captured[0].attributes["at_command"]["references"][0]["id"] == item.id


async def test_duplicate_and_invalid_at_command_registrations_are_rejected() -> None:
    container = ZettelkastenAgent(ZettelkastenAgentConfig("session", extensions=(), mcp_config_path=None))
    container.register_at_command(
        owner="example",
        kind="example",
        source=_Source(),
        handler=_ignoring_handler,
    )

    with pytest.raises(ValueError):
        container.register_at_command(
            owner="example",
            kind="example",
            source=_Source(),
            handler=_ignoring_handler,
        )
    with pytest.raises(ValueError):
        container.register_at_command(
            owner="example",
            kind="Not A Kind",
            source=_Source(kind="Not A Kind"),
            handler=_ignoring_handler,
        )
    with pytest.raises(ValueError):
        container.register_at_command(
            owner="example",
            kind="mismatched",
            source=_Source(),
            handler=_ignoring_handler,
        )

    assert [definition.kind for definition in container.at_command_definitions()] == ["example"]


def test_at_command_listing_route_returns_referenceable_resources() -> None:
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        client.post(
            f"/api/agent/{session_id}/assets/text",
            json={"name": "Session Notes", "content": "Body"},
        )

        listed = client.get(f"/api/agent/{session_id}/at-commands")

        assert listed.status_code == 200
        items = listed.json()
        assert len(items) == 1
        assert items[0]["id"]
        assert items[0]["kind"] == "asset"
        assert items[0]["name"] == "session-notes"
        assert items[0]["label"] == "Session Notes"
        assert items[0]["description"] == "text asset · 4 B"
        assert client.get("/api/agent/missing/at-commands").status_code == 404


def test_streamed_reference_turn_sends_kind_and_id_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[ModelRequest] = []

    class CapturingModel:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            captured.append(request)
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="ok")))

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: CapturingModel())
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        asset = client.post(
            f"/api/agent/{session_id}/assets/text",
            json={"name": "Report", "content": "Body"},
        ).json()
        item_id = client.get(f"/api/agent/{session_id}/at-commands").json()[0]["id"]

        response = client.post(
            f"/api/agent/{session_id}/at-commands/{item_id}",
            json={
                "raw_content": "please review @report",
                "provider_id": provider_id,
                "reasoning_effort": "medium",
            },
        )

        assert response.status_code == 200
        prompt = captured[0].messages[-1]
        assert isinstance(prompt, UserMessage)
        assert f"- @report: asset {asset['id']}" in prompt.text
        assert "Body" not in prompt.text
        assert prompt.text.endswith("User request:\nplease review @report")
        assert prompt.attributes["at_command"]["references"][0]["target_id"] == asset["id"]


def test_unknown_at_command_id_fails_before_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnusedModel:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            raise RuntimeError("the model must not run for an unknown reference")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: UnusedModel())
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]

        response = client.post(
            f"/api/agent/{session_id}/at-commands/unknown",
            json={
                "raw_content": "review @missing",
                "provider_id": provider_id,
                "reasoning_effort": "medium",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "At command not found"
