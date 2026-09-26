"""Public plugin API for Zett.

This package is the stable surface a plugin imports. It intentionally avoids
pulling in Zett application or infrastructure modules so plugins (for example
``zett-weixin``) can depend on it without import cycles.
"""

from .channels import (
    MAX_CHANNEL_MEDIA_BYTES,
    MAX_CHANNEL_MEDIA_ITEMS,
    MAX_CHANNEL_MEDIA_TOTAL_BYTES,
    ChannelCredentials,
    ChannelInboundMessage,
    ChannelLoginChallenge,
    ChannelLoginState,
    ChannelLoginStatus,
    ChannelMedia,
    ChannelMediaKind,
    ChannelMediaRejection,
    ChannelMediaRejectionReason,
    ChannelPlugin,
)
from .contract import (
    JsonValue,
    KVStorage,
    NamespacedKV,
    Plugin,
    PluginContext,
    PluginDescriptor,
    PluginError,
    PluginKind,
    PluginLoadError,
)

__all__ = [
    "ChannelCredentials",
    "ChannelInboundMessage",
    "ChannelLoginChallenge",
    "ChannelLoginState",
    "ChannelLoginStatus",
    "ChannelMedia",
    "ChannelMediaKind",
    "ChannelMediaRejection",
    "ChannelMediaRejectionReason",
    "ChannelPlugin",
    "JsonValue",
    "KVStorage",
    "NamespacedKV",
    "Plugin",
    "PluginContext",
    "PluginDescriptor",
    "PluginError",
    "PluginKind",
    "PluginLoadError",
    "MAX_CHANNEL_MEDIA_BYTES",
    "MAX_CHANNEL_MEDIA_ITEMS",
    "MAX_CHANNEL_MEDIA_TOTAL_BYTES",
]
