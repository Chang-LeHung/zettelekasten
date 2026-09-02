from abc import ABC, abstractmethod
from collections.abc import Sequence


class Storage[T, ID](ABC):
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
    def list(self) -> Sequence[T]:
        raise NotImplementedError
