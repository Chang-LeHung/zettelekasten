"""Session-scoped browser RPC. No browser capability exists without a live peer.

The Chrome panel owns the tab and approves mutations. Zett keeps only ephemeral
connections and pending futures, never DOM patches or page data in storage.
"""

import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..._compat import Self
from ...infra.log import get_logger
from ...infra.persistence.dao import session_storage

logger = get_logger(__name__)
MAX_BROWSER_MESSAGE = 100_000
MAX_BROWSER_RESULT = 64_000


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Not a JSON value: {value}")


class BrowserUnavailableError(ValueError):
    """An expired/missing connection must never silently target another tab."""


class BrowserDOMPatch(BaseModel):
    """One allowlisted DOM edit, not executable source, HTML, or attributes."""

    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["set_text", "fill", "select", "set_checked"]
    selector: str = Field(min_length=1, max_length=500)
    value: str | bool
    description: str = Field(min_length=1, max_length=300)

    @field_validator("selector", "description")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value

    @model_validator(mode="after")
    def value_matches_action(self) -> Self:
        if self.action == "set_checked":
            if not isinstance(self.value, bool):
                raise ValueError("set_checked requires a boolean value")
        elif not isinstance(self.value, str) or len(self.value) > 10_000:
            raise ValueError("Text edits require a string of at most 10000 characters")
        return self


class BrowserPageQuery(BaseModel):
    """Read the whole page or exactly one CSS-selected subtree."""

    model_config = ConfigDict(extra="forbid", strict=True)
    selector: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("selector")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("selector must not be blank")
        return value


class BrowserInteraction(BaseModel):
    """A single user-like action with bounded, explicit parameters."""

    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["click", "double_click", "hover", "focus", "scroll", "press_key", "drag"]
    selector: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=300)
    target_selector: str | None = Field(default=None, min_length=1, max_length=500)
    key: (
        Literal[
            "Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"
        ]
        | None
    ) = None
    direction: Literal["up", "down", "left", "right"] | None = None
    distance: int | None = Field(default=None, ge=1, le=2000)

    @model_validator(mode="after")
    def arguments_match_action(self) -> Self:
        if not self.selector.strip() or not self.description.strip():
            raise ValueError("Selector and description cannot be blank")
        if self.action == "drag":
            if not self.target_selector or not self.target_selector.strip():
                raise ValueError("drag requires target_selector")
        elif self.target_selector is not None:
            raise ValueError("Only drag accepts target_selector")
        if self.action == "press_key":
            if self.key is None:
                raise ValueError("press_key requires key")
        elif self.key is not None:
            raise ValueError("Only press_key accepts key")
        if self.action == "scroll":
            if self.direction is None or self.distance is None:
                raise ValueError("scroll requires direction and distance")
        elif self.direction is not None or self.distance is not None:
            raise ValueError("Only scroll accepts direction and distance")
        return self


class BrowserCommand(BaseModel):
    """One expiring command sent only to its original connection."""

    type: Literal["command"] = "command"
    id: str
    operation: Literal["snapshot", "update", "interact"]
    change: BrowserDOMPatch | None = None
    query: BrowserPageQuery | None = None
    interaction: BrowserInteraction | None = None

    @model_validator(mode="after")
    def require_operation_payload(self) -> Self:
        if self.operation == "update" and (
            self.change is None or self.query is not None or self.interaction is not None
        ):
            raise ValueError("update requires only a DOM change")
        if self.operation == "interact" and (
            self.interaction is None or self.change is not None or self.query is not None
        ):
            raise ValueError("interact requires only an interaction")
        if self.operation == "snapshot" and (self.change is not None or self.interaction is not None):
            raise ValueError("snapshot cannot carry a mutation")
        return self


class BrowserResult(BaseModel):
    """Bounded JSON text from the page, or a user-visible execution error."""

    model_config = ConfigDict(extra="forbid", strict=True)
    ok: bool
    result: str | None = Field(default=None, max_length=MAX_BROWSER_RESULT)
    error: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def valid_result(self) -> Self:
        if self.ok:
            if self.result is None or self.error is not None:
                raise ValueError("Successful result needs JSON text and no error")
            if len(self.result.encode("utf-8")) > MAX_BROWSER_RESULT:
                raise ValueError("Browser result exceeds 64 KB")
            json.loads(self.result, parse_constant=_reject_json_constant)
        elif not self.error or not self.error.strip():
            raise ValueError("Failed execution needs an error")
        return self


