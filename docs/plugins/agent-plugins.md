# Agent plugins

An agent plugin adds capability inside a conversation: tools the model can call,
hooks into the run lifecycle, and browser-facing commands. It is a normal Python
package that declares the `zett.agent` entry point.

## Package layout

```text
zett-memory/
├── pyproject.toml
└── src/
    └── zett_memory/
        └── __init__.py
```

```toml title="pyproject.toml"
[project]
name = "zett-memory"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["zett>=0.1.0"]

[project.entry-points."zett.agent"]
memory = "zett_memory:MemoryPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/zett_memory"]
```

The entry-point name is the plugin id. Declaring `plugin_id` on the class with
the same value is good practice; if the two disagree, Zett logs a warning and
uses the entry-point name.

## A tool

```python title="src/zett_memory/__init__.py"
from collections.abc import Sequence

from zett.plugins import AgentPlugin, PluginContext
from zett_agent import AgentTool, tool


@tool(guidelines=("Call it when the user asks you to remember something.",))
async def remember(query: str, limit: int = 5) -> str:
    """Store one note in the external memory index.

    Args:
        query: Text to remember.
        limit: How many similar notes to return.
    """
    return f"remembered {query} ({limit})"


class MemoryPlugin(AgentPlugin):
    plugin_id = "memory"
    plugin_label = "External memory"

    def __init__(self, context: PluginContext) -> None:
        self.context = context

    def tools(self) -> Sequence[AgentTool]:
        return (remember,)

    async def start(self) -> None:
        """Open what the plugin needs before its first call."""

    async def stop(self) -> None:
        """Release what start() opened."""
```

Three things are worth knowing about tools:

- The decorator and the tool types come from the runtime package (`zett_agent`);
  the plugin class comes from Zett (`zett.plugins`). That split is deliberate —
  Zett owns the plugin contract, the runtime owns the hook arguments.
- The docstring is the tool's model-facing documentation. Its first line becomes
  the description, `Args:` documents each parameter, and `Snippet:` and
  `Guidelines:` sections are rendered beside the tool in prompt guidance. A tool
  needs at least one non-empty guideline.
- `remember` reaches the model as `memory__remember`. Namespacing is applied by
  Zett, not by the plugin, so a plugin can never shadow a built-in tool.

Tools are declared by `tools()` rather than registered per request, and the
instance is shared by every conversation. Keep per-conversation state in the
namespaced KV store instead of on `self`:

```python
    async def before_run(self, context) -> None:
        await self.context.kv.set("last-session", context.config.session_id)
        await self.context.kv.set(f"runs:{context.config.session_id}", 1)
```

`PluginContext.kv` is a `KVStorage` whose keys are already prefixed with
`agent:<plugin_id>:`, so two plugins, or two scopes, never collide.

## Lifecycle hooks

Every hook is optional and mirrors the runtime's own lifecycle:

| Hook | Called |
| --- | --- |
| `before_run` / `after_run` | Once around a run, `after_run` with the final answer |
| `on_success` / `on_error` | After a successful run, or before a failure returns to the caller |
| `before_turn` / `after_turn` | Around one model step and the tool calls it requested |
| `before_model` / `after_model` | With the outgoing `ModelRequest` and the incoming `ModelResponse` |
| `before_tool` / `after_tool` | Around each tool invocation, including a failed one |

```python
    async def after_tool(self, context, call, result, error) -> None:
        """Index one tool outcome in the external store."""
        if error is not None:
            return
        await self.context.kv.set(f"tool:{call.name}", {"ok": True})

    async def on_error(self, context, error) -> None:
        """Report a failed run to the memory service."""
```

Exceptions are the API here: raising from a hook fails the run and surfaces as
`PluginError` naming the plugin and the hook, because a plugin that stopped
working should be visible rather than silent.

## Commands and `@` references

`register()` lets a plugin add capabilities to the composer, using the same
container the built-in ones use:

```python
from collections.abc import AsyncIterator

from zett.agent.at_command import AtCommandItem, AtCommandSource, reference_handler
from zett.agent.slash import SlashCommandInvocation
from zett.plugins import AgentCommandRegistry
from zett_agent import AgentEvent, UserMessage


class MemorySource(AtCommandSource):
    owner = "memory"          # must equal the plugin id
    kind = "memory-note"      # must equal the registered kind

    def __init__(self, plugin: MemoryPlugin) -> None:
        self.plugin = plugin

    async def items(self, session_id: str) -> Sequence[AtCommandItem]:
        return [
            self.item(target_id=note_id, label=title, description=excerpt)
            for note_id, title, excerpt in await self.plugin.recent_notes()
        ]

    async def verify(self, session_id: str, item: AtCommandItem) -> bool:
        return await self.plugin.has_note(item.target_id)


class MemoryPlugin(AgentPlugin):
    ...

    async def register(self, registry: AgentCommandRegistry) -> None:
        registry.register_slash_command(
            name="recall",
            description="Search the memory index",
            command_type="memory-recall",
            handler=self._recall,
        )
        registry.register_at_command(
            kind="memory-note",
            source=MemorySource(self),
            # The default handler names the referenced item and runs the turn;
            # the content stays behind the tool that owns it.
            handler=reference_handler(),
        )

    def _recall(self, invocation: SlashCommandInvocation) -> AsyncIterator[AgentEvent]:
        async def stream() -> AsyncIterator[AgentEvent]:
            message = UserMessage(content=f"Search your memory index for: {invocation.message.text}")
            async for event in invocation.prompt(message=message):
                yield event

        return stream()
```

Rules the container enforces:

- `owner` and `kind` on an `@` source must match what it is registered for, and
  the registry pins the definition to the plugin's id. A plugin cannot register
  as another owner.
- Slash command names use lowercase letters, digits, and single hyphens; `@`
  kinds use the same shape.
- A turn is single use. `invocation.prompt()` streams it exactly once, so a
  handler rewrites the message and hands the turn back rather than calling the
  model itself.

## Testing a plugin

A plugin is a plain package, so most of it is testable without Zett: call
`tools()` and invoke a tool with a mapping of arguments, call a hook with a
small stand-in context, and exercise the services it talks to with a fake. The
reference harness in Zett's own suite is
[`backend/zett/tests/test_agent_plugins.py`](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett/tests/test_agent_plugins.py),
which builds a plugin, runs it through the adapter, and asserts tool names,
hook order, and the failure path.

For the integration itself, the checks that matter are: the package installs
into Zett's environment, the entry point resolves, `tools()` returns valid
tools, and startup logs the plugin under `Agent plugins loaded`.
