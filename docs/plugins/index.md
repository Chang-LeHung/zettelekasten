# Build a Zett plugin

A plugin adds something to Zett for every conversation: tools the model can
call, a `/` command, an `@` reference, or a whole chat app people can message
Zett from. Plugins are ordinary Python packages. Declare an entry point,
install the package next to Zett, and restart Zett.

| You want to… | Build a… | Entry point group |
| --- | --- | --- |
| Give Zett new tools, watch its runs, or add `/` commands and `@` references | [Agent plugin](agent-plugins.md) | `zett.agent` |
| Let people talk to Zett from another chat app | [Channel plugin](channel-plugins.md) | `zett.channels` |

One package may provide both; declare both entry points.

## What a plugin imports

- **`zett.plugins`** holds the base classes (`AgentPlugin`, `ChannelPlugin`),
  `PluginContext`, `KVStorage`, `PluginError`, and the channel models. It is the
  stable surface for plugins. The only other Zett modules a plugin needs are
  `zett.agent.slash` and `zett.agent.at_command`, for `/` commands and `@`
  references.
- **`zett_agent`** is the agent runtime Zett is built on. Tools, messages, and
  run events are its types: `tool` and `AgentTool` from `zett_agent.tools.base`,
  `UserMessage` from `zett_agent.messages`, `AgentEvent` from
  `zett_agent.events`, and `AgentRunContext` from `zett_agent.agent`.

Both arrive with Zett, so a plugin does not list them as runtime dependencies.
Add Zett to a development dependency group instead, so that your tests and
your editor can import it:

```toml
[dependency-groups]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.26,<2", "zettelekasten==0.0.1"]

[tool.uv.sources]
zett = { path = "../zettelekasten/backend", editable = true }  # your Zett checkout
```

The two guides each show a complete `pyproject.toml`.

## What Zett hands a plugin

Zett constructs your plugin class with one argument, a `PluginContext`:

| Field | What it holds |
| --- | --- |
| `plugin_id` | The entry-point name, such as `memory`. |
| `scope_id` | `agent` for an agent plugin. For a channel plugin, one login attempt or one connected channel. |
| `kv` | Durable key-value storage that belongs to this plugin and scope. |
| `config`, `secrets` | For a connected channel, what its login returned. Empty during a login and for an agent plugin. |

Keep anything that must survive a restart in `kv`. Its methods are async:

| Method | Does |
| --- | --- |
| `get(key)` | Returns the stored value, or `None`. |
| `set(key, value)` | Stores a JSON-compatible value: text, numbers, booleans, `None`, lists, and dicts. |
| `delete(key)` | Removes a key and returns whether it existed. |
| `iter_prefix(prefix)` | Returns every `(key, value)` pair under a prefix, sorted by key. |

Choose short keys of your own, such as `note:42`. Zett already keeps each
plugin's keys apart from every other plugin's.

## Install and check

Install the package into the same Python environment as Zett, then restart
Zett. A package installed anywhere else is never found.

If you installed Zett with `make install`, run this from the root of your Zett
checkout:

```bash
uv tool install --force --with-editable /absolute/path/to/zett-memory ./backend
zett stop
zett start
```

The plugin stays linked to its folder, so after you edit it, `zett stop` and
`zett start` load the new code. `make install` reinstalls Zett without your
plugin; run the command again after it.

If you run Zett from source with `make dev`, add the plugin to the backend
environment instead. Use an absolute path, because `--directory` changes the
folder that relative paths start from:

```bash
uv add --directory backend --editable /absolute/path/to/zett-memory
```

This records the plugin in `backend/pyproject.toml` and `backend/uv.lock`;
leave those lines out of changes you share.

Then check that Zett found it. Start Zett with `zett start --foreground` to
watch the log on screen, or open `~/.zettelekasten/logs/zett.log`:

```text
Agent plugins loaded: memory (External memory)
Channel plugins available: my-platform, wechat
```

A plugin that cannot be imported or constructed is skipped. The log names it
and shows the error, and the rest of Zett starts normally.

An installed channel plugin becomes available in **Channels → Connect**.
WeChat ships with Zett, so once you install another platform the dialog asks
which one to connect, listing each by its label.

## Trust

A plugin runs as Python code inside Zett, with the same access to your files,
your network, and your library as Zett itself. Install only plugins you trust.
Zett names plugin tools `<plugin_id>__<tool>` so that a plugin cannot replace a
built-in tool, keeps every plugin's storage apart, and names the plugin in
every failure it reports, but it is not a sandbox.

Keep secrets out of log lines and tool results: a tool result goes to the
model provider.

Start with [an agent plugin](agent-plugins.md) to add a tool or a command.
Build [a channel plugin](channel-plugins.md) when you have a chat platform
client that can log in, receive, and send.
