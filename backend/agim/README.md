# agim

One stateless interface for IM login, receive, and send. agim is a plain SDK:
it owns no storage, no plugin registry, and no host concepts. Callers persist
the login handshake and receive cursor themselves and hand them back on the
next call.

## Interface

```python
class IMClient(ABC):
    async def login(self) -> LoginHandshake: ...
    async def is_login(self, handshake: LoginHandshake) -> LoginState: ...
    async def receive(self, cursor: str | None = None) -> ReceiveResult: ...
    async def send(self, chat_id: str, text: str, *, context_token: str | None = None) -> None: ...
    async def aclose(self) -> None: ...
```

Because nothing is stored inside agim:

- `login()` returns the QR payload **and** the provider state needed to poll it.
  Persist the whole `LoginHandshake`, then pass it back to `is_login()`.
- `receive()` returns the message **and** the next cursor. Persist the cursor,
  then pass it to the next `receive()`.
- `send()` takes the context token the caller stored from the inbound message.

One `getupdates` poll can carry several messages. `receive()` still hands over
exactly one message per call: the rest of the batch waits in memory (oldest
first), and the returned cursor only advances past the batch once its last
message has been handed over, so a restart mid-batch re-delivers that batch
instead of dropping the messages behind the first one.

## Platform clients

`WeChatClient` implements the Tencent personal WeChat iLink/ClawBot protocol
used by Tencent's official `openclaw-weixin` project: QR login, `getupdates`
long polling, and `sendmessage`. More platforms (for example Discord)
implement the same `IMClient` surface.

Inbound messages carry their attachments on `InboundMessage.media`, one
`InboundMedia` per image, voice note, file, or video. The client downloads the
CDN reference and removes the AES-128-ECB encryption before returning, so a
caller receives usable bytes; whether a given consumer reads an image, plays a
voice note, or ignores both is the caller's decision. An item that cannot be
downloaded or decrypted is logged and skipped: the message keeps the
`[image]`/`[voice]`/`[file]`/`[video]` placeholder in its text. An item over
`MAX_MEDIA_BYTES` raises `MediaTooLargeError` from `fetch_media` and is reported
on `InboundMessage.rejected_media`, so a caller can tell the sender that the
attachment was refused instead of losing it quietly.

## Storage

None. Whoever calls agim owns persistence.
