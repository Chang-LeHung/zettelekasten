"""SSE projection and minimal zett-agent composition tests."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from zett_agent import (
    DEFAULT_MCP_CONFIG_PATH,
    DEFAULT_MCP_SERVER_KEYS,
    Agent,
    AgentEvent,
    AgentEventType,
    AgentMessage,
    AgentRunConfig,
    AssistantMessage,
    McpExtension,
    McpHttpServer,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    RawMessageRecord,
    SkillExtension,
    SQLiteSessionStorage,
    SystemMessage,
    ToolCall,
    ToolDefinition,
    ToolMessage,
    UserMessage,
    tool,
)

from zett.agent import (
    ContextCompositionExtension,
    ZettelkastenAgent,
    ZettelkastenAgentConfig,
    ZettelkastenEventDispatcher,
    context_composition,
    event_payload,
)
from zett.agent.tags import TagExtension
from zett.application.presentation import message_out
from zett.infra.agent_runtime import get_agent_runtime_storage


class StreamingModel:
    """Produce deterministic reasoning and text without external I/O."""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        assert request.messages[-1].text == "Hello"
        yield ModelEvent.reasoning("Think")
        yield ModelEvent.text("Hi")
        yield ModelEvent.completed(
            ModelResponse(
                AssistantMessage(content="Hi", reasoning="Think", provider="test", model="test-model"),
                finish_reason="stop",
                usage=ModelUsage(input_tokens=5, output_tokens=2, reasoning_tokens=1),
            )
        )


def decode_frame(frame: str) -> tuple[str, dict[str, object]]:
    """Decode the strict two-line JSON frame emitted by the dispatcher."""
    event_line, data_line = frame.strip().splitlines()
    return event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))


def raw_record(message: AssistantMessage | ToolMessage, sequence: int) -> RawMessageRecord:
    """Build a minimal persisted record for HTTP projection tests."""
    now = datetime.now(UTC)
    return RawMessageRecord(
        id=f"message-{sequence}",
        session_id="session-1",
        request_id="request-1",
        sequence=sequence,
        message=message,
        metadata={},
        tags={},
        started_at=now,
        completed_at=now,
        duration_ns=0,
        reasoning_started_at=None,
        reasoning_completed_at=None,
        reasoning_duration_ns=None,
        content_started_at=None,
        content_completed_at=None,
        content_duration_ns=None,
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=None,
        cache_write_tokens=None,
        reasoning_tokens=None,
        created_at=now,
        updated_at=now,
    )


def test_persisted_message_projection_keeps_tool_calls_and_results_correlated():
    call = ToolCall("call-1", "read_file", {"path": "README.md"})
    assistant = message_out(raw_record(AssistantMessage(reasoning="Inspect first", tool_calls=[call]), 1))
    result = message_out(
        raw_record(ToolMessage(tool_call_id=call.id, name=call.name, content='{"lines": 12}', success=True), 2)
    )

    assert assistant.tool_calls[0].model_dump() == {
        "id": "call-1",
        "name": "read_file",
        "arguments": {"path": "README.md"},
    }
    assert result.tool_call_id == "call-1"
    assert result.tool_name == "read_file"
    assert result.tool_success is True


async def test_agent_uses_create_agent_and_sends_ordered_sse_frames():
    frames: list[str] = []
    tasks: list[asyncio.Task[object] | None] = []

    async def send(frame: str) -> None:
        tasks.append(asyncio.current_task())
        frames.append(frame)

    owner = asyncio.current_task()
    agent = await ZettelkastenAgent.create(StreamingModel(), config=AgentRunConfig(session_id="session-1"))
    client = agent.client(ZettelkastenEventDispatcher(send))
    events = [event async for event in client.stream("Hello")]
    decoded = [decode_frame(frame) for frame in frames]

    assert [name for name, _ in decoded] == [event.type.value for event in events]
    assert all(task is owner for task in tasks)
    reasoning = next(payload for name, payload in decoded if name == "reasoning_delta")
    content = next(payload for name, payload in decoded if name == "text_delta")
    completed = next(payload for name, payload in decoded if name == "model_completed")
    assert reasoning == {"session_id": "session-1", "phase": "generating", "delta": "Think"}
    assert content == {"session_id": "session-1", "phase": "generating", "delta": "Hi"}
    assert completed["usage"] == {
        "input_tokens": 5,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 1,
    }


async def test_run_returns_answer_after_all_frames_are_sent():
    frames = []

    async def send(frame: str) -> None:
        frames.append(decode_frame(frame)[0])

    agent = await ZettelkastenAgent.create(StreamingModel())
    answer = await agent.client(ZettelkastenEventDispatcher(send)).run("Hello")
    assert answer.content == "Hi"
    assert frames[-1] == AgentEventType.RUN_COMPLETED.value


async def test_send_failure_propagates_and_stops_the_agent_stream():
    calls = 0

    async def send(_: str) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("SSE disconnected")

    agent = await ZettelkastenAgent.create(StreamingModel())
    with pytest.raises(RuntimeError, match="SSE disconnected"):
        await agent.client(ZettelkastenEventDispatcher(send)).run("Hello")
    assert calls == 1


async def test_one_agent_uses_request_owned_models_and_dispatchers() -> None:
    class NamedModel:
        def __init__(self, name: str) -> None:
            self.name = name

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            yield ModelEvent.text(self.name)
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content=self.name)))

    agent = await ZettelkastenAgent.create()
    received: dict[str, list[str]] = {"a": [], "b": []}

    async def run(session_id: str) -> str:
        async def send(frame: str) -> None:
            received[session_id].append(decode_frame(frame)[0])

        client = agent.client(ZettelkastenEventDispatcher(send))
        result = await client.run(
            "Hello",
            config=AgentRunConfig(session_id=session_id),
            model=NamedModel(session_id),
        )
        return result.content

    assert await asyncio.gather(run("a"), run("b")) == ["a", "b"]
    assert received["a"][-1] == AgentEventType.RUN_COMPLETED.value
    assert received["b"][-1] == AgentEventType.RUN_COMPLETED.value


async def test_factory_builds_a_fresh_agent_for_every_message_request() -> None:
    storage = get_agent_runtime_storage()
    first = await ZettelkastenAgentConfig("session-a", max_iterations=7).create(storage)
    second = await ZettelkastenAgentConfig("session-a", max_iterations=11).create(storage)

    assert second is not first
    assert first.agent.max_iterations == 7
    assert second.agent.max_iterations == 11


def test_factory_configuration_exposes_skill_and_mcp_defaults() -> None:
    config = ZettelkastenAgentConfig("defaults")

    assert config.skill_roots == ("~/.zett/skills",)
    assert config.mcp_servers == ()
    assert config.mcp_config_path == DEFAULT_MCP_CONFIG_PATH
    assert config.mcp_server_keys == DEFAULT_MCP_SERVER_KEYS
    assert config.compaction_max_tokens == 128_000
    assert config.compaction_keep_recent_tokens == 32_000


def test_context_composition_returns_only_normalized_semantic_ratios() -> None:
    request = ModelRequest(
        messages=[
            SystemMessage(content="Answer concisely."),
            SystemMessage(content="# Tool guidelines\n\n## read_file\n- Read before writing."),
            UserMessage(content="Inspect the project."),
            AssistantMessage(content="I will inspect it."),
            ToolMessage(tool_call_id="call-1", name="read_file", content='{"content":"README"}'),
            AgentMessage(content="Continue after inspection."),
        ],
        tools=[
            ToolDefinition(
                name="read_file",
                description="Read a file.",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            )
        ],
    )

    ratios = context_composition(request)

    assert set(ratios) == {
        "system_prompt",
        "tool_prompt",
        "tool_output",
        "user",
        "assistant",
    }
    assert all(0 < ratio < 1 for ratio in ratios.values())
    assert sum(ratios.values()) == pytest.approx(1)
    assert all("token" not in key for key in ratios)


async def test_context_composition_extension_is_registered_after_prompt_extensions(tmp_path) -> None:
    storage = SQLiteSessionStorage(tmp_path / "agent.db")
    try:
        agent = await ZettelkastenAgentConfig("context-composition").create(storage)
        extensions = agent.agent.extensions
        names = [extension.name for extension in extensions]
        assert any(isinstance(extension, TagExtension) for extension in extensions)
        assert names.index("ContextCompositionExtension") > names.index("ToolGuidelinesExtension")
    finally:
        await storage.close()


async def test_context_composition_streams_every_model_step_and_includes_tool_output() -> None:
    """The extension must follow the live hooks; it used to implement a removed API."""
    recorded: list[dict[str, float]] = []

    @tool(guidelines="Echo one required argument.")
    async def echo(text: str) -> str:
        """Return the supplied text unchanged.

        Args:
            text: Text to return.
        """
        return text

    class ToolModel:
        def __init__(self) -> None:
            self.step = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            self.step += 1
            if self.step == 1:
                yield ModelEvent.completed(
                    ModelResponse(AssistantMessage(tool_calls=(ToolCall("echo-1", "echo", {"text": "body" * 400}),)))
                )
                return
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="Answer")))

    async def recorder(session_id: str, ratios: dict[str, float]) -> None:
        assert session_id == "session-context"
        recorded.append(ratios)

    agent = await Agent.create(
        ToolModel(),
        config=AgentRunConfig("session-context"),
        extensions=[ContextCompositionExtension(recorder)],
        tools=[echo],
    )

    events = [event async for event in agent.stream("Question")]

    payloads = [event.payload for event in events if event.name == "context_composition"]
    assert len(payloads) == 4
    assert all(payload is not None and sum(payload.values()) == pytest.approx(1) for payload in payloads)
    assert payloads[0]["assistant"] == 0
    # The tool result only exists once its own model step finished.
    assert payloads[-1]["tool_output"] > 0
    assert recorded == payloads


async def test_factory_loads_default_user_skills_and_mcp_configuration(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    skill_path = home / ".zett" / "skills" / "zett-review" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: zett-review\ndescription: Review Zett changes.\n---\nRun focused checks.",
        encoding="utf-8",
    )
    mcp_path = home / ".zett" / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "docs": {
                        "type": "streamable-http",
                        "url": "https://docs.test/mcp",
                        "headers": {"Authorization": "Bearer secret"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    storage = SQLiteSessionStorage(tmp_path / "agent.db")
    try:
        agent = await ZettelkastenAgentConfig("configured-session").create(storage)

        skill = next(item for item in agent.agent.extensions if isinstance(item, SkillExtension))
        mcp = next(item for item in agent.agent.extensions if isinstance(item, McpExtension))
        assert [(item.name, item.path) for item in skill.skills] == [("zett-review", skill_path.resolve())]
        assert mcp.servers == (McpHttpServer("docs", "https://docs.test/mcp", {"Authorization": "Bearer secret"}),)
    finally:
        await storage.close()


async def test_factory_accepts_explicit_skill_and_mcp_configuration(tmp_path) -> None:
    skill_root = tmp_path / "project-skills"
    skill_path = skill_root / "project-review" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: project-review\ndescription: Review project changes.\n---\nInspect the diff.",
        encoding="utf-8",
    )
    storage = SQLiteSessionStorage(tmp_path / "agent.db")
    server = McpHttpServer("internal", "https://internal.test/mcp")
    try:
        agent = await ZettelkastenAgentConfig(
            "explicit-session",
            skill_roots=(skill_root,),
            mcp_servers=(server,),
            mcp_config_path=None,
        ).create(storage)

        skill = next(item for item in agent.agent.extensions if isinstance(item, SkillExtension))
        mcp = next(item for item in agent.agent.extensions if isinstance(item, McpExtension))
        assert [(item.name, item.path) for item in skill.skills] == [("project-review", skill_path.resolve())]
        assert mcp.servers == (server,)
    finally:
        await storage.close()


@pytest.mark.parametrize(
    ("content", "expected"),
    [('{"saved":true}', {"saved": True}), ("plain output", "plain output"), ("", "")],
)
def test_tool_results_are_forwarded_without_tool_specific_logic(content, expected):
    call = ToolCall("call-1", "any_tool", {"path": "notes.md"})
    message = ToolMessage(content=content, tool_call_id=call.id, name=call.name, success=True)
    payload = event_payload(
        AgentEvent(
            AgentEventType.TOOL_COMPLETED,
            session_id="session-1",
            tool_calls=[call],
            message=message,
        )
    )
    assert payload["tool_calls"] == [{"id": "call-1", "name": "any_tool", "arguments": {"path": "notes.md"}}]
    assert payload["message"] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "name": "any_tool",
        "success": True,
        "output": expected,
        "attributes": {},
    }


def test_server_tool_lifecycle_is_forwarded_without_local_tool_message():
    from zett_agent import ServerToolCall, ServerToolInputDelta, ServerToolResult

    started = event_payload(
        AgentEvent(
            AgentEventType.SERVER_TOOL_STARTED,
            session_id="session-1",
            server_tool_call=ServerToolCall("hosted-1", "web_fetch", {"url": "https://example.com"}),
        )
    )
    completed = event_payload(
        AgentEvent(
            AgentEventType.SERVER_TOOL_COMPLETED,
            session_id="session-1",
            server_tool_result=ServerToolResult("hosted-1", "web_fetch", {"status": 200}),
        )
    )
    input_delta = event_payload(
        AgentEvent(
            AgentEventType.SERVER_TOOL_INPUT_DELTA,
            session_id="session-1",
            server_tool_input_delta=ServerToolInputDelta("hosted-1", '{"url":"https://example.com"}'),
        )
    )

    assert started["server_tool_call"] == {
        "id": "hosted-1",
        "name": "web_fetch",
        "input": {"url": "https://example.com"},
    }
    assert completed["server_tool_result"] == {
        "call_id": "hosted-1",
        "name": "web_fetch",
        "output": {"status": 200},
        "error_code": None,
    }
    assert input_delta["server_tool_input_delta"] == {
        "call_id": "hosted-1",
        "delta": '{"url":"https://example.com"}',
    }


async def test_custom_event_keeps_name_and_payload_namespaces():
    frames = []

    async def send(frame: str) -> None:
        frames.append(decode_frame(frame))

    dispatcher = ZettelkastenEventDispatcher(send)
    await dispatcher.dispatch(
        AgentEvent(
            AgentEventType.CUSTOM,
            session_id="session-1",
            name="ask_user",
            payload={"question": "Continue?"},
        )
    )
    assert frames == [
        (
            "custom",
            {
                "session_id": "session-1",
                "phase": None,
                "name": "ask_user",
                "payload": {"question": "Continue?"},
            },
        )
    ]
