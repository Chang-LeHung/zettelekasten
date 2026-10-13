# 构建 Zett 插件

插件可以为 Zett 的每个会话添加能力：模型可以调用的工具、`/` 命令、`@` 引用，
或是一个完整的聊天应用，让人们可以从中向 Zett 发送消息。插件就是普通的
Python 包。声明一个入口点，把包安装到 Zett 旁边，然后重启 Zett 即可。

| 你想要… | 构建… | 入口点组 |
| --- | --- | --- |
| 为 Zett 提供新工具、监视它的运行，或添加 `/` 命令和 `@` 引用 | [Agent 插件](agent-plugins.md) | `zett.agent` |
| 让人们通过其他聊天应用与 Zett 对话 | [渠道插件](channel-plugins.md) | `zett.channels` |

同一个包可以同时提供两者，声明两个入口点即可。

## 插件导入什么 {#what-a-plugin-imports}

- **`zett.plugins`** 包含基类（`AgentPlugin`、`ChannelPlugin`）、
  `PluginContext`、`KVStorage`、`PluginError`，以及通信渠道相关的模型。它是提供给插件的
  稳定接口。插件需要的其他 Zett 模块只有 `zett.agent.slash` 和
  `zett.agent.at_command`，分别用于 `/` 命令和 `@` 引用。
- **`zett_agent`** 是 Zett 所基于的 Agent 运行时。工具、消息和运行事件都是它的类型：
  来自 `zett_agent.tools.base` 的 `tool` 和 `AgentTool`，来自
  `zett_agent.messages` 的 `UserMessage`，来自 `zett_agent.events` 的
  `AgentEvent`，以及来自 `zett_agent.agent` 的 `AgentRunContext`。

这两者都随 Zett 一起提供，因此插件不必把它们列为运行时依赖。
请把 Zett 加入开发依赖组，这样测试和编辑器就能导入它：

```toml
[dependency-groups]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.26,<2", "zettelekasten==0.0.1"]

[tool.uv.sources]
zett = { path = "../zettelekasten/backend", editable = true }  # 你的 Zett 代码仓库
```

两篇指南都给出了完整的 `pyproject.toml`。

## Zett 交给插件什么 {#what-zett-hands-a-plugin}

Zett 构造你的插件类时会传入一个参数，即 `PluginContext`：

| 字段 | 内容 |
| --- | --- |
| `plugin_id` | 入口点名称，例如 `memory`。 |
| `scope_id` | Agent 插件为 `agent`。渠道插件则对应一次登录尝试或一个已连接的渠道。 |
| `kv` | 属于该插件及该作用域的持久化键值存储。 |
| `config`、`secrets` | 对于已连接的渠道，是其登录时返回的内容。登录过程中以及 Agent 插件中为空。 |

任何需要在重启后保留的数据，都请存放在 `kv` 中。它的方法都是异步的：

| 方法 | 作用 |
| --- | --- |
| `get(key)` | 返回已存储的值，或 `None`。 |
| `set(key, value)` | 存储兼容 JSON 的值：文本、数字、布尔值、`None`、列表和字典。 |
| `delete(key)` | 删除一个键，并返回该键此前是否存在。 |
| `iter_prefix(prefix)` | 返回某个前缀下的所有 `(key, value)` 键值对，按键排序。 |

请自行选择简短的键，例如 `note:42`。Zett 已经把每个插件的键与其他插件的键隔离开了。

## 安装与检查 {#install-and-check}

把包安装到与 Zett 相同的 Python 环境中，然后重启 Zett。安装在其他位置的包
永远不会被发现。

如果你是用 `make install` 安装的 Zett，请在 Zett 代码仓库的根目录运行：

```bash
uv tool install --force --with-editable /absolute/path/to/zett-memory ./backend
zett stop
zett start
```

插件会一直链接到它所在的文件夹，因此编辑之后，先后运行 `zett stop` 和
`zett start` 就会加载新代码。`make install` 会在不含你的插件的情况下重新安装
Zett，所以运行它之后需要再运行一次上面的命令。

如果你用 `make dev` 从源码运行 Zett，则应改为把插件添加到后端环境中。请使用绝对路径，
因为 `--directory` 会改变相对路径的起始目录：

```bash
uv add --directory backend --editable /absolute/path/to/zett-memory
```

这会把插件记录到 `backend/pyproject.toml` 和 `backend/uv.lock` 中；
分享你的改动时，请不要包含这些行。

然后检查 Zett 是否找到了它。用 `zett start --foreground` 启动 Zett，
即可在屏幕上查看日志，也可以打开 `~/.zettelekasten/logs/zett.log`：

```text
Agent plugins loaded: memory (External memory)
Channel plugins available: my-platform, wechat
```

无法导入或无法构造的插件会被跳过。日志会给出它的名称和错误信息，
Zett 的其余部分仍会正常启动。

已安装的渠道插件会出现在 **通信渠道 → 连接** 中。微信随 Zett 一起提供，
所以一旦你安装了其他平台，对话框就会询问要连接哪一个，并按标签逐一列出。

## 信任 {#trust}

插件作为 Python 代码在 Zett 内部运行，对你的文件、网络和产物库拥有与 Zett 本身相同的访问权限。
请只安装你信任的插件。Zett 把插件工具命名为 `<plugin_id>__<tool>`，这样插件就无法替换
内置工具；它还会隔离每个插件的存储，并在报告的每一次失败中指明是哪个插件，
但它不是沙箱。

不要把密钥写进日志行和工具结果：工具结果会发送给模型服务商。

如果想添加工具或命令，请从 [Agent 插件](agent-plugins.md)开始。
当你有一个能够登录、接收和发送消息的聊天平台客户端时，再去构建
[渠道插件](channel-plugins.md)。
