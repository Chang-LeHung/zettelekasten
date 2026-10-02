# Agent plugins

An agent plugin adds to every conversation: tools the model can call, hooks
that watch each run, `/` commands, and `@` references. This page builds one
called `memory`, which lets Zett keep notes for you and find them again. Read
[Build a Zett plugin](index.md) first: it covers what Zett hands a plugin and
how to install one.

## The package

```text
zett-memory/
├── pyproject.toml
├── src/
│   └── zett_memory/
│       └── __init__.py
└── tests/
    └── test_memory.py
```

```toml title="pyproject.toml"
[project]
name = "zett-memory"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[project.entry-points."zett.agent"]
memory = "zett_memory:MemoryPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/zett_memory"]

[dependency-groups]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.26,<2", "zett==0.1.0"]

[tool.uv.sources]
zett = { path = "../zettelekasten/backend", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

The entry point is how Zett finds the plugin: `memory` is the plugin id, and
`zett_memory:MemoryPlugin` is the class Zett constructs. Keep `dependencies`
for what the plugin needs beyond Zett, such as a client for an outside
service, and point the `zett` path at your own Zett checkout.

## The whole plugin

The sections below walk through this file one part at a time.

```python title="src/zett_memory/__init__.py"
from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

from zett.agent.at_command import AtCommandItem, AtCommandSource, reference_handler
from zett.agent.slash import SlashCommandInvocation
from zett.plugins import AgentCommandRegistry, AgentPlugin, KVStorage, PluginContext
from zett_agent.agent import AgentRunContext
from zett_agent.events import AgentEvent
from zett_agent.messages import AssistantMessage, UserMessage
from zett_agent.tools.base import AgentTool, tool

NOTE = "note:"


def memory_tools(kv: KVStorage) -> tuple[AgentTool, ...]:
    """Build the plugin's tools around its storage."""

    @tool(guidelines=("Call it only when the user asks you to remember something.",))
    async def remember(note: str) -> str:
        """Keep one note in the user's memory.

        Args:
            note: The sentence to keep, in the user's words.
        """
        text = note.strip()
        if not text:
            raise ValueError("A note cannot be blank")
        note_id = uuid4().hex[:8]
        await kv.set(f"{NOTE}{note_id}", text)
        return f"Remembered as {note_id}"

    @tool(guidelines=("Search before you tell the user you do not know something they told you.",))
    async def recall(query: str, limit: int = 5) -> str:
        """Search the user's notes for a word or phrase.

        Args:
            query: Text to look for; matching ignores case.
            limit: The most notes to return.
        """
        needle = query.casefold()
        hits = [
            f"{key.removeprefix(NOTE)}: {value}"
            for key, value in await kv.iter_prefix(NOTE)
            if isinstance(value, str) and needle in value.casefold()
        ]
        return "\n".join(hits[:limit]) or "No matching notes."

    @tool(guidelines=("When the user references a memory-note, read it with this tool before you answer.",))
    async def read_note(note_id: str) -> str:
        """Read one note by its id.

        Args:
            note_id: The id that remember returned, or that a memory-note reference names.
        """
        note = await kv.get(f"{NOTE}{note_id}")
        if not isinstance(note, str):
            raise ValueError(f"No note {note_id}")
        return note

    return remember, recall, read_note


class NoteSource(AtCommandSource):
    """List the user's notes in the @ menu."""

    owner = "memory"  # the plugin id
    kind = "memory-note"  # the kind it is registered under

    def __init__(self, kv: KVStorage) -> None:
        self.kv = kv

    async def items(self, session_id: str) -> Sequence[AtCommandItem]:
        return [
            self.item(target_id=key.removeprefix(NOTE), label=value[:60], description=value)
            for key, value in await self.kv.iter_prefix(NOTE)
            if isinstance(value, str) and value.strip()
        ]

    async def verify(self, session_id: str, item: AtCommandItem) -> bool:
        return await self.kv.get(f"{NOTE}{item.target_id}") is not None


class MemoryPlugin(AgentPlugin):
    plugin_id = "memory"
    plugin_label = "External memory"

    def __init__(self, context: PluginContext) -> None:
        self.kv = context.kv
        self._tools = memory_tools(context.kv)

    def tools(self) -> Sequence[AgentTool]:
        return self._tools

    async def after_run(self, context: AgentRunContext, answer: AssistantMessage) -> None:
        # One instance serves every conversation, so key its state by conversation.
        key = f"runs:{context.config.session_id}"
        runs = await self.kv.get(key)
        await self.kv.set(key, (runs if isinstance(runs, int) else 0) + 1)

    async def register(self, registry: AgentCommandRegistry) -> None:
        registry.register_slash_command(
            name="recall",
            description="Search what you asked Zett to remember",
            command_type="memory",
            handler=self._recall,
        )
        registry.register_at_command(kind="memory-note", source=NoteSource(self.kv), handler=reference_handler())

    async def _recall(self, invocation: SlashCommandInvocation) -> AsyncIterator[AgentEvent]:
        request = invocation.message.text.strip()
        message = UserMessage(
            content=(
                "The user invoked the /recall command. Search their notes with memory__recall "
                f"and answer from what it finds.\n\nUser request:\n{request}"
            ),
            # The conversation shows what the user typed, not this instruction.
            attributes={
                "slash_command": {
                    "name": "recall",
                    "type": "memory",
                    "raw_parts": [{"type": "text", "text": request}],
                }
            },
        )
        async for event in invocation.prompt(message=message):
            yield event
