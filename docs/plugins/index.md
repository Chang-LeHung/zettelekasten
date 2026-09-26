# Plugins

Zett is extended by installed packages, not by patches. A plugin is an ordinary
Python distribution that registers itself through an entry point; Zett discovers
it at startup, hands it the objects it may use, and contains its failures.

Two kinds exist today, each with its own entry-point group:

| Kind | Entry-point group | Base class | What it adds |
| --- | --- | --- | --- |
| Channel | `zett.channels` | `zett.plugins.ChannelPlugin` | A chat platform: login, receive, send |
| Agent | `zett.agent` | `zett.plugins.AgentPlugin` | Tools, lifecycle hooks, slash commands, `@` references inside a conversation |

A package can register both. `zett-weixin` is the reference channel plugin; the
[agent plugin guide](agent-plugins.md) walks through a complete `zett.agent`
package.

## The public API

Plugins import from `zett.plugins`, which is deliberately narrow — it never
pulls in Zett's application or infrastructure modules, so a plugin can depend on
it without an import cycle:

- contracts: `Plugin`, `PluginContext`, `KVStorage`, `NamespacedKV`, `PluginError`, `PluginLoadError`
- channel models: `ChannelPlugin`, `ChannelLoginChallenge`, `ChannelLoginState`, `ChannelCredentials`, `ChannelInboundMessage`, `ChannelMedia`, and the media limits
- agent contracts: `AgentPlugin`, `AgentCommandRegistry`, `AGENT_PLUGIN_API_VERSION`

Everything a hook or a tool receives is the runtime's own type, so a plugin
author reads one set of types (`AgentTool`, `ModelRequest`, `ModelResponse`,
`ToolCall`, `ToolMessage`, `AgentRunContext`) and never a second, parallel copy.

## Installing a plugin

Discovery reads the entry points of the environment Zett itself runs in, so a
package installed somewhere else is invisible.

```bash
# Zett installed as a uv tool: add the plugin to the tool environment
uv tool install --force --with zett-weixin ./backend

# Running from a source checkout: put it in the backend environment
uv add --directory backend zett-weixin
uv run --directory backend zett start --reload
```

Restart Zett afterwards. Startup logs name what loaded — channel plugins are
reported by `ChannelService.initialize`, agent plugins by
`Agent plugins loaded: …` — and `GET /api/channels/plugins` lists the channel
platforms the UI may offer.

## What the host guarantees

Plugin code is treated as untrusted third-party code at every boundary:

- **Discovery is best effort.** A broken entry point, a factory that raises, or a
  plugin that does not match its contract is skipped with a log line while the
  rest still load. One bad plugin never stops the application from starting.
- **Construction is guarded.** Blank ids, blank scopes, a store that is not a
  `KVStorage`, and constructor exceptions become `PluginLoadError` instead of
  leaking a plugin's own exception type.
- **Lifetime is process-wide.** One instance serves every conversation, started
  with the application and stopped on shutdown in reverse order.
- **Storage is namespaced.** A plugin persists only through
  `PluginContext.kv`, prefixed with its own kind, id, and scope — for agent
  plugins that is `agent:<plugin_id>:`. One plugin cannot read another's keys.
- **Failures stay visible.** A failing agent-plugin call is re-raised as
  `PluginError` naming the plugin and the hook, so the run fails being able to
  say which plugin broke, instead of continuing with a plugin that silently
  stopped working.
- **Capabilities are pinned.** Plugin tools are registered as
  `<plugin_id>__<tool>`, and every slash command and `@` kind carries the
  plugin's id as its owner, so a plugin can neither shadow a built-in name nor
  register under someone else's namespace.

## Deliberate limits

Two extension points stay with the host, because each needs its own contract
rather than a passthrough:

- Nothing can replace the incoming user message or inject into the leading
  system prefix. Every run declares its session id as the provider's prompt
  cache key, so a rebuilt prefix costs a full cache miss for the whole
  conversation.
- No plugin can answer an external event such as a shell approval, and the
  model-request and tool-call middlewares are not exposed, because they change
  what the provider receives and could bypass the approval boundary.

The runtime adapter is also appended after every built-in extension, so a plugin
cannot wrap persistence, safety, or logging.

## In-repo extensions are a different mechanism

Zett itself is composed of two internal extension points, which are not the
plugin API:

- `zett/agent/extensions/` holds adapters to the runtime's `AgentExtension`
  (artifacts, assets, tags, scheduled tasks, tracing, approval, compaction). This
  is where a built-in tool belongs.
- `zett/agent/plugins/` holds Zett's own container plugins: `ZettelkastenExt`
  implementations that register slash commands and `@` kinds from
  `ZettelkastenAgentConfig`. Built-in capabilities are registered here.

An installed agent plugin reaches the same container through
`AgentPlugin.register`, so a third-party command appears next to the built-in
ones without touching Zett's HTTP layer. If you are contributing a feature to
Zett itself rather than publishing a package, add it as an extension or a
container plugin, and read `AGENTS.md` for the boundaries that apply.

## Next

- [Agent plugins](agent-plugins.md) — tools, hooks, commands, and packaging.
- [Channel plugins](channel-plugins.md) — a new chat platform built on `agim`.
