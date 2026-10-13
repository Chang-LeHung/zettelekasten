# Agent 插件

Agent 插件可以为每个会话添加能力：模型可以调用的工具、监视每次运行的钩子、`/` 命令和
`@` 引用。本页将构建一个名为 `memory` 的插件，它能让 Zett 为你记笔记，并在需要时再找出来。
请先阅读[构建 Zett 插件](index.md)：它介绍了 Zett 交给插件什么，以及如何安装插件。

## 包结构 {#the-package}

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
dev = ["pytest>=8,<9", "pytest-asyncio>=0.26,<2", "zettelekasten==0.0.1"]

[tool.uv.sources]
zett = { path = "../zettelekasten/backend", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

入口点是 Zett 发现插件的方式：`memory` 是插件 id，`zett_memory:MemoryPlugin` 是
Zett 要构造的类。`dependencies` 留给插件在 Zett 之外所需的依赖，例如外部服务的客户端；
同时请把 `zett` 的路径指向你自己的 Zett 代码仓库。

## 完整插件 {#the-whole-plugin}

下面的各节会逐段讲解这个文件。

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

    owner = "memory"  # 插件 id
    kind = "memory-note"  # 它注册时使用的类型

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
        # 同一个实例服务所有会话，因此要用会话 id 作为状态的键。
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
            # 会话中显示的是用户输入的内容，而不是这条指令。
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

## 插件类 {#the-plugin-class}

`MemoryPlugin` 继承自 `AgentPlugin`，Zett 会传入一个 `PluginContext` 来构造它。
`tools()` 是唯一必须编写的方法；本页中的其他一切都是可选的。

- **`plugin_id`** 必须与入口点名称一致。Zett 用它来命名你的工具和命令，
  两者不一致时会在日志中发出警告。没有设置它的插件会被跳过。
- **`plugin_label`** 是日志中显示的名称。省略它则显示 id。
- **只有一个实例。** Zett 只构造一次这个类，并把该实例用于所有会话，
  通常还会同时服务多个会话。请把状态保存在 `kv` 中，并且任何只属于某个会话的数据，
  都要用会话 id（`context.config.session_id`）作为键，就像 `after_run` 那样。
- **`start()` 和 `stop()`** 会在 Zett 启动和停止时运行，适合放置只需打开一次的资源，
  例如连接池。定时任务运行在单独的后台进程中，该进程会构造自己的实例，
  并且不会调用 `start()`，所以这类资源请在工具第一次需要时再打开。

## 工具 {#tools}

工具是一个带类型标注和文档字符串的函数，由 `@tool` 转换为工具。
模型会阅读文档字符串和使用准则来决定何时调用它，因此请面向模型来编写这两者：

```python
@tool(guidelines=("Call it only when the user asks you to remember something.",))
async def remember(note: str) -> str:
    """Keep one note in the user's memory.

    Args:
        note: The sentence to keep, in the user's words.
    """
```

- **描述。** 文档字符串的第一段。每个工具都需要有描述。
- **参数。** 为每个参数添加类型标注，并在 `Args:` 下描述它。Zett 会在你的函数运行之前，
  根据这些标注检查模型传入的参数，并拒绝函数未声明的任何参数。
  不允许使用 `*args` 和 `**kwargs`，`Args:` 下也不能出现函数没有接收的名称。
- **准则。** 至少一条简短的规则，说明何时使用该工具，或何时不该使用。
  可以把它们传给 `@tool(guidelines=...)`，也可以在文档字符串中写一个 `Guidelines:`
  部分，每行一条规则。
- **示例。** 可选，一个示例调用，写成 `Snippet:` 部分或 `@tool(snippet=...)`。

工具运行时：

- **返回** 一个字符串，或任何 JSON 能表示的值，例如字典或列表。
- **抛出异常** 来报告失败。模型会把错误消息当作该工具的结果收到，
  可以尝试别的方式，会话也会继续进行。
- **不要阻塞。** `async def` 工具与其他所有会话共享 Zett，因此遇到耗时的操作要用 await 等待，
  而不是阻塞在上面。普通的 `def` 工具会在工作线程中运行，适合会阻塞的库。

模型看到的每个工具都是 `<plugin_id>__<name>`，所以 `remember` 会变成
`memory__remember`，插件工具也就永远无法替换 Zett 自带的工具。Zett 在每次运行开始时都会调用 `tools()`，
所以请只构建一次工具，并每次返回同样的这些工具。违反上述任何规则的工具，会在定义它的地方抛出错误。
在这个插件中，这发生在 Zett 构造它的时候，因此插件会被跳过，日志中会说明原因。

## 钩子 {#hooks}

钩子是 Zett 在运行中的某个时间点调用的 `async` 方法。它们全部是可选的。

| 钩子 | 调用时机 |
| --- | --- |
| `before_run(context)` | 一次，在一次运行的第一次模型调用之前。 |
| `after_run(context, answer)` | 一次，在一次成功运行得到最终回答时，并传入该回答。 |
| `on_success(context, answer)` | 在所有插件的 `after_run` 之后。 |
| `on_error(context, error)` | 运行失败时，在报告错误之前。 |
| `before_turn(context)`、`after_turn(context)` | 围绕每个模型步骤及其请求的工具调用。 |
| `before_model(context, request)`、`after_model(context, response)` | 分别在请求即将发往服务商时，以及响应返回之后，并传入相应的请求和响应。 |
| `before_tool(context, call)`、`after_tool(context, call, result, error)` | 围绕每次工具调用，包括失败的调用。`error` 是异常，或为 `None`。 |

`context` 描述这次运行，`context.config.session_id` 标识所属会话。`answer` 是助手的消息，
`call` 是带有 `name` 和 `arguments` 的工具调用，`result` 是携带工具结果的消息。
如需类型标注，请从 `zett_agent.agent` 导入 `AgentRunContext`；
从 `zett_agent.messages` 导入 `AssistantMessage`、`ToolCall` 和 `ToolMessage`；
从 `zett_agent.model` 导入 `ModelRequest` 和 `ModelResponse`。

钩子只是监视运行，不会操控它。钩子无法替换用户的消息，也无法向系统提示词添加内容，
还不能回应命令审批，或 Zett 向用户提出的问题。安装了多个插件时，每个钩子都会在每个插件中运行，
顺序按入口点名称排列。

如果钩子抛出异常，运行会因一个指明插件和钩子的错误而停止，例如
`Agent plugin 'memory' failed in after_run: …`。只有在运行确实无法继续时才抛出异常。
对于可选的工作，例如把一次运行上报给外部服务，请捕获失败，而不是让它终止运行。

## `/` 命令和 `@` 引用 {#commands-and-references}

两者都在 `register()` 中注册。Zett 每次准备会话时都会调用它，因此请只在其中放 `register_…` 调用，
不要发起网络请求、读取文件或做其他耗时的工作。这里的错误，例如无效的名称或已被占用的类型，
会导致所有消息都无法发送，并给出指明你的插件的错误，直到你修复或移除该插件为止。

### `/` 命令 {#commands}

```python
registry.register_slash_command(
    name="recall",
    description="Search what you asked Zett to remember",
    command_type="memory",
    handler=self._recall,
)
```

- **`name`** 是用户在 `/` 之后输入的内容：小写字母、数字和单个连字符。Zett 的技能和所有插件共用同一个菜单，
  即使两个命令同名，菜单也会把它们都列出来，所以请选择不太可能冲突的名称。
- **`description`** 是菜单中名称下方的那一行。
- **`command_type`** 是它旁边的小标签。Zett 自带的技能显示为 `skill`。

当用户在 `/` 菜单中选中该命令并发送消息时，Zett 会用一个 `SlashCommandInvocation` 调用处理函数。
`invocation.message` 是用户的消息，包含他们输入的 `/recall`。`_recall` 把它转换成给模型的指令，
用该指令调用 `invocation.prompt()`，并产出这次运行生成的每个事件。

- 只能调用一次 `prompt()`；第二次调用会抛出错误。不带参数调用，则按原样发送用户的消息。
- `slash_command` 属性让会话显示用户输入的内容，而不是你的指令。`raw_parts` 列出要显示的内容，
  形式为 `{"type": "text", "text": ...}` 片段。
- `invocation.message.parts` 中也包含用户附加的所有图片。这个示例只发送文本。

### `@` 引用 {#references}

`@` 引用让用户可以在输入框中指向你的某个条目，就像指向一个资源或一个产物那样。
`NoteSource` 描述这些条目，`register_at_command` 把它按类型添加进去：

```python
registry.register_at_command(kind="memory-note", source=NoteSource(self.kv), handler=reference_handler())
```

- **`owner`** 必须是你的插件 id，**`kind`** 必须是你注册的类型。类型使用小写字母、数字和单个连字符，
  每个类型只属于一个插件：Zett 已经使用了 `asset` 和 `artifact`，
  而其他插件已先注册的类型会被拒绝。
- **`items(session_id)`** 列出用户在该会话中可以引用的内容。Zett 每次列出该会话的 `@` 菜单时都会调用它，
  所以要保持快速。请用 `self.item(...)` 构建每个条目。`target_id` 是你自己给条目定的 id。
  `label` 和 `description` 会显示在菜单中，不能为空白，且描述会被截短到 160 个字符。
  用户看到的标记由 label 生成。
- **`verify(session_id, item)`** 在发送消息时运行。当该条目已不存在时返回 `False`，
  Zett 会拒绝这条消息，而不是向模型发送一个它无法跟进的引用。

`reference_handler()` 会告诉模型用户所引用的每个条目的类型和 `target_id`，然后运行这一轮。
条目的内容不会被包含在内，所以请为插件提供一个读取单个条目的工具，并在该工具的准则中说明何时使用它，
就像 `read_note` 那样。

## 测试 {#test-it}

插件就是普通的类，所以无需运行 Zett 就能测试它。给它一个内存中的 `KVStorage`，
并直接调用它的工具，传入一个包含模型会发送的参数的字典。

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

以这种方式调用的工具，会像处理模型传入的参数那样检查参数，所以缺失或拼错的参数会让测试失败。
如果想在真实会话中查看插件，包括它注册的命令和被调用的钩子，Zett 自己的
[插件测试](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett/tests/test_agent_plugins.py)
就是一个可用的示例。

## 安装并试用 {#install-and-try-it}

把包安装到 Zett 旁边并重启 Zett，方法见
[安装与检查](index.md#install-and-check)。日志中应列出
`memory (External memory)`。然后在一个会话中：

1. 让 Zett 记住一句话。会话中会显示一次对 `memory__remember` 的调用。
2. 输入 `/` 并选择 **recall**，搜索你保存的内容。
3. 输入 `@`，在菜单中找到你的笔记，并在提问时引用其中一条。
