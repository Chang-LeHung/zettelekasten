"""The one interface every agim platform client implements."""

from abc import ABC, abstractmethod

from .models import LoginHandshake, LoginState, ReceiveResult


class IMClient(ABC):
    """Unified login, receive, and send surface for one IM platform.

    agim is stateless by design: callers own and persist the login handshake
    and the receive cursor, then hand them back on the next call.
    """

    @abstractmethod
    async def login(self) -> LoginHandshake:
        """Begin a login flow and return the handshake the caller must store."""

    @abstractmethod
    async def is_login(self, handshake: LoginHandshake) -> LoginState:
        """Poll one stored handshake and return the current login state."""

    @abstractmethod
    async def receive(self, cursor: str | None = None) -> ReceiveResult:
        """Await the next inbound message and return its next cursor."""

    @abstractmethod
    async def send(self, chat_id: str, text: str, *, context_token: str | None = None) -> None:
        """Send one outbound message, reusing the caller's stored token."""

    async def aclose(self) -> None:
        """Release transport resources; platforms without one keep the default."""
        return None


__all__ = ["IMClient"]
