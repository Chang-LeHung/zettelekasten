# Channel plugins

A channel plugin connects Zett to a chat platform, so people can message Zett
from that app. You write three things against the platform: logging in,
receiving a message, and sending a reply. Zett does the rest: the **Connect**
dialog and its QR code, one conversation per chat, the model run, saving
attachments, and retrying. Read [Build a Zett plugin](index.md) first.

The WeChat plugin that ships with Zett is a complete channel plugin. This page
builds a smaller one for a made-up platform, *My Platform*.

## The package

```text
zett-my-platform/
├── pyproject.toml
├── src/
│   └── zett_my_platform/
│       └── __init__.py
└── tests/
    └── test_plugin.py
```

```toml title="pyproject.toml"
[project]
name = "zett-my-platform"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["myplatform"]  # your platform's SDK

[project.entry-points."zett.channels"]
my-platform = "zett_my_platform:MyPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/zett_my_platform"]

[dependency-groups]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.26,<2", "zett==0.1.0"]

[tool.uv.sources]
zett = { path = "../zettelekasten/backend", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

The entry-point name, `my-platform`, is the platform's id. Zett stores it with
every channel connected through the plugin, so keep it once people use the
plugin, and set the class's `plugin_id` to the same value. `plugin_label` is
the name people see in the **Connect** dialog and on each channel card.

## How Zett uses the plugin

Zett builds two kinds of instances from your class.

- **A login instance** is built when someone presses **Generate QR code**. Its
  `config` and `secrets` are empty, and Zett never calls `start()` on it. Zett
  calls `login()` once, then `is_login()` about once a second while the dialog
  is open, and `stop()` when the attempt ends.
- **A channel instance** is built for each enabled channel: when Zett starts,
  when a login succeeds, and when someone turns a channel back on. It receives
  the `config` and `secrets` its login returned. Zett calls `start()`, then
  `receive()` in a loop and `send()` with each reply, and `stop()` when the
  channel is turned off or deleted, or Zett stops.

Every instance has its own `kv`. A channel cannot read what its login stored,
so the credentials are the only thing passed from one to the other. Someone
can connect several accounts on the same platform, each as its own channel,
with its own instance.

| Method | Required | Zett calls it |
| --- | --- | --- |
| `login()` | Yes | Once per login attempt, for the QR code to show. |
| `is_login()` | Yes | About once a second during a login attempt, for where the login stands. |
| `submit_login_code(code)` | No | Before each poll, once the user has typed a pairing code. |
| `start()` | Yes | When a channel instance starts. Open your client from `config` and `secrets`. |
| `receive()` | Yes | In a loop, for the next message. |
| `send(chat_id, text)` | Yes | With each reply. |
| `stop()` | Yes | When an instance is done. Close whatever `login()` or `start()` opened. |

## The whole plugin

`myplatform` stands for your platform's SDK, and its calls are invented for
this page: `start_login()` returns a QR code and the state needed to check on
it, `check_login()` reports how the login is going, `next_update()` waits for
the next message after a cursor, and `send()` replies. The sections below walk
through the file.

```python title="src/zett_my_platform/__init__.py"
import myplatform  # stands for your platform's SDK
from zett.plugins import (
    ChannelCredentials,
    ChannelInboundMessage,
    ChannelLoginChallenge,
    ChannelLoginState,
    ChannelLoginStatus,
    ChannelMedia,
    ChannelMediaKind,
    ChannelPlugin,
    PluginContext,
)

HANDSHAKE = "login:handshake"
PAIRING_CODE = "login:pairing_code"
CURSOR = "receive:cursor"

#: My Platform's login states in Zett's terms; "confirmed" is handled on its own.
LOGIN_STATUS = {
    "waiting": ChannelLoginStatus.PENDING,
    "scanned": ChannelLoginStatus.SCANNED,
    "needs_code": ChannelLoginStatus.VERIFY_REQUIRED,
    "denied": ChannelLoginStatus.FAILED,
    "timed_out": ChannelLoginStatus.EXPIRED,
}


