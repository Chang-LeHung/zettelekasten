# zett-weixin

面向个人微信的 Zett 渠道插件。它封装了无状态的 `agim` 微信 SDK 客户端，并通过 `zett.channels` 入口点组注册到 Zett，因此 Zett 能够发现它，并像驱动其他渠道插件一样驱动 `login` / `is_login` / `receive` / `send`。

```toml
[project.entry-points."zett.channels"]
wechat = "zett_weixin:WeChatPlugin"
```

插件把自身所需的连续性状态存放在 Zett 提供给它的键值存储中（通过 `PluginContext.kv`）：登录握手、接收游标，以及每个会话的回复上下文令牌。`agim` 自身不存储任何数据。
