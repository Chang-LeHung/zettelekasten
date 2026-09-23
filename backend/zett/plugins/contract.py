"""Generic plugin contracts shared by every Zett plugin kind."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class PluginKind(StrEnum):
    """Category of plugin; each kind discovers through its own entry-point group."""

    CHANNEL = "channel"


class PluginError(RuntimeError):
    """Raised when a plugin fails at the boundary Zett controls.

    Plugin code is third-party code, so its failures are contained and
    re-raised as this type instead of leaking arbitrary exceptions into Zett.
    """


class PluginLoadError(PluginError):
    """Raised when a plugin cannot be discovered or constructed."""


class KVStorage(ABC):
    """Key-value store a plugin persists through, owned and provided by Zett."""

    @abstractmethod
    async def get(self, key: str) -> JsonValue | None:
        """Return one value, or ``None`` when the key is absent."""

    @abstractmethod
    async def set(self, key: str, value: JsonValue) -> None:
        """Create or replace one value."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete one key and report whether it existed."""

    @abstractmethod
    async def iter_prefix(self, prefix: str) -> list[tuple[str, JsonValue]]:
        """Return a key-sorted snapshot of values under a prefix."""


class NamespacedKV(KVStorage):
    """Prefix every key so one plugin scope cannot reach another's data."""

    def __init__(self, storage: KVStorage, prefix: str) -> None:
        self._storage = storage
        self._prefix = prefix

    async def get(self, key: str) -> JsonValue | None:
        return await self._storage.get(f"{self._prefix}{key}")

    async def set(self, key: str, value: JsonValue) -> None:
        await self._storage.set(f"{self._prefix}{key}", value)

    async def delete(self, key: str) -> bool:
        return await self._storage.delete(f"{self._prefix}{key}")

    async def iter_prefix(self, prefix: str) -> list[tuple[str, JsonValue]]:
        rows = await self._storage.iter_prefix(f"{self._prefix}{prefix}")
        return [(key[len(self._prefix) :], value) for key, value in rows]


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Everything one plugin instance receives from Zett."""

    plugin_id: str
    scope_id: str
    kv: KVStorage
    config: Mapping[str, JsonValue]
    secrets: Mapping[str, str]


class Plugin(ABC):
    """Lifecycle every Zett plugin shares."""

    kind: ClassVar[PluginKind]
    plugin_id: ClassVar[str]

    @abstractmethod
    async def start(self) -> None:
        """Acquire whatever the plugin needs before its operations run."""

    @abstractmethod
    async def stop(self) -> None:
        """Release resources opened during ``start``."""


__all__ = [
    "JsonValue",
    "KVStorage",
    "NamespacedKV",
    "Plugin",
    "PluginContext",
    "PluginError",
    "PluginKind",
    "PluginLoadError",
]
