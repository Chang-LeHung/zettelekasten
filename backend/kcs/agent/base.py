from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class StreamingAgent[RequestT](ABC):
    """Boundary for agents that expose server-sent event streams."""

    @abstractmethod
    def stream(self, conversation_id: str, request: RequestT) -> AsyncIterator[str]:
        """Run one conversation turn and yield serialized stream events."""
        raise NotImplementedError