def reply_key(chat_id: str) -> str:
    return f"reply:{chat_id}"


class MyPlugin(ChannelPlugin):
    plugin_id = "my-platform"
    plugin_label = "My Platform"

    def __init__(self, context: PluginContext) -> None:
        self.context = context
        # An instance runs either one login or one channel, so one client serves both.
        self._client: myplatform.Client | None = None

    async def login(self) -> ChannelLoginChallenge:
        handshake = await self._login_client().start_login()
        await self.context.kv.set(HANDSHAKE, handshake.state)
        return ChannelLoginChallenge(qr_content=handshake.qr_content, qr_url=handshake.qr_url)

    async def submit_login_code(self, code: str) -> None:
        if code.strip():
            await self.context.kv.set(PAIRING_CODE, code.strip())

    async def is_login(self) -> ChannelLoginState:
        handshake = await self.context.kv.get(HANDSHAKE)
        if handshake is None:
            return ChannelLoginState(
                status=ChannelLoginStatus.EXPIRED,
                message="Login session expired; request a new QR code.",
            )
        code = await self.context.kv.get(PAIRING_CODE)
        result = await self._login_client().check_login(
            handshake, pairing_code=code if isinstance(code, str) else None
        )
        if result.status != "confirmed":
            return ChannelLoginState(status=LOGIN_STATUS[result.status], message=f"My Platform: {result.status}")
        return ChannelLoginState(
            status=ChannelLoginStatus.CONNECTED,
            message="Connected",
            credentials=ChannelCredentials(config={"bot_id": result.bot_id}, secrets={"token": result.token}),
        )

    async def start(self) -> None:
        token = self.context.secrets.get("token")
        if not token:
            raise ValueError("My Platform needs a token; connect the channel again")
        self._client = myplatform.Client(token=token)

    async def receive(self) -> ChannelInboundMessage:
        client = self._channel_client()
        while True:
            cursor = await self.context.kv.get(CURSOR)
            update = await client.next_update(cursor if isinstance(cursor, str) else None)
            await self.context.kv.set(CURSOR, update.cursor)
            message = update.message
            if not message.text.strip() and not message.photos:
                continue  # nothing to answer, such as a sticker
            if message.reply_context:
                await self.context.kv.set(reply_key(message.chat_id), message.reply_context)
            return ChannelInboundMessage(
                event_id=message.id,
                chat_id=message.chat_id,
                user_id=message.sender_id,
                text=message.text,
                media=[
                    ChannelMedia(kind=ChannelMediaKind.IMAGE, media_type=photo.mime_type, data=photo.data)
                    for photo in message.photos
                ],
            )

    async def send(self, chat_id: str, text: str) -> None:
        context = await self.context.kv.get(reply_key(chat_id))
        await self._channel_client().send(
            chat_id, text, reply_context=context if isinstance(context, str) else None
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _login_client(self) -> myplatform.Client:
        if self._client is None:
            self._client = myplatform.Client()  # signed out, for logging in
        return self._client

    def _channel_client(self) -> myplatform.Client:
        if self._client is None:
            raise RuntimeError("My Platform channel is not started")
        return self._client
```

## Logging in

`login()` starts an attempt and returns a `ChannelLoginChallenge`.
`qr_content` is the text Zett draws as the QR code, usually a link the
platform's app opens. The optional `qr_url` adds an **Open link** button for
someone who cannot scan, for example because they are already on their phone.
Keep whatever the attempt needs later, such as the platform's login state, in
`kv`.

While the dialog stays open, Zett calls `is_login()` about once a second for up
to five minutes. Return a `ChannelLoginState` with one of six statuses. The
dialog shows its own text for each one:

| Status | The dialog shows |
| --- | --- |
| `pending` | Waiting for the scan… |
| `scanned` | Scanned. Confirm on the platform. |
| `verify_required` | Enter the pairing code shown on the platform, with a field to type it in. |
| `connected` | Bot created. Connecting… |
| `failed` | Login failed. |
| `expired` | QR code expired. Generate a new one. |

- **`message`** is required, 1 to 2,000 characters. Zett keeps it with the
  attempt to help you diagnose a login, but people see the dialog's text, so
  write it for yourself and never put a secret in it.
- **A pairing code.** Report `verify_required` when the platform shows the user
  a code to type in. Once they type it, Zett passes it to `submit_login_code()`
  before every later poll, not only once, so store it in a way that tolerates
  repeats and read it in `is_login()`. A code is at most 100 characters.
- **Connected.** Return `connected` with `ChannelCredentials`: `config` for
  plain settings, such as a bot id or a server address, and `secrets` for
  tokens, with at least one secret. Zett encrypts the secrets, saves the
  channel, stops the login instance, and starts a channel instance with them.
  A `connected` state without credentials or secrets fails the attempt.
- **The end of an attempt.** Reporting `failed` or `expired`, raising from
  `is_login()`, or five minutes passing ends the attempt, and Zett calls
  `stop()`. If someone closes the dialog first, the login instance waits until
  Zett stops, so keep what `login()` opens light.

## Receiving messages

For each enabled channel, Zett calls `receive()` in a loop. Wait for the next
message and return it. Do not return when nothing has arrived: Zett calls
`receive()` again as soon as it returns. To stop a channel, Zett cancels the
call, so let `asyncio.CancelledError` pass through.

A channel handles one message at a time. Zett calls `receive()` again only
after it has replied to the previous message, so whatever arrives in the
meantime waits on the platform, or in your client, until then.

| Field | What it holds |
| --- | --- |
| `event_id` | The platform's id for the message, at most 200 characters. Zett answers each id once and ignores it if it arrives again within seven days, so use an id that stays the same when the platform delivers a message twice. |
| `chat_id` | The direct or group chat, at most 500 characters. Each chat gets its own conversation in Zett. |
| `user_id` | Who sent the message, at most 500 characters. |
| `text` | The message text, at most 100,000 characters. |
| `media`, `rejected_media` | Attachments you deliver, and attachments you refuse. See [Attachments](#attachments). |

A message must carry text, an attachment, or a refused attachment. Skip
anything else, such as a sticker or a reaction, inside `receive()` and wait
for the next message, as the example does. These models check their limits
when you build them, so a value over a limit raises in `receive()`.

Keep how far you have read, the platform's cursor, in `kv` and resume from it,
so a restart neither misses messages nor answers one twice.

## Replying

When the conversation finishes, Zett calls `send(chat_id, text)` with the
whole answer, as the model wrote it, so it may contain Markdown. Convert or
strip formatting the platform cannot show, and split the text yourself if the
platform limits the length of a message. Zett sends nothing for an empty answer. If the
conversation fails, Zett sends "Sorry, something went wrong while handling that
message. Please try again." instead.

`send()` gets only the chat and the text. If the platform needs more to reply,
such as a token from the incoming message, store it per chat in `receive()`
and read it back in `send()`, as the example does. `ChannelInboundMessage` has
a `reply_token` field, but Zett does not pass it back to `send()`.

Zett reads a channel's provider and its other settings for each message, so
changing them does not restart your plugin.

## Attachments

Deliver each attachment as a `ChannelMedia`, with its bytes already downloaded
and decrypted:

| Field | What it holds |
| --- | --- |
| `kind` | `ChannelMediaKind.IMAGE`, `VOICE`, `FILE`, or `VIDEO`. |
| `media_type` | The file type, such as `image/png` or `audio/amr`. |
| `name` | The file name, if the platform has one. |
| `data` | The file's bytes. |

Zett saves every attachment with the conversation. An image also goes to the
model as an image, up to 32 MB each and 64 MB in one message, for models that
can see. Everything else reaches the model as a note naming the saved file.

A message carries at most 16 attachments, at most 256 MB each and 256 MB in
total, and Zett checks these limits again on its side. To refuse an attachment,
for example one too large to download, add it to `rejected_media`:

```python
from zett.plugins import ChannelMediaKind, ChannelMediaRejection, ChannelMediaRejectionReason

ChannelMediaRejection(kind=ChannelMediaKind.VIDEO, reason=ChannelMediaRejectionReason.TOO_LARGE)
```

Zett then replies "That file is too large to process. Please send a smaller
one." and runs no conversation for that message. The same happens when an
attachment you deliver is over the limits.

## When something fails

Raise when a platform call fails, instead of hiding the failure. Zett handles
it according to the call:

| Fails | What happens |
| --- | --- |
| Building the plugin, or `start()` | That channel does not run, and the log says why. The other channels start normally. |
| Building a login instance | The page shows "Channel plugin unavailable: my-platform". |
| `login()` | Zett calls `stop()`, and the page shows "Channel plugin failed to start login". |
| `is_login()` | The login attempt fails. |
| `submit_login_code()` | The failure is logged, and polling continues. |
| `receive()` | The failure is logged, and Zett calls `receive()` again two seconds later. The channel card still reads **Connected**, so watch the log. |
| `send()` | The failure is logged, and that reply is lost. |
| `stop()` | The failure is logged. |

Zett logs every one of these with its error message, so keep tokens out of the
exceptions you raise.

## Test it

Test the plugin with an in-memory `KVStorage` and a fake in place of the SDK's
client, so the tests never reach the platform:

```python title="tests/test_plugin.py"
from types import SimpleNamespace

import pytest
from zett.plugins import ChannelLoginStatus, JsonValue, KVStorage, PluginContext

import zett_my_platform
from zett_my_platform import MyPlugin


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


class FakeClient:
    """Scripted stand-in for myplatform.Client."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    async def start_login(self) -> SimpleNamespace:
        return SimpleNamespace(qr_content="https://my-platform.example/qr/1", qr_url=None, state={"qr": "1"})

    async def check_login(self, state: JsonValue, pairing_code: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(status="confirmed", bot_id="bot-1", token="token-1")

    async def close(self) -> None:
        pass


async def test_login_returns_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(zett_my_platform.myplatform, "Client", FakeClient)
    kv = MemoryKV()
    plugin = MyPlugin(PluginContext(plugin_id="my-platform", scope_id="login-1", kv=kv, config={}, secrets={}))

    challenge = await plugin.login()
    state = await plugin.is_login()

    assert challenge.qr_content == "https://my-platform.example/qr/1"
    assert kv.data["login:handshake"] == {"qr": "1"}
    assert state.status is ChannelLoginStatus.CONNECTED
    assert state.credentials is not None
    assert state.credentials.secrets == {"token": "token-1"}
```

```bash
uv run pytest
```

The WeChat plugin's
[tests](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett-weixin/tests/test_plugin.py)
cover receiving, attachments, and the reply token the same way.

## Install and try it

Install the package next to Zett and restart Zett, as described in
[Install and check](index.md#install-and-check). The log should list both
platforms:

```text
Channel plugins available: my-platform, wechat
```

WeChat ships with Zett, so **Channels → Connect** now asks which platform to
connect. Pick **My Platform**, choose a provider, press **Generate QR code**,
and scan the code with the platform's app. When the channel card appears, send
the bot a message.

## Build on agim

agim is the SDK under the WeChat plugin: one small interface (`login`,
`is_login`, `receive`, `send`) with one client per platform. It stores nothing
itself. It returns the login handshake and the receive cursor and expects them
back on the next call, which is exactly what `kv` is for, so a plugin built on
it is a thin adapter.
[The WeChat plugin's source](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett-weixin/src/zett_weixin/plugin.py)
is a complete example to copy from. See the [agim SDK](../agim.md) and
[WeChat channel plugin](../weixin.md) references for the details.
