"""Generic CRUD boundary shared by infrastructure storage implementations."""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class Storage[WriteModelT, ReadModelT, ID, ListOptionsT](ABC):
    """Typed create, read, update, delete, and list operations."""

    @abstractmethod
    def create(self, entity: WriteModelT) -> ReadModelT:
        """Persist a new entity and return its complete read representation."""
        raise NotImplementedError

    @abstractmethod
    def get(self, entity_id: ID) -> ReadModelT | None:
        """Return one entity by identity, or None when it does not exist."""
        raise NotImplementedError

    @abstractmethod
    def update(self, entity_id: ID, entity: WriteModelT) -> ReadModelT:
        """Replace mutable entity fields or raise KeyError when it is absent."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: ID) -> bool:
        """Delete one entity and report whether it previously existed."""
        raise NotImplementedError

    @abstractmethod
    def list(self, options: ListOptionsT | None = None) -> Sequence[ReadModelT]:
        """Return entities matching typed filters and pagination options."""
        raise NotImplementedError


class AsyncStorage[WriteModelT, ReadModelT, ID, ListOptionsT](ABC):
    """Typed CRUD operations for a boundary that performs asynchronous I/O.

    The Agent session database is owned by the asynchronous zett-agent storage,
    so its adapter cannot expose the blocking contract above.
    """

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
