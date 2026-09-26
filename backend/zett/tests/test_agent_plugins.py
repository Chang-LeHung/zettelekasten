"""Discovery, adaptation, and lifetime of third-party agent plugins."""

from collections.abc import Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from zett_agent import (
    AgentRunConfig,
    AgentRunContext,
    AgentTool,
    AssistantMessage,
    ModelRequest,
    ModelResponse,
    ReasoningEffort,
    ToolCall,
    ToolMessage,
    UserMessage,
    tool,
)

from zett.agent.config import ZettelkastenAgentConfig
from zett.agent.extensions import AgentPluginExtension
from zett.agent.zettelkasten import ZettelkastenAgent
from zett.infra.plugins import AgentPluginService, LoadedAgentPlugin, ZettKVStorage, load_agent_plugins
from zett.plugins import AGENT_PLUGIN_API_VERSION, AgentPlugin, PluginError


@tool(guidelines=("Call it when the user asks you to remember something.",))
async def remember(query: str, limit: int = 5) -> str:
    """Store one note in the external memory index.

    Args:
        query: Text to remember.
        limit: How many similar notes to return.
    """
    return f"remembered {query} ({limit})"


class MemoryPlugin(AgentPlugin):
    """A plugin shaped like an external memory store."""

    plugin_id = "memory"
    plugin_label = "External memory"

    def __init__(
        self,
        context: Any = None,
        *,
        fail_tools: bool = False,
        fail_after_run: bool = False,
    ) -> None:
        self.context = context
        self.fail_tools = fail_tools
        self.fail_after_run = fail_after_run
        self.hooks: list[str] = []
        self.answers: list[AssistantMessage] = []
        self.requests: list[ModelRequest] = []
        self.responses: list[ModelResponse] = []
        self.calls: list[ToolCall] = []
        self.results: list[ToolMessage] = []
        self.errors: list[Exception] = []
        self.started = 0
        self.stopped = 0

    def tools(self) -> Sequence[AgentTool]:
        if self.fail_tools:
            raise RuntimeError("memory index unreachable")
        return (remember,)

    async def before_run(self, context: AgentRunContext) -> None:
        self.hooks.append(f"before_run:{context.config.session_id}")

    async def after_run(self, context: AgentRunContext, answer: AssistantMessage) -> None:
        if self.fail_after_run:
            raise RuntimeError("memory write failed")
        self.answers.append(answer)

    async def before_model(self, context: AgentRunContext, request: ModelRequest) -> None:
        self.requests.append(request)

    async def after_model(self, context: AgentRunContext, response: ModelResponse) -> None:
        self.responses.append(response)

    async def before_tool(self, context: AgentRunContext, call: ToolCall) -> None:
        self.calls.append(call)

    async def after_tool(
        self,
        context: AgentRunContext,
        call: ToolCall,
        result: ToolMessage,
        error: Exception | None,
    ) -> None:
        self.results.append(result)

    async def on_error(self, context: AgentRunContext, error: Exception) -> None:
        self.errors.append(error)

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