```

## The plugin class

`MemoryPlugin` subclasses `AgentPlugin`, and Zett constructs it with a
`PluginContext`. `tools()` is the one method you must write; everything else
on this page is optional.

- **`plugin_id`** must match the entry-point name. Zett names your tools and
  commands with it and warns in the log when the two differ. A plugin that
  does not set it is skipped.
- **`plugin_label`** is the name the log shows. Leave it out to show the id.
- **One instance.** Zett builds the class once and uses that instance for every
  conversation, often for several at the same time. Keep state in `kv`, and key
  anything that belongs to one conversation by its id,
  `context.config.session_id`, as `after_run` does.
- **`start()` and `stop()`** run when Zett starts and stops, for anything you
  want to open once, such as a connection pool. Scheduled tasks run in a
  separate background process that builds its own instance and does not call
  `start()`, so open such resources the first time a tool needs them.

## Tools

A tool is a typed function with a docstring, turned into a tool by `@tool`.
The model reads the docstring and the guidelines to decide when to call it, so
write both for the model:

```python
@tool(guidelines=("Call it only when the user asks you to remember something.",))
async def remember(note: str) -> str:
    """Keep one note in the user's memory.

    Args:
        note: The sentence to keep, in the user's words.
    """
```

- **Description.** The first paragraph of the docstring. Every tool needs one.
- **Parameters.** Give every parameter a type annotation and describe it under
  `Args:`. Zett checks the model's arguments against the annotations before
  your function runs and rejects any argument the function does not declare.
  `*args` and `**kwargs` are not allowed, and neither is a name under `Args:`
  that the function does not take.
- **Guidelines.** At least one short rule about when to use the tool, or when
  not to. Pass them to `@tool(guidelines=...)`, or write a `Guidelines:`
  section in the docstring with one rule per line.
- **Snippet.** Optionally, an example call, as a `Snippet:` section or
  `@tool(snippet=...)`.

When a tool runs:

- **Return** a string, or any value JSON can represent, such as a dict or a
  list.
- **Raise** to report a failure. The model receives the error message as the
  tool's result and can try something else, and the conversation goes on.
- **Don't block.** An `async def` tool shares Zett with every other
  conversation, so await slow work instead of blocking on it. A plain `def`
  tool runs in a worker thread, which suits a library that blocks.

The model sees each tool as `<plugin_id>__<name>`, so `remember` becomes
`memory__remember`, and a plugin tool can never replace one of Zett's. Zett
asks for `tools()` at the start of every run, so build the tools once and
return the same ones. A tool that breaks one of the rules above raises an error
where it is defined. In this plugin that happens when Zett constructs it, so
the plugin is skipped and the log says why.

## Hooks

A hook is an `async` method that Zett calls at one point in a run. All of them
are optional.

| Hook | Called |
| --- | --- |
| `before_run(context)` | Once, before the first model call of a run. |
| `after_run(context, answer)` | Once, with the final answer of a successful run. |
| `on_success(context, answer)` | After every plugin's `after_run`. |
| `on_error(context, error)` | When a run fails, before the error is reported. |
| `before_turn(context)`, `after_turn(context)` | Around each model step and the tool calls it asks for. |
| `before_model(context, request)`, `after_model(context, response)` | With the request about to go to the provider, and with the response that came back. |
| `before_tool(context, call)`, `after_tool(context, call, result, error)` | Around each tool call, including one that fails. `error` is the exception, or `None`. |

`context` describes the run, and `context.config.session_id` identifies the
conversation. `answer` is the assistant's message, `call` is the tool call
with its `name` and `arguments`, and `result` is the message that carries the
tool's result. For type annotations, import `AgentRunContext` from
`zett_agent.agent`; `AssistantMessage`, `ToolCall`, and `ToolMessage` from
`zett_agent.messages`; and `ModelRequest` and `ModelResponse` from
`zett_agent.model`.

Hooks watch a run; they do not steer it. A hook cannot replace the user's
message or add to the system prompt, and it cannot answer a command approval
or a question Zett asked the user. When several plugins are installed, each
hook runs in every plugin, in order of entry-point name.

If a hook raises, the run stops with an error that names the plugin and the
hook, such as `Agent plugin 'memory' failed in after_run: …`. Raise only when
the run really cannot go on. For optional work, such as reporting a run to an
outside service, catch the failure instead of letting it end the run.

## `/` commands and `@` references

Register both in `register()`. Zett calls it every time it prepares a
conversation, so keep it to the `register_…` calls, with no network requests,
file reads, or other slow work. A mistake there, such as an invalid name or a
kind that is already taken, stops every message from being sent, with an error
that names your plugin, until you fix or remove the plugin.

### `/` commands

```python
registry.register_slash_command(
    name="recall",
    description="Search what you asked Zett to remember",
    command_type="memory",
    handler=self._recall,
)
```

- **`name`** is what the user types after `/`: lowercase letters, digits, and
  single hyphens. Zett's skills and every plugin share one menu, which lists
  each command even when two have the same name, so choose a name that is
  unlikely to clash.
- **`description`** is the line under the name in the menu.
- **`command_type`** is the small label beside it. Zett's own skills show
  `skill`.

When the user picks the command in the `/` menu and sends the message, Zett
calls the handler with a `SlashCommandInvocation`. `invocation.message` is the
user's message, including the `/recall` they typed. `_recall` turns it into an
instruction for the model, calls `invocation.prompt()` with that instruction,
and yields every event the run produces.

- Call `prompt()` exactly once; a second call raises an error. Call it with no
  argument to send the user's message as it is.
- The `slash_command` attribute keeps the conversation showing what the user
  typed instead of your instruction. `raw_parts` lists what to show, as
  `{"type": "text", "text": ...}` parts.
- `invocation.message.parts` also holds any images the user attached. This
  example sends only the text.

### `@` references

An `@` reference lets the user point at one of your items from the composer,
the way they point at an asset or an artifact. `NoteSource` describes the
items, and `register_at_command` adds it under its kind:

```python
registry.register_at_command(kind="memory-note", source=NoteSource(self.kv), handler=reference_handler())
```

- **`owner`** must be your plugin id, and **`kind`** must be the kind you
  register. Kinds use lowercase letters, digits, and single hyphens, and each
  kind belongs to one plugin: Zett already uses `asset` and `artifact`, and a
  kind another plugin registered first is refused.
- **`items(session_id)`** lists what the user can reference in that
  conversation. Zett calls it whenever it lists the conversation's `@` menu,
  so keep it quick. Build each entry with `self.item(...)`. `target_id` is your
  own id for the item. `label` and `description` are shown in the menu, must
  not be blank, and a description is shortened to 160 characters. The token
  the user sees is made from the label.
- **`verify(session_id, item)`** runs when the message is sent. Return `False`
  when the item no longer exists, and Zett refuses the message instead of
  sending the model a reference it cannot follow.

`reference_handler()` tells the model the kind and `target_id` of each item
the user referenced, then runs the turn. The item's content is not included,
so give the plugin a tool that reads one item, and say in that tool's
guideline when to use it, as `read_note` does.

## Test it

A plugin is an ordinary class, so you can test it without running Zett. Give
it an in-memory `KVStorage` and call its tools directly, with a dict of the
arguments the model would send.

```python title="tests/test_memory.py"
from zett.plugins import JsonValue, KVStorage, PluginContext

