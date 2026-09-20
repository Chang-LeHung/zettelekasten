"""Container slash command registration, stable IDs, and Agent handoff."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from zett_agent import (
    AgentClient,
    AgentEvent,
    AgentEventType,
    AgentRunConfig,
    ImageBytesSource,
    ImageContent,
    ReasoningEffort,
    TextContent,
    UserContent,
    UserMessage,
)

from zett.agent import (
    SkillSlashCommandExtension,
    SlashCommandInvocation,
    ZettelkastenAgent,
    ZettelkastenAgentConfig,
    ZettelkastenContainer,
)
from zett.application.routes import agent as agent_routes
from zett.main import app


class ExampleSlashExtension:
    """Register one deterministic command without requiring a model."""

    name = "example"

    async def register(self, container: ZettelkastenContainer) -> None:
        container.register_slash_command(
            owner=self.name,
            name="example-command",
            description="Exercise the slash command container.",
            command_type="action",
            handler=self.handler,
        )

    @staticmethod
    async def handler(
        container: ZettelkastenContainer,
        invocation: SlashCommandInvocation,
    ) -> AsyncIterator[AgentEvent]:
        del container, invocation
        yield AgentEvent(
            AgentEventType.CUSTOM,
            session_id="slash-session",
            name="example_command",
            payload={"ok": True},
        )


def _invocation(message: UserContent = "/example-command inspect this") -> SlashCommandInvocation:
    return SlashCommandInvocation(
        session_id="slash-session",
        client=AgentClient.__new__(AgentClient),
        message=UserMessage(content=message),
        model=None,  # type: ignore[arg-type]
        config=AgentRunConfig(session_id="slash-session"),
        reasoning_effort=ReasoningEffort.MEDIUM,
        metadata={},
        tags={},
    )


async def test_container_registers_stable_slash_command_ids() -> None:
    first = await ZettelkastenAgent(
        ZettelkastenAgentConfig(
            "slash-session",
            extensions=(ExampleSlashExtension(),),
            mcp_config_path=None,
        )
    ).initialize()
    second = await ZettelkastenAgent(
        ZettelkastenAgentConfig(
            "slash-session",
            extensions=(ExampleSlashExtension(),),
            mcp_config_path=None,
        )
    ).initialize()

    first_command = first.slash_commands()[0]
    second_command = second.slash_commands()[0]
    assert first_command.name == "example-command"
    assert first_command.type == "action"
    assert first_command.id == second_command.id


async def test_container_executes_the_registered_handler() -> None:
    container = await ZettelkastenAgent(
        ZettelkastenAgentConfig(
            "slash-session",
            extensions=(ExampleSlashExtension(),),
            mcp_config_path=None,
        )
    ).initialize()
    command = container.slash_commands()[0]

    events = [event async for event in container.execute_slash_command(command.id, _invocation())]

    assert [event.name for event in events] == ["example_command"]
    assert events[0].payload == {"ok": True}


async def test_skill_extension_registers_and_expands_skill_commands(tmp_path) -> None:
    skill = tmp_path / "zett-review" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: zett-review\ndescription: Review changes.\n---\nRun focused checks first.",
        encoding="utf-8",
    )
    extension = SkillSlashCommandExtension((tmp_path,))
    captured: list[UserMessage] = []

    class CapturingContainer:
        async def stream_to_agent(
            self,
            invocation: SlashCommandInvocation,
            *,
            message: UserMessage | None = None,
        ) -> AsyncIterator[AgentEvent]:
            del invocation
            assert message is not None
            captured.append(message)
            yield AgentEvent(AgentEventType.CUSTOM, session_id="slash-session", name="captured")

        def register_slash_command(self, **kwargs):
            raise AssertionError(f"Unexpected registration: {kwargs}")

    commands = []

    class RegistrationContainer(CapturingContainer):
        def register_slash_command(self, **kwargs):
            commands.append(kwargs)
            return object()

    registration_container = RegistrationContainer()
    await extension.register(registration_container)
    assert [(command["name"], command["command_type"]) for command in commands] == [("zett-review", "skill")]

    handler = commands[0]["handler"]
    events = [event async for event in handler(registration_container, _invocation("/zett-review inspect the diff"))]

    assert [event.name for event in events] == ["captured"]
    assert len(captured) == 1
    prompt = captured[0].text
    assert "Run focused checks first." in prompt
    assert "inspect the diff" in prompt
    assert "invoked the /zett-review slash command" in prompt
    assert "loaded the zett-review skill" in prompt
    assert prompt.index("Skill instructions:") < prompt.index("User request:")
    assert captured[0].attributes["slash_command"] == {
        "name": "zett-review",
        "type": "skill",
        "raw_parts": [{"type": "text", "text": "/zett-review inspect the diff"}],
    }


async def test_skill_command_records_the_original_message_with_images(tmp_path) -> None:
    skill = tmp_path / "zett-review" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: zett-review\ndescription: Review changes.\n---\nRun focused checks first.",
        encoding="utf-8",
    )
    extension = SkillSlashCommandExtension((tmp_path,))
    captured: list[UserMessage] = []

    class CapturingContainer:
        async def stream_to_agent(
            self,
            invocation: SlashCommandInvocation,
            *,
            message: UserMessage | None = None,
        ) -> AsyncIterator[AgentEvent]:
            del invocation
            assert message is not None
            captured.append(message)
            yield AgentEvent(AgentEventType.CUSTOM, session_id="slash-session", name="captured")

        def register_slash_command(self, **kwargs):
            captured.append(kwargs)
            return object()

    container = CapturingContainer()
    await extension.register(container)
    handler = captured.pop()["handler"]
    image = ImageContent(source=ImageBytesSource(b"png", "image/png"), alt_text="diff.png")
    invocation = _invocation([TextContent("/zett-review check this diff"), image])

    [event async for event in handler(container, invocation)]

    assert captured[0].attributes["slash_command"]["raw_parts"] == [
        {"type": "text", "text": "/zett-review check this diff"},
        {
            "type": "image",
            "name": "diff.png",
            "mime_type": "image/png",
            "content_url": "data:image/png;base64,cG5n",
        },
    ]


async def test_duplicate_slash_command_registration_is_rejected() -> None:
    container = await ZettelkastenAgent(
        ZettelkastenAgentConfig("slash-session", extensions=(), mcp_config_path=None)
    ).initialize()

    kwargs = {
        "owner": "example",
        "name": "duplicate",
        "description": "First",
        "command_type": "action",
        "handler": ExampleSlashExtension.handler,
    }
    container.register_slash_command(**kwargs)
    with pytest.raises(ValueError, match="already registered"):
        container.register_slash_command(**kwargs)


def test_slash_command_endpoints_list_and_stream(monkeypatch) -> None:
    def configured_agent(session_id: str, runtime_settings):
        del runtime_settings
        return ZettelkastenAgentConfig(
            session_id,
            extensions=(ExampleSlashExtension(),),
            mcp_config_path=None,
        )

    monkeypatch.setattr(agent_routes, "_agent_config", configured_agent)

    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post(
            "/api/ai/providers",
            json={
                "name": "Slash provider",
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "https://example.invalid/v1",
                "api_key": "secret",
                "enabled": True,
            },
        ).json()["id"]
        listing = client.get(f"/api/agent/{session_id}/slash-commands")
        command = listing.json()[0]
        response = client.post(
            f"/api/agent/{session_id}/slash-commands/{command['id']}",
            json={
                "raw_content": "/example-command inspect this",
                "provider_id": provider_id,
                "reasoning_effort": "medium",
            },
        )

    assert listing.status_code == 200
    assert command["name"] == "example-command"
    assert command["type"] == "action"
    assert response.status_code == 200
    assert "event: custom" in response.text
    assert '"name":"example_command"' in response.text
