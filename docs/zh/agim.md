# agim

用于 IM 登录、接收和发送的统一无状态接口。agim 是一个纯粹的 SDK：它没有存储、没有插件注册表，也不包含任何宿主概念。调用方需要自行持久化登录握手和接收游标，并在下一次调用时传回。

## 接口 {#interface}

```python
class IMClient(ABC):
    async def login(self) -> LoginHandshake: ...
    async def is_login(self, handshake: LoginHandshake) -> LoginState: ...
    async def receive(self, cursor: str | None = None) -> ReceiveResult: ...
    async def send(self, chat_id: str, text: str, *, context_token: str | None = None) -> None: ...
    async def aclose(self) -> None: ...
```

由于 agim 内部不存储任何数据：

- `login()` 返回二维码内容**以及**轮询所需的平台状态。请持久化整个 `LoginHandshake`，再把它传回 `is_login()`。
- `receive()` 返回消息**以及**下一个游标。请持久化游标，再把它传给下一次 `receive()`。
- `send()` 接收调用方从入站消息中保存的上下文令牌。

一次 `getupdates` 轮询可能携带多条消息。`receive()` 每次调用仍然只交出一条消息：这一批中的其余消息会按从旧到新的顺序留在内存中，只有当这一批的最后一条消息被交出后，返回的游标才会越过这一批。因此，如果在一批消息处理到一半时重启，这一批会被重新投递，而不会丢掉第一条之后的消息。

## 平台客户端 {#platform-clients}

`WeChatClient` 实现了腾讯官方 `openclaw-weixin` 项目所使用的腾讯个人微信 iLink/ClawBot 协议：二维码登录、`getupdates` 长轮询和 `sendmessage`。更多平台（例如 Discord）会实现同样的 `IMClient` 接口。

入站消息通过 `InboundMessage.media` 携带附件，每张图片、语音、文件或视频对应一个 `InboundMedia`。客户端会在返回之前下载 CDN 引用并移除 AES-128-ECB 加密，所以调用方拿到的是可直接使用的字节数据；至于具体的使用方是读取图片、播放语音还是两者都忽略，由调用方决定。无法下载或解密的条目会被记入日志并跳过：消息文本中会保留 `[image]`/`[voice]`/`[file]`/`[video]` 占位符。超过 `MAX_MEDIA_BYTES` 的条目会让 `fetch_media` 抛出 `MediaTooLargeError`，并记录在 `InboundMessage.rejected_media` 上，这样调用方就可以告知发送者附件被拒收，而不是悄悄丢掉它。

## 存储 {#storage}

无。持久化由调用 agim 的一方负责。