from zett_memory import MemoryPlugin


class MemoryKV(KVStorage):
    """In-memory stand-in for the KVStorage Zett hands to a plugin."""

    def __init__(self) -> None:
        self.data: dict[str, JsonValue] = {}

    async def get(self, key: str) -> JsonValue | None:
        return self.data.get(key)

    async def set(self, key: str, value: JsonValue) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> bool:
        return self.data.pop(key, None) is not None

    async def iter_prefix(self, prefix: str) -> list[tuple[str, JsonValue]]:
        return sorted((key, value) for key, value in self.data.items() if key.startswith(prefix))


def make_plugin() -> MemoryPlugin:
    return MemoryPlugin(PluginContext(plugin_id="memory", scope_id="agent", kv=MemoryKV(), config={}, secrets={}))


async def test_remember_then_recall() -> None:
    remember, recall, read_note = make_plugin().tools()
    note_id = (await remember({"note": "Local-first beats sync"})).removeprefix("Remembered as ")
    assert "Local-first beats sync" in await recall({"query": "SYNC"})
    assert await read_note({"note_id": note_id}) == "Local-first beats sync"
```

```bash
uv run pytest
```

A tool called this way checks its arguments as it does for the model, so a
missing or misspelled argument fails the test. To see a plugin inside a real
conversation, with its commands registered and its hooks called, Zett's own
[plugin tests](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett/tests/test_agent_plugins.py)
are a working example.

## Install and try it

Install the package next to Zett and restart Zett, as described in
[Install and check](index.md#install-and-check). The log should list
`memory (External memory)`. Then, in a conversation:

1. Ask Zett to remember a sentence. The conversation shows a call to
   `memory__remember`.
2. Type `/` and pick **recall** to search what you saved.
3. Type `@` to find your notes in the menu, and reference one in a question.
