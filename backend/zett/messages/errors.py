"""Failures raised while validating multimodal message parts."""


class MessagePartError(ValueError):
    """Base class for rejected message part payloads."""


class UnsupportedMessagePartError(MessagePartError):
    """Raised when a part is neither text nor image."""


class MessagePartBytesError(MessagePartError):
    """Raised when raw bytes cross a boundary that speaks base64."""


class InvalidImagePayloadError(MessagePartError):
    """Raised when an image part is not a valid base64 image."""


class MessageImageCountExceeded(MessagePartError):
    """Raised when one message declares more images than the limit allows."""


class MessageImageSizeExceeded(MessagePartError):
    """Raised when decoded message images exceed the configured size limit."""


__all__ = [
    "InvalidImagePayloadError",
    "MessageImageCountExceeded",
    "MessageImageSizeExceeded",
    "MessagePartBytesError",
    "MessagePartError",
    "UnsupportedMessagePartError",
]