class BrowserReply(BrowserResult):
    """The correlation ID is transport-only, not part of the model receipt."""

    type: Literal["result"]
    id: str = Field(min_length=1, max_length=64)


@dataclass(eq=False)
class BrowserConnection:
    session_id: str
    token: str
    send: Callable[[dict[str, object]], Awaitable[None]]
    pending: dict[str, asyncio.Future[BrowserResult]] = field(default_factory=dict)
    active: bool = True

    async def call(
        self,
        operation: Literal["snapshot", "update", "interact"],
        change: BrowserDOMPatch | None = None,
        *,
        query: BrowserPageQuery | None = None,
        interaction: BrowserInteraction | None = None,
    ) -> BrowserResult:
        if not self.active:
            raise BrowserUnavailableError("Browser disconnected; reconnect the tab before another turn")
        if self.pending:
            raise BrowserUnavailableError("Another browser command is pending; call browser tools sequentially")
        command = BrowserCommand(
            id=secrets.token_hex(16), operation=operation, change=change, query=query, interaction=interaction
        )
        future: asyncio.Future[BrowserResult] = asyncio.get_running_loop().create_future()
        self.pending[command.id] = future
        completed = False
        logger.info(
            "Browser command started; session_id=%s command_id=%s operation=%s", self.session_id, command.id, operation
        )
        try:
            await asyncio.wait_for(self.send(command.model_dump(mode="json")), timeout=5)
            result = await asyncio.wait_for(future, timeout=120)
            completed = True
            return result
        except asyncio.TimeoutError as error:
            raise BrowserUnavailableError(
                "Browser command timed out; outcome may be unknown. Inspect before retrying."
            ) from error
        finally:
            self.pending.pop(command.id, None)
            if not future.done():
                future.cancel()
            # Cancel pending consent in the panel too. Never replay on reconnect.
            if self.active and not completed:
                try:
                    await asyncio.wait_for(self.send({"type": "cancel", "id": command.id}), timeout=2)
                except (OSError, RuntimeError, asyncio.TimeoutError):
                    pass
            logger.info("Browser command finished; session_id=%s command_id=%s", self.session_id, command.id)

    def resolve(self, reply: BrowserReply) -> None:
        future = self.pending.get(reply.id)
        if future is None or future.done():
            return  # Late/duplicate results cannot complete another call.
        future.set_result(BrowserResult(ok=reply.ok, result=reply.result, error=reply.error))

    def close(self) -> None:
        self.active = False
        for future in self.pending.values():
            if not future.done():
                future.set_exception(BrowserUnavailableError("Browser disconnected; outcome may be unknown"))
        self.pending.clear()


class BrowserBridge:
    """A token binds one request to one live socket, never merely a session ID."""

    def __init__(self) -> None:
        self.connections: dict[str, BrowserConnection] = {}

    async def connect(self, session_id: str, send: Callable[[dict[str, object]], Awaitable[None]]) -> BrowserConnection:
        if await session_storage.get(session_id) is None:
            raise BrowserUnavailableError("Session not found")
        if len(self.connections) >= 32:
            raise BrowserUnavailableError("Too many connected browser panels")
        if any(peer.session_id == session_id for peer in self.connections.values()):
            raise BrowserUnavailableError("This session already has a browser panel")
        token = secrets.token_urlsafe(32)
        connection = BrowserConnection(session_id, token, send)
        self.connections[token] = connection
        logger.info("Browser connected; session_id=%s", session_id)
        return connection

    def require(self, session_id: str, token: str) -> BrowserConnection:
        connection = self.connections.get(token)
        if connection is None or not connection.active or connection.session_id != session_id:
            raise BrowserUnavailableError("Browser connection is missing or belongs to another session")
        return connection

    def disconnect(self, connection: BrowserConnection) -> None:
        if self.connections.get(connection.token) is connection:
            self.connections.pop(connection.token)
        connection.close()
        logger.info("Browser disconnected; session_id=%s", connection.session_id)


browser_bridge = BrowserBridge()
