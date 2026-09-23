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

## Platform clients

`WeChatClient` implements the Tencent personal WeChat iLink/ClawBot protocol
used by Tencent's official `openclaw-weixin` project: QR login, `getupdates`
long polling, and `sendmessage`. More platforms (for example Discord)
implement the same `IMClient` surface.

## Storage

None. Whoever calls agim owns persistence.
