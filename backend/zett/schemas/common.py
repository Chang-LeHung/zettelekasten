"""Shared JSON-compatible type aliases and constrained input primitives."""

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, StringConstraints

from .._compat import TypeAliasType

JsonValue = TypeAliasType("JsonValue", "bool | int | float | str | None | list[JsonValue] | dict[str, JsonValue]")


def validate_http_url(value: str) -> str:
    """Require an absolute HTTP(S) URL without accepting executable schemes."""
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL must be an absolute http:// or https:// URL")
    return value


HttpUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4_096),
    AfterValidator(validate_http_url),
]
DataImageUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=10_000_000,
        pattern=r"^data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+$",
    ),
]
ImageUrl = HttpUrl | DataImageUrl
NonBlankName100 = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
NonBlankName200 = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
NonBlankName500 = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=500,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
