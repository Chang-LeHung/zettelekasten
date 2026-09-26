"""agim: one stateless interface for IM login, receive, and send.

The package is a plain SDK. It owns no storage, no plugin registry, and no
host concepts: callers persist the login handshake and receive cursor
themselves and hand them back on the next call.
"""

from .client import IMClient
from .errors import MediaTooLargeError
from .models import (
    MAX_MEDIA_BYTES,
    MAX_MEDIA_ITEMS,
    InboundMedia,
    InboundMessage,
    JsonValue,
    LoginCredentials,
    LoginHandshake,
    LoginState,
    LoginStatus,
    MediaKind,
    MediaRejectionReason,
    ReceiveResult,
    RejectedMedia,
)
from .wechat import WeChatAuthClient, WeChatClient

__all__ = [
    "IMClient",
    "InboundMessage",
    "InboundMedia",
    "JsonValue",
    "LoginCredentials",
    "LoginHandshake",
    "LoginState",
    "LoginStatus",
    "MAX_MEDIA_BYTES",
    "MAX_MEDIA_ITEMS",
    "MediaKind",
    "MediaRejectionReason",
    "MediaTooLargeError",
    "RejectedMedia",
    "ReceiveResult",
    "WeChatAuthClient",
    "WeChatClient",
]
