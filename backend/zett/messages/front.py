"""The message shape the browser submits and reads back.

``FrontUserMessage`` is the only frontend-facing message type: ordered text and
image blocks whose images carry base64 data URLs. ``MessagePartCodec`` converts
it to and from zett-agent's ``UserMessage``, so no other model describes the
same parts.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._compat import TypeAliasType

IMAGE_MIME_PATTERN = r"^image/[A-Za-z0-9.+-]+$"


class FrontPart(BaseModel):
    """Base model that rejects implicit coercions such as bytes-to-text."""

    model_config = ConfigDict(strict=True)


class FrontTextPart(FrontPart):
    """One text block inside an ordered frontend message."""

    type: Literal["text"] = "text"
    text: str


class FrontImagePart(FrontPart):
    """One image block carried as a base64 data URL, or a remote URL."""

    type: Literal["image"] = "image"
    name: str = Field(min_length=1, max_length=500)
    mime_type: str | None = Field(default=None, pattern=IMAGE_MIME_PATTERN, max_length=255)
    content_url: str = Field(min_length=1)


FrontMessagePart = TypeAliasType(
    "FrontMessagePart", Annotated[FrontTextPart | FrontImagePart, Field(discriminator="type")]
)


class FrontUserMessage(FrontPart):
    """One user turn exactly as the browser submits it."""

    raw_content: str = ""
    parts: list[FrontMessagePart] = Field(default_factory=list, max_length=513)

    @property
    def current_message(self) -> str:
        """Return only this request's text; persisted history is restored separately."""
        return self.raw_content.strip()

    @model_validator(mode="after")
    def require_message_content(self) -> FrontUserMessage:
        """Accept text, images, or both while rejecting an empty user turn."""
        if not self.current_message and not any(
            isinstance(part, FrontImagePart) or (isinstance(part, FrontTextPart) and part.text.strip())
            for part in self.parts
        ):
            raise ValueError("A message requires text or at least one image")
        return self


__all__ = [
    "IMAGE_MIME_PATTERN",
    "FrontImagePart",
    "FrontMessagePart",
    "FrontPart",
    "FrontTextPart",
    "FrontUserMessage",
]
