# Channel plugins

A channel plugin connects Zett to a chat platform. Zett owns everything around
it — the channel records, the login flow, the Agent sessions, deduplication, and
the message loop — and the plugin owns exactly one thing: talking to the
platform.

`zett-weixin` is the working reference, and `agim` is the SDK it is built on.

## The contract

```python
from zett.plugins import ChannelPlugin, PluginContext


class MyPlugin(ChannelPlugin):
    plugin_id = "my-platform"
    plugin_label = "My Platform"

    def __init__(self, context: PluginContext) -> None: ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def login(self) -> ChannelLoginChallenge: ...
    async def is_login(self) -> ChannelLoginState: ...
    async def submit_login_code(self, code: str) -> None: ...
    async def receive(self) -> ChannelInboundMessage: ...
    async def send(self, chat_id: str, text: str) -> None: ...
```

| Method | Contract |
| --- | --- |
| `login` | Begin an authorization flow and return the QR payload (`qr_content`, optional `qr_url`) |
| `is_login` | Report `pending`, `scanned`, `verify_required`, `connected`, `failed`, or `expired`; on success include `credentials` |
| `submit_login_code` | Record a pairing code the platform displayed; default is a no-op |
| `receive` | Await the next inbound message and return its text plus any media |
| `send` | Send one outbound message to a chat |

Zett polls `is_login` while the QR dialog is open, stores the returned
credentials, and only then creates the channel and starts the receive loop.
Editing a channel's policy never restarts the plugin, because those values are
read per turn; only the enabled flag starts or stops it.

## Persisting platform continuity

A channel plugin is stateless by design; the login handshake, the receive
cursor, and any per-chat reply token belong in `PluginContext.kv`, which Zett
prefixes with `channel:<plugin_id>:<scope>:`. That is how a QR handshake
survives a restart and how a long poll resumes where it stopped:

```python
    async def receive(self) -> ChannelInboundMessage:
        cursor = await self.context.kv.get("receive:cursor")
        result = await self._client.receive(cursor if isinstance(cursor, str) else None)
        await self.context.kv.set("receive:cursor", result.cursor)
        return ChannelInboundMessage(
            event_id=result.message.event_id,
            chat_id=result.message.chat_id,
            user_id=result.message.user_id,
            text=result.message.text,
            media=[...],
            reply_token=result.message.reply_token,
        )
```

`PluginContext.config` and `.secrets` carry what the login flow returned
(`ChannelCredentials`), so `start()` can build a client from them. The WeChat
plugin reads `config["base_url"]` and `secrets["bot_token"]` this way.

## Media

Deliver attachments as `ChannelMedia` with the bytes already downloaded and
decrypted. Zett stores them under the session's upload directory and decides
what the model receives:

- `kind` is `image`, `voice`, `file`, or `video`, and `media_type` carries the
  IANA type a shell command or an image tool needs.
- Images within the inline limit travel as real image content for a vision
  model; voice, files, video, and oversized images become a text reference
  naming the stored object key.
- Limits are re-applied by Zett rather than trusted from the plugin: at most
  `MAX_CHANNEL_MEDIA_ITEMS` (16) and `MAX_CHANNEL_MEDIA_BYTES` (256 MB) per
  attachment, `MAX_CHANNEL_MEDIA_TOTAL_BYTES` (256 MB) per message.
- Refusing an attachment is part of the contract, not an error: report it in
  `ChannelMediaRejection` with `ChannelMediaRejectionReason.TOO_LARGE` and Zett
  tells the sender the file is too large instead of running a turn over bytes
  nobody received.

An inbound message must carry text, media, or a rejection — a media-only message
is a valid turn, and the model decides whether it can use what arrived.

## Failure policy

Zett wraps every plugin call, and the policy differs per call because the
consequences differ:

| Call | On failure |
| --- | --- |
| construct / `start` | Skip that channel, keep starting the others |
| `login` | Raise `PluginError` (HTTP 502) |
| `is_login` | Record a failed login attempt |
| `receive` | Log and retry |
| `send` / `stop` / `submit_login_code` | Log only |

Cancellation is never swallowed. A reconnectable failure stays a reconnect:
`is_login` can report `pending` again, and a `receive` that raises is retried
rather than closing the channel.

## Writing one on `agim`

`agim` is a standalone, stateless SDK: one interface
(`login` / `is_login` / `receive` / `send`), one client per platform, no storage
and no host concepts. The WeChat plugin is a thin adapter over it — verify the
handshake state, translate agim's models into the channel contract, and keep
the cursor in KV.

Package it like any other plugin:

```toml title="pyproject.toml"
[project]
name = "zett-my-platform"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["zett>=0.1.0"]

[project.entry-points."zett.channels"]
my-platform = "zett_my_platform:MyPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install it into Zett's environment, restart, and it appears in
`GET /api/channels/plugins`, which is what the `Connect` dialog lists. A login
request may omit the platform only while exactly one plugin is installed, so
adding a second one is enough to make the picker appear.

[`backend/zett-weixin/src/zett_weixin/plugin.py`](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett-weixin/src/zett_weixin/plugin.py)
is a complete implementation to copy from, and the
[agim README](../agim.md) documents the SDK underneath it.
