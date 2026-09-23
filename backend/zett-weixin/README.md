# zett-weixin

A Zett channel plugin for personal WeChat. It wraps the stateless `agim` WeChat
SDK client and registers into Zett through the `zett.channels` entry-point
group, so Zett discovers it and drives `login` / `is_login` / `receive` /
`send` like any other channel plugin.

```toml
[project.entry-points."zett.channels"]
wechat = "zett_weixin:WeChatPlugin"
```

The plugin stores its own continuity in the key-value store Zett hands it
(through `PluginContext.kv`): the login handshake, the receive cursor, and each
conversation's reply context token. `agim` itself stores nothing.
