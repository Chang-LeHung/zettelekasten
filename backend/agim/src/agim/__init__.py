"""agim: one stateless interface for IM login, receive, and send.

The package is a plain SDK. It owns no storage, no plugin registry, and no
host concepts: callers persist the login handshake and receive cursor
themselves and hand them back on the next call.
"""

from .client import IMClient
from .models import (
    InboundMessage,
    JsonValue,
    LoginCredentials,
    LoginHandshake,
    LoginState,
    LoginStatus,
    ReceiveResult,
)
from .wechat import WeChatAuthClient, WeChatClient

__all__ = [
    "IMClient",
    "InboundMessage",
    "JsonValue",
    "LoginCredentials",
    "LoginHandshake",
    "LoginState",
    "LoginStatus",
    "ReceiveResult",
    "WeChatAuthClient",
    "WeChatClient",
]
