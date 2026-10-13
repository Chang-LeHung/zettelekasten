# 渠道插件

渠道插件把 Zett 接入某个聊天平台，让人们可以在那个应用里给 Zett 发消息。你只需要针对平台实现三件事：登录、接收消息和发送回复。其余的都由 Zett 完成：**连接**对话框及其二维码、每个聊天对应一个会话、运行模型、保存附件，以及重试。请先阅读[构建 Zett 插件](index.md)。

随 Zett 一起发布的微信插件就是一个完整的渠道插件。本页会为一个虚构的平台 *My Platform* 构建一个更小的渠道插件。

## 插件包 {#the-package}

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
dependencies = ["myplatform"]  # 你的平台 SDK

[project.entry-points."zett.channels"]
my-platform = "zett_my_platform:MyPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/zett_my_platform"]

[dependency-groups]
dev = ["pytest>=8,<9", "pytest-asyncio>=0.26,<2", "zettelekasten==0.0.1"]

[tool.uv.sources]
zett = { path = "../zettelekasten/backend", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

入口点名称 `my-platform` 就是该平台的 id。Zett 会把它和通过该插件连接的每个通信渠道一起保存，所以一旦有人在使用这个插件，就不要再改动它，并把类的 `plugin_id` 设为同一个值。`plugin_label` 是人们在**连接**对话框和每张渠道卡片上看到的名称。

## Zett 如何使用插件 {#how-zett-uses-the-plugin}

Zett 会用你的类构建两种实例。

- **登录实例**在有人点击**生成二维码**时构建。它的 `config` 和 `secrets` 为空，Zett 也不会对它调用 `start()`。Zett 先调用一次 `login()`，在对话框打开期间约每秒调用一次 `is_login()`，登录尝试结束时调用 `stop()`。
- **渠道实例**会为每个已启用的通信渠道构建：Zett 启动时、登录成功时，以及有人重新启用某个渠道时。它会收到登录返回的 `config` 和 `secrets`。Zett 先调用 `start()`，然后循环调用 `receive()`，并对每条回复调用 `send()`；当渠道被停用或删除，或者 Zett 停止时，调用 `stop()`。

每个实例都有自己的 `kv`。渠道无法读取登录阶段存下的内容，所以凭据是从登录实例传给渠道实例的唯一内容。同一个平台上可以连接多个账号，每个账号都是独立的通信渠道，拥有各自的实例。

| 方法 | 是否必需 | Zett 何时调用 |
| --- | --- | --- |
| `login()` | 是 | 每次登录尝试调用一次，用于获取要显示的二维码。 |
| `is_login()` | 是 | 登录尝试期间约每秒一次，用于查询登录进度。 |
| `submit_login_code(code)` | 否 | 用户输入配对数字后，在每次轮询之前调用。 |
| `start()` | 是 | 渠道实例启动时。根据 `config` 和 `secrets` 打开你的客户端。 |
| `receive()` | 是 | 循环调用，用于获取下一条消息。 |
| `send(chat_id, text)` | 是 | 每条回复都会调用。 |
| `stop()` | 是 | 实例结束时。关闭 `login()` 或 `start()` 打开的所有资源。 |

## 完整插件 {#the-whole-plugin}

`myplatform` 代表你的平台 SDK，它的调用都是为本页虚构的：`start_login()` 返回二维码以及之后查询登录所需的状态，`check_login()` 报告登录进展，`next_update()` 等待游标之后的下一条消息，`send()` 发送回复。下面的各节会逐段讲解这个文件。

```python title="src/zett_my_platform/__init__.py"
import myplatform  # 代表你的平台 SDK
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

#: My Platform 的登录状态按 Zett 的方式映射；"confirmed" 单独处理。
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
        # 一个实例只运行一次登录或一个通信渠道，所以同一个客户端可以兼顾两者。
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
                continue  # 没有可回复的内容，例如贴纸
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
            self._client = myplatform.Client()  # 未登录状态，用于登录
        return self._client

    def _channel_client(self) -> myplatform.Client:
        if self._client is None:
            raise RuntimeError("My Platform channel is not started")
        return self._client
```

## 登录 {#logging-in}

`login()` 发起一次登录尝试，并返回一个 `ChannelLoginChallenge`。`qr_content` 是 Zett 绘制成二维码的文本，通常是平台应用可以打开的链接。可选的 `qr_url` 会增加一个**打开链接**按钮，供无法扫码的人使用，例如他们本来就在手机上操作。尝试过程中之后还要用到的内容，例如平台的登录状态，请保存在 `kv` 中。

对话框保持打开期间，Zett 约每秒调用一次 `is_login()`，最长持续五分钟。请返回一个 `ChannelLoginState`，其状态为以下六种之一。对话框会为每种状态显示各自的文字：

| 状态 | 对话框显示 |
| --- | --- |
| `pending` | 等待扫码登录… |
| `scanned` | 已扫描，请在平台上确认。 |
| `verify_required` | 请输入平台上显示的配对数字，并提供输入框。 |
| `connected` | 机器人已创建，正在连接… |
| `failed` | 登录失败。 |
| `expired` | 二维码已过期，请重新生成。 |

- **`message`** 为必填，长度 1 到 2,000 个字符。Zett 会把它和这次登录尝试一起保存，方便你排查登录问题，但人们看到的是对话框自己的文字，所以请写给自己看，并且不要在其中放入任何密钥。
- **配对数字。** 当平台向用户显示一个需要输入的数字时，请报告 `verify_required`。用户输入后，Zett 会在之后的每一次轮询之前（而不只是一次）把它传给 `submit_login_code()`，所以请用能容忍重复写入的方式保存它，并在 `is_login()` 中读取。配对数字最长 100 个字符。
- **已连接。** 返回 `connected` 并附带 `ChannelCredentials`：`config` 存放普通设置，例如机器人 id 或服务器地址，`secrets` 存放令牌，且至少要有一项密钥。Zett 会加密这些密钥、保存通信渠道、停止登录实例，并用这些凭据启动一个渠道实例。如果 `connected` 状态没有携带凭据或密钥，这次登录尝试就会失败。
- **尝试结束。** 报告 `failed` 或 `expired`、`is_login()` 抛出异常，或者超过五分钟，都会结束这次尝试，Zett 随后调用 `stop()`。如果用户先关闭了对话框，登录实例会一直等到 Zett 停止，所以请让 `login()` 打开的资源保持轻量。

## 接收消息 {#receiving-messages}

对每个已启用的通信渠道，Zett 都会循环调用 `receive()`。请等待下一条消息并返回它。没有消息到达时不要返回：`receive()` 一返回，Zett 就会立刻再次调用它。要停止一个渠道时，Zett 会取消这次调用，所以请让 `asyncio.CancelledError` 正常向外传播。

一个通信渠道一次只处理一条消息。只有在回复完上一条消息之后，Zett 才会再次调用 `receive()`，所以在此期间到达的消息会在平台或你的客户端中等待。

| 字段 | 内容 |
| --- | --- |
| `event_id` | 平台给这条消息的 id，最长 200 个字符。Zett 对每个 id 只回答一次，七天内再次收到同一个 id 时会忽略它，所以请使用在平台重复投递同一条消息时保持不变的 id。 |
| `chat_id` | 单聊或群聊，最长 500 个字符。每个聊天在 Zett 中都有各自的会话。 |
| `user_id` | 消息发送者，最长 500 个字符。 |
| `text` | 消息文本，最长 100,000 个字符。 |
| `media`、`rejected_media` | 你交付的附件，以及你拒收的附件。参见[附件](#attachments)。 |

一条消息必须带有文本、附件或被拒收的附件。其他情况，例如贴纸或表情回应，请像示例那样在 `receive()` 内部跳过，继续等待下一条消息。这些模型会在构建时检查各项限制，所以超出限制的值会在 `receive()` 中抛出异常。

请把你读取到的位置，也就是平台的游标，保存在 `kv` 中，并从它继续读取，这样重启后既不会漏掉消息，也不会重复回答同一条消息。

## 回复 {#replying}

会话结束时，Zett 会调用 `send(chat_id, text)`，传入模型写出的完整答案，所以其中可能包含 Markdown。请转换或去除平台无法显示的格式；如果平台限制单条消息的长度，请自行拆分文本。答案为空时，Zett 不会发送任何内容。如果会话失败，Zett 会改为发送 "Sorry, something went wrong while handling that message. Please try again."。

`send()` 只会拿到聊天和文本。如果平台回复时还需要更多信息，例如来自入站消息的令牌，请像示例那样在 `receive()` 中按聊天保存，再在 `send()` 中读回。`ChannelInboundMessage` 有一个 `reply_token` 字段，但 Zett 不会把它传回 `send()`。

Zett 会在处理每条消息时读取通信渠道的 Provider 及其他设置，所以修改它们不会重启你的插件。

## 附件 {#attachments}

请把每个附件交付为一个 `ChannelMedia`，其字节数据需要已经下载并解密：

| 字段 | 内容 |
| --- | --- |
| `kind` | `ChannelMediaKind.IMAGE`、`VOICE`、`FILE` 或 `VIDEO`。 |
| `media_type` | 文件类型，例如 `image/png` 或 `audio/amr`。 |
| `name` | 文件名（如果平台提供）。 |
| `data` | 文件的字节数据。 |

Zett 会把每个附件与会话一起保存。对于具备视觉能力的模型，图片还会以图片的形式发送给模型，单张最大 32 MB，一条消息中最多 64 MB。其他类型的附件则以一条注明已保存文件名的说明发送给模型。

一条消息最多携带 16 个附件，单个附件最大 256 MB，总计最大 256 MB，Zett 在自己这一侧还会再次检查这些限制。如果要拒收某个附件，例如它太大而无法下载，请把它加入 `rejected_media`：

```python
from zett.plugins import ChannelMediaKind, ChannelMediaRejection, ChannelMediaRejectionReason

ChannelMediaRejection(kind=ChannelMediaKind.VIDEO, reason=ChannelMediaRejectionReason.TOO_LARGE)
```

随后 Zett 会回复 "That file is too large to process. Please send a smaller one."，并且不会为这条消息运行任何会话。如果你交付的附件超出了上述限制，也会出现同样的结果。

## 出错时 {#when-something-fails}

平台调用失败时请直接抛出异常，不要掩盖失败。Zett 会根据失败的调用分别处理：

| 失败的环节 | 发生的事情 |
| --- | --- |
| 构建插件或 `start()` | 该通信渠道不会运行，日志会说明原因。其他渠道正常启动。 |
| 构建登录实例 | 页面显示 "Channel plugin unavailable: my-platform"。 |
| `login()` | Zett 调用 `stop()`，页面显示 "Channel plugin failed to start login"。 |
| `is_login()` | 这次登录尝试失败。 |
| `submit_login_code()` | 失败会被记入日志，轮询继续。 |
| `receive()` | 失败会被记入日志，两秒后 Zett 再次调用 `receive()`。渠道卡片仍然显示**已连接**，所以请留意日志。 |
| `send()` | 失败会被记入日志，这条回复会丢失。 |
| `stop()` | 失败会被记入日志。 |

Zett 会把上述每种失败连同错误信息一起记入日志，所以请不要在你抛出的异常中带上令牌。

## 测试 {#test-it}

请使用内存中的 `KVStorage`，并用一个替身代替 SDK 的客户端来测试插件，这样测试就不会访问平台：

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

微信插件的[测试](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett-weixin/tests/test_plugin.py)以同样的方式覆盖了消息接收、附件和回复令牌。

## 安装并试用 {#install-and-try-it}

按照[安装并检查](index.md#install-and-check)中的说明，把插件包安装到 Zett 旁边并重启 Zett。日志中应该会列出两个平台：

```text
Channel plugins available: my-platform, wechat
```

微信随 Zett 一起发布，所以现在点击**通信渠道 → 连接**时，会询问要连接哪个平台。选择 **My Platform**，选择一个 Provider，点击**生成二维码**，然后用该平台的应用扫描二维码。渠道卡片出现后，给机器人发一条消息即可。

## 基于 agim 构建 {#build-on-agim}

agim 是微信插件底层的 SDK：一个精简的接口（`login`、`is_login`、`receive`、`send`），每个平台对应一个客户端。它自身不存储任何数据。它会返回登录握手和接收游标，并期望在下一次调用时被传回，这正是 `kv` 的用途，所以基于它构建的插件只是一层很薄的适配器。[微信插件的源码](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/zett-weixin/src/zett_weixin/plugin.py)是一个可以直接参考的完整示例。详情请参阅 [agim SDK](../agim.md) 和[微信渠道插件](../weixin.md)参考文档。
