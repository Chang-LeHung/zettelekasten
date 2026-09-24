"""Shims for standard-library features that are newer than Python 3.10.

The application supports Python 3.10 and newer, but a few pieces build on
features that only exist from 3.11 onward. Collecting them here keeps the
version checks in one place instead of repeating them across the package.

This module is an implementation detail and is not part of the public API.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):  # pragma: no cover - selected by the interpreter
    from asyncio import timeout
    from datetime import UTC
    from enum import StrEnum
    from typing import Self
else:  # pragma: no cover - selected by the interpreter
    from datetime import timezone
    from enum import Enum

    from async_timeout import timeout
    from typing_extensions import Self

    UTC = timezone.utc

    class StrEnum(str, Enum):
        """``enum.StrEnum`` for Python 3.10: members are their own string value."""

        def __str__(self) -> str:
            return str(self.value)

        def __format__(self, format_spec: str) -> str:
            return str.__format__(str(self), format_spec)


if sys.version_info >= (3, 12):  # pragma: no cover - selected by the interpreter
    from typing import TypeAliasType
else:  # pragma: no cover - selected by the interpreter
    from typing_extensions import TypeAliasType

__all__ = ["StrEnum", "Self", "TypeAliasType", "UTC", "timeout"]