class RecordingContext:
    """Minimal request context: the adapter only registers tools on it."""

    def __init__(self) -> None:
        self.tools: dict[str, AgentTool] = {}

    def register_tool(self, tool: AgentTool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        self.tools[tool.name] = tool


def _run_context(session_id: str = "session-1") -> AgentRunContext:
    return AgentRunContext(
        config=AgentRunConfig(session_id=session_id, request_id="request-1"),
        state=None,  # type: ignore[arg-type]
        tools={},
    )


async def test_plugin_tools_are_registered_under_the_plugin_namespace() -> None:
    context = RecordingContext()

    await AgentPluginExtension([MemoryPlugin()]).on_tool(context)  # type: ignore[arg-type]

    assert list(context.tools) == ["memory__remember"]
    registered = context.tools["memory__remember"]
    assert registered.description == "Store one note in the external memory index."
    assert await registered.handler(query="zett", limit=2) == "remembered zett (2)"


async def test_a_plugin_that_cannot_return_tools_names_itself(captured_logs) -> None:
    """The run fails visibly, and the message says which plugin did it."""
    with pytest.raises(PluginError) as failure:
        await AgentPluginExtension([MemoryPlugin(fail_tools=True)]).on_tool(RecordingContext())  # type: ignore[arg-type]

    assert "'memory'" in str(failure.value)
    assert "memory index unreachable" in str(failure.value)
    assert any("plugin_id=memory" in message and "scope=tools" in message for message in captured_logs)


async def test_every_hook_receives_the_runtime_object() -> None:
    """Hooks get the runtime's own types, and Zett only adds namespacing."""
    plugin = MemoryPlugin()
    extension = AgentPluginExtension([plugin])
    context = _run_context()
    request = ModelRequest(messages=[UserMessage(content="hi")], reasoning_effort=ReasoningEffort.LOW)
    response = ModelResponse(AssistantMessage(content="hello"))
    call = ToolCall("call-1", "memory__remember", {"query": "x"})
    result = ToolMessage(tool_call_id="call-1", name="memory__remember", content="stored")
    failure = RuntimeError("provider exploded")

    await extension.before_run(context)
    await extension.after_run(context, response.message)
    await extension.before_model(context, request)
    await extension.after_model(context, response)
    await extension.before_tool(context, call)
    await extension.after_tool(context, call, result, None)
    await extension.on_error(context, failure)

    assert plugin.hooks == ["before_run:session-1"]
    assert plugin.answers == [response.message]
    assert plugin.requests == [request]
    assert plugin.responses == [response]
    assert plugin.calls == [call]
    assert plugin.results == [result]
    assert plugin.errors == [failure]


async def test_a_failing_hook_names_the_plugin(captured_logs) -> None:
    plugin = MemoryPlugin(fail_after_run=True)

    with pytest.raises(PluginError) as failure:
        await AgentPluginExtension([plugin]).after_run(_run_context(), AssistantMessage(content="answer"))

    assert "'memory'" in str(failure.value)
    assert "after_run" in str(failure.value)
    assert any("plugin_id=memory" in message and "scope=after_run" in message for message in captured_logs)


async def test_a_plugin_can_never_answer_external_events() -> None:
    """Approving a shell command stays the user's decision, not a plugin's."""
    extension = AgentPluginExtension([MemoryPlugin()])

    assert extension.accept(AgentRunConfig(session_id="session-1"), SimpleNamespace()) is False


@dataclass
class FakeEntry:
    """One installed entry point, without touching importlib metadata."""

    name: str
    factory: Any
    error: Exception | None = None

    def load(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.factory


def test_installed_plugins_load_and_broken_ones_are_skipped(captured_logs) -> None:
    class WrongApiPlugin(MemoryPlugin):
        plugin_id = "other"
        api_version = AGENT_PLUGIN_API_VERSION + 1

    class NotAPlugin:
        def __init__(self, context: Any) -> None:
            del context

    loaded = load_agent_plugins(
        entries=[
            FakeEntry("memory", MemoryPlugin),
            FakeEntry("exploding", MemoryPlugin, error=RuntimeError("import failed")),
            FakeEntry("other", WrongApiPlugin),
            FakeEntry("plain", NotAPlugin),
        ],
        kv=ZettKVStorage(),
    )

    assert [item.plugin_id for item in loaded] == ["memory"]
    assert loaded[0].label == "External memory"
    assert any("Agent plugins loaded: memory (External memory)" in message for message in captured_logs)
    assert sum("Skipping agent plugin" in message for message in captured_logs) == 3


async def test_plugin_storage_is_namespaced() -> None:
    """A plugin persists through its own prefix, so plugins cannot collide."""
    captured: dict[str, Any] = {}

    def factory(context: Any) -> MemoryPlugin:
        plugin = MemoryPlugin()
        plugin.context = context
        captured["plugin"] = plugin
        return plugin

    store = ZettKVStorage()
    load_agent_plugins(entries=[FakeEntry("memory", factory)], kv=store)
    context = captured["plugin"].context

    await context.kv.set("cursor", 7)
    assert await store.get("agent:memory:cursor") == 7


async def test_plugin_service_starts_and_stops_every_plugin(captured_logs) -> None:
    plugin = MemoryPlugin()

    class ExplodingPlugin(MemoryPlugin):
        plugin_id = "exploding"

        async def start(self) -> None:
            raise RuntimeError("start failed")

    service = AgentPluginService(
        loader=lambda: (
            LoadedAgentPlugin(plugin_id="memory", label="External memory", plugin=plugin),
            LoadedAgentPlugin(plugin_id="exploding", label="Exploding", plugin=ExplodingPlugin()),
        )
    )

    await service.start()
    await service.stop()

    assert plugin.started == 1 and plugin.stopped == 1
    assert any("plugin_id=exploding" in message and "failed to start" in message for message in captured_logs)


async def test_the_agent_loads_plugins_inside_its_own_extensions() -> None:
    agent = await ZettelkastenAgent(
        ZettelkastenAgentConfig(
            "session-plugins",
            agent_plugins=(MemoryPlugin(),),
            skill_roots=(),
            mcp_config_path=None,
        )
    ).initialize()

    names = [type(extension).__name__ for extension in agent.agent.extensions]
    assert "AgentPluginExtension" in names
    # Built-ins stay outermost, so a plugin cannot wrap persistence or safety.
    for builtin in (
        "SessionPersistenceExtension",
        "CompactionExtension",
        "ShellApprovalExtension",
        "TraceLogExtension",
    ):
        assert names.index("AgentPluginExtension") > names.index(builtin)
