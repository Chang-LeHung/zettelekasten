from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmptyListOptions:
    """Default options for storage types without list filters."""


class Storage[T, ID, ListOptionsT](ABC):
    """Generic storage boundary used by application services."""

    @abstractmethod
    def create(self, entity: T) -> T:
        raise NotImplementedError

    @abstractmethod
    def get(self, entity_id: ID) -> T | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, entity_id: ID, entity: T) -> T:
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: ID) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self, options: ListOptionsT | None = None) -> Sequence[T]:
        raise NotImplementedError
