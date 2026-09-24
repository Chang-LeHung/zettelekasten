"""Generic CRUD boundary shared by infrastructure storage implementations.

Application storage awaits one asynchronous SQLite engine, so the contract is
asynchronous end to end and every DAO implements the same coroutine surface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

WriteModelT = TypeVar("WriteModelT")
ReadModelT = TypeVar("ReadModelT")
ID = TypeVar("ID")
ListOptionsT = TypeVar("ListOptionsT")


class AsyncStorage(ABC, Generic[WriteModelT, ReadModelT, ID, ListOptionsT]):
    """Typed asynchronous create, read, update, delete, and list operations."""

    @abstractmethod
    async def create(self, entity: WriteModelT) -> ReadModelT:
        """Persist a new entity and return its complete read representation."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, entity_id: ID) -> ReadModelT | None:
        """Return one entity by identity, or None when it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity_id: ID, entity: WriteModelT) -> ReadModelT:
        """Replace mutable entity fields or raise KeyError when it is absent."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: ID) -> bool:
        """Delete one entity and report whether it previously existed."""
        raise NotImplementedError

    @abstractmethod
    async def list(self, options: ListOptionsT | None = None) -> Sequence[ReadModelT]:
        """Return entities matching typed filters and pagination options."""
        raise NotImplementedError
