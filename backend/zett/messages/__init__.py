"""Conversion between the browser message shape and zett-agent messages.

Callers use :class:`MessagePartCodec` instead of touching base64, bytes, or
zett-agent content types directly:

* ingress: ``to_user_message(front)`` validates a ``FrontUserMessage`` and
  rejects bytes
* egress: ``to_front_message(message)`` and ``to_front_parts(content)`` project
  stored messages back into the browser shape
"""

from .codec import DecodedImage, MessagePartCodec
from .errors import (
    InvalidImagePayloadError,
    MessageImageCountExceeded,
    MessageImageSizeExceeded,
    MessagePartBytesError,
    MessagePartError,
    UnsupportedMessagePartError,
)
from .front import (
    IMAGE_MIME_PATTERN,
    FrontImagePart,
    FrontMessagePart,
    FrontPart,
    FrontTextPart,
    FrontUserMessage,
)

__all__ = [
    "DecodedImage",
    "IMAGE_MIME_PATTERN",
    "FrontImagePart",
    "FrontMessagePart",
    "FrontPart",
    "FrontTextPart",
    "FrontUserMessage",
    "InvalidImagePayloadError",
    "MessageImageCountExceeded",
    "MessageImageSizeExceeded",
    "MessagePartBytesError",
    "MessagePartCodec",
    "MessagePartError",
    "UnsupportedMessagePartError",
]
