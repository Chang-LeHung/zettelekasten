"""Conversion between ``FrontUserMessage`` and zett-agent messages.

The browser and zett-agent describe the same turn with different shapes, and
images always travel as base64 text. This module is the single owner of that
boundary: it rejects raw bytes, validates MIME types and base64 payloads,
enforces image budgets, and converts both directions.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence

from zett_agent import (
    ImageBytesSource,
    ImageContent,
    ImageUrlSource,
    TextContent,
    UserContent,
    UserContentPart,
    UserMessage,
)

from .errors import (
    InvalidImagePayloadError,
    MessageImageCountExceeded,
    MessageImageSizeExceeded,
    MessagePartBytesError,
    UnsupportedMessagePartError,
)
from .front import (
    IMAGE_MIME_PATTERN,
    FrontImagePart,
    FrontMessagePart,
    FrontTextPart,
    FrontUserMessage,
)

_BYTE_TYPES = (bytes, bytearray, memoryview)
_BASE64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_DATA_URL_HEADER = re.compile(r"^data:(image/[A-Za-z0-9.+-]+);base64$")
_REMOTE_SCHEMES = ("http://", "https://")

_IMAGE_MIME = re.compile(IMAGE_MIME_PATTERN)


class MessagePartCodec:
    """Convert a frontend message into an Agent message and back.

    Args:
        max_images: Image budget for one ingested message; None disables it.
        max_bytes: Decoded image byte budget for one ingested message; None
            disables it.

    Examples:
        Accept one browser turn::

            codec = MessagePartCodec(max_images=4, max_bytes=10_000_000)
            message = codec.to_user_message(front_message)

        Project one stored message for the browser::

            front = MessagePartCodec().to_front_message(message)
    """

    image_url_prefix = "data:"

    def __init__(self, *, max_images: int | None = None, max_bytes: int | None = None) -> None:
        if max_images is not None and max_images < 1:
            raise ValueError("max_images must be a positive integer or None")
        if max_bytes is not None and max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer or None")
        self._max_images = max_images
        self._max_bytes = max_bytes

    def to_user_message(self, front: FrontUserMessage) -> UserMessage:
        """Validate one frontend message and build the Agent message it describes.

        Text and image blocks keep the order the browser sent them in, empty
        text blocks are dropped, and a message without text parts falls back to
        its ``raw_content``.
        """
        content: list[UserContentPart] = []
        images = 0
        total_bytes = 0
        for part in front.parts:
            match part:
                case FrontTextPart(text=text):
                    text_content = self._text_content(text)
                    if text_content is not None:
                        content.append(text_content)
                case FrontImagePart(name=name, mime_type=mime_type, content_url=content_url):
                    images += 1
                    if self._max_images is not None and images > self._max_images:
                        label = "image" if self._max_images == 1 else "images"
                        raise MessageImageCountExceeded(f"A message can contain up to {self._max_images} {label}")
                    image_content, decoded_size = self._image_content(name, mime_type, content_url)
                    total_bytes += decoded_size
                    if self._max_bytes is not None and total_bytes > self._max_bytes:
                        raise MessageImageSizeExceeded("Message images exceed the configured limit")
                    content.append(image_content)
                case _:
                    raise UnsupportedMessagePartError(
                        f"Unsupported message part: {type(part).__name__}; use FrontTextPart or FrontImagePart"
                    )
        if not content:
            return UserMessage(content=front.current_message)
        return UserMessage(content=content)

    def to_front_message(self, message: UserMessage) -> FrontUserMessage:
        """Project one Agent message back into the frontend shape."""
        return FrontUserMessage(raw_content=message.text, parts=self.to_front_parts(message.parts))

    def to_front_parts(self, content: UserContent | Sequence[UserContentPart]) -> list[FrontMessagePart]:
        """Project Agent content into frontend parts.

        String content yields no parts: REST clients read that text from the
        message ``content`` field, so structured tool output stays intact.
        """
        if isinstance(content, str):
            return []
        parts: list[FrontMessagePart] = []
        for part in content:
            match part:
                case TextContent(text=text):
                    parts.append(FrontTextPart(text=text))
                case ImageContent():
                    parts.append(self._front_image(part))
                case _:
                    raise UnsupportedMessagePartError(f"Unsupported message part: {type(part).__name__}")
        return parts

    @staticmethod
    def _text_content(text: str) -> TextContent | None:
        if isinstance(text, _BYTE_TYPES):
            raise MessagePartBytesError("Text message parts must be UTF-8 text, not raw bytes")
        return TextContent(text) if text else None

    def _image_content(
        self,
        name: str,
        mime_type: str | None,
        content_url: str,
    ) -> tuple[ImageContent, int]:
        """Build one Agent image from a base64 data URL or a remote URL."""
        if isinstance(content_url, _BYTE_TYPES):
            raise MessagePartBytesError(f"Image {name!r} must carry base64 text, not raw bytes")
        if content_url.startswith(_REMOTE_SCHEMES):
            return ImageContent(source=ImageUrlSource(content_url), alt_text=name), 0
        header, separator, payload = content_url.partition(",")
        if not separator:
            raise InvalidImagePayloadError(f"Image {name!r} must be a base64 data URL or an http(s) URL")
        data_mime = self._data_url_mime(header, name)
        if mime_type is not None and mime_type != data_mime:
            raise InvalidImagePayloadError(f"Image {name!r} declares {mime_type} but its data URL carries {data_mime}")
        encoded = "".join(payload.split())
        size = self._decoded_size(encoded, name)
        source = ImageUrlSource(f"{self.image_url_prefix}{data_mime};base64,{encoded}")
        return ImageContent(source=source, alt_text=name), size

    @classmethod
    def _front_image(cls, part: ImageContent) -> FrontImagePart:
        """Project one Agent image, encoding stored bytes as a data URL."""
        name = part.alt_text or "Image"
        match part.source:
            case ImageUrlSource(url=url):
                return FrontImagePart(name=name, mime_type=cls._url_mime(url), content_url=url)
            case ImageBytesSource(data=data, media_type=media_type):
                if not isinstance(data, _BYTE_TYPES):
                    raise MessagePartBytesError(f"Image payload must be raw bytes, got {type(data).__name__}")
                encoded = base64.b64encode(data).decode("ascii")
                return FrontImagePart(
                    name=name,
                    mime_type=media_type,
                    content_url=f"{cls.image_url_prefix}{media_type};base64,{encoded}",
                )
        raise UnsupportedMessagePartError(f"Unsupported image source: {type(part.source).__name__}")

    @classmethod
    def _url_mime(cls, url: str) -> str | None:
        """Return the MIME type carried by a data URL, or None for remote URLs."""
        if not url.startswith("data:"):
            return None
        header, _, _ = url.partition(",")
        match = _DATA_URL_HEADER.fullmatch(header)
        return match.group(1) if match else None

    @staticmethod
    def _data_url_mime(header: str, name: str) -> str:
        match = _DATA_URL_HEADER.fullmatch(header)
        if match is None:
            raise InvalidImagePayloadError(f"Image {name!r} must use a base64 data URL")
        return match.group(1)

    @staticmethod
    def _decoded_size(encoded: str, name: str) -> int:
        """Measure a base64 payload without decoding it."""
        if len(encoded) % 4 or _BASE64.fullmatch(encoded) is None:
            raise InvalidImagePayloadError(f"Invalid image data: {name}")
        padding = len(encoded) - len(encoded.rstrip("="))
        size = len(encoded) // 4 * 3 - padding
        if size <= 0:
            raise InvalidImagePayloadError(f"Image is empty: {name}")
        return size


__all__ = ["MessagePartCodec"]
