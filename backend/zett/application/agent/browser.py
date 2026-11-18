"""Session-scoped browser RPC. No browser capability exists without a live peer.

The Chrome panel owns the tab and approves mutations. Zett keeps only ephemeral
connections and pending futures, never DOM patches or page data in storage.
"""

import asyncio
import base64
import binascii
import json
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from zett._compat import Self, timeout
from zett.infra.log import get_logger
from zett.infra.persistence.dao import session_storage

logger = get_logger(__name__)
MAX_BROWSER_MESSAGE = 100_000
MAX_BROWSER_RESULT = 64_000
#: One capture replies with a JPEG data URL, so that frame is larger than a command.
MAX_BROWSER_IMAGE_FRAME = 8_000_000
MAX_BROWSER_IMAGE_BYTES = 4_000_000
SCREENSHOT_PREFIX = "data:image/jpeg;base64,"


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Not a JSON value: {value}")


DISCONNECTED = (
    "Browser disconnected: the tab navigated, closed, or the panel reconnected. Page tools are unavailable "
    "for the rest of this turn, so do not retry them; tell the user what you could and could not do."
)
DISCONNECTED_MID_ACTION = (
    "Browser disconnected while the last action ran, so it may or may not have happened. Do not repeat it "
    "blindly and do not retry page tools this turn; tell the user."
)


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
    """Read the page or one CSS-selected subtree, or find elements by their visible text."""

    model_config = ConfigDict(extra="forbid", strict=True)
    selector: str | None = Field(default=None, min_length=1, max_length=500)
    text: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("selector", "text")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("selector and text must not be blank")
        return value


class BrowserInspectQuery(BaseModel):
    """Read one element's layout, styling, and reachability without touching it."""

    model_config = ConfigDict(extra="forbid", strict=True)
    selector: str = Field(min_length=1, max_length=500)

    @field_validator("selector")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("selector must not be blank")
        return value


class BrowserWaitQuery(BaseModel):
    """Wait, briefly, until the page reaches one observable condition."""

    model_config = ConfigDict(extra="forbid", strict=True)
    condition: Literal["appear", "disappear", "url_change"]
    selector: str | None = Field(default=None, min_length=1, max_length=500)
    text: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_ms: int = Field(default=5000, ge=500, le=8000)

    @field_validator("selector", "text")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("selector and text must not be blank")
        return value

    @model_validator(mode="after")
    def arguments_match_condition(self) -> Self:
        if self.condition == "url_change":
            if self.selector is not None or self.text is not None:
                raise ValueError("url_change accepts neither a selector nor text")
            return self
        if (self.selector is None) == (self.text is None):
            raise ValueError(f"{self.condition} needs exactly one of selector or text")
        return self


class BrowserProbeQuery(BaseModel):
    """Read one slice of what the page-world probe observed, bounded on both ends."""

    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["console", "network", "metrics"]
    limit: int = Field(default=30, ge=1, le=50)


#: Attributes whose value changes accessibility and nothing else. A page's own
#: behaviour is never driven by these, so a wrong edit is visible and reversible
#: rather than a silent rewrite of a link or a handler.
class BrowserAttributeChange(BaseModel):
    """Set or remove one allowlisted accessibility attribute on one element."""

    model_config = ConfigDict(extra="forbid", strict=True)
    name: Literal["alt", "title", "aria-label", "aria-labelledby", "aria-hidden", "role"]
    selector: str = Field(min_length=1, max_length=500)
    #: New value. An empty string is meaningful (`alt=""` marks a decorative image).
    value: str | None = Field(default=None, max_length=200)
    #: Explicit removal: omitting `value` is an error, never a silent delete.
    remove: bool = False
    description: str = Field(min_length=1, max_length=300)

    @field_validator("selector", "description")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value

    @model_validator(mode="after")
    def value_matches_removal(self) -> Self:
        if self.remove and self.value is not None:
            raise ValueError("Set either value or remove, never both")
        if not self.remove and self.value is None:
            raise ValueError("Set value, or remove=True to delete the attribute")
        return self


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
    operation: Literal["snapshot", "update", "interact", "inspect", "wait", "screenshot", "probe", "attribute", "audit"]
    change: BrowserDOMPatch | None = None
    query: BrowserPageQuery | None = None
    interaction: BrowserInteraction | None = None
    inspect: BrowserInspectQuery | None = None
    wait: BrowserWaitQuery | None = None
    probe: BrowserProbeQuery | None = None
    attribute: BrowserAttributeChange | None = None

    @model_validator(mode="after")
    def require_operation_payload(self) -> Self:
        """One operation carries exactly its own payload, so a read can never hide a write."""
        payloads = {
            "change": self.change,
            "query": self.query,
            "interaction": self.interaction,
            "inspect": self.inspect,
            "wait": self.wait,
            "probe": self.probe,
            "attribute": self.attribute,
        }
        present = [field for field, value in payloads.items() if value is not None]
        if self.operation == "snapshot":
            if present not in ([], ["query"]):
                raise ValueError("snapshot cannot carry a change, interaction, inspection, wait, probe, or attribute")
            return self
        if self.operation in ("screenshot", "audit"):
            if present:
                raise ValueError(f"{self.operation} is read-only and carries no payload")
            return self
        required = {
            "update": "change",
            "interact": "interaction",
            "inspect": "inspect",
            "wait": "wait",
            "probe": "probe",
            "attribute": "attribute",
        }[self.operation]
        if present != [required]:
            found = ", ".join(present) if present else "none"
            raise ValueError(f"{self.operation} carries only its own payload, but this command sent: {found}")
        return self


class BrowserResult(BaseModel):
    """Bounded JSON text from the page, a JPEG capture, or a user-visible error."""

    model_config = ConfigDict(extra="forbid", strict=True)
    ok: bool
    result: str | None = Field(default=None, max_length=MAX_BROWSER_RESULT)
    image: str | None = Field(default=None, max_length=MAX_BROWSER_IMAGE_FRAME)
    error: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def valid_result(self) -> Self:
        # An image is validated even on a failed reply: an unvalidated payload
        # would otherwise be the one path that skips every bound.
        if self.image is not None:
            self.screenshot_bytes()
        if not self.ok:
            if not self.error or not self.error.strip():
                raise ValueError("Failed execution needs an error")
            if self.image is not None:
                raise ValueError("A failed execution cannot carry an image")
            return self
        if self.error is not None:
            raise ValueError("Successful result needs no error")
        if (self.result is None) == (self.image is None):
            raise ValueError("A successful result carries exactly one of JSON text or an image")
        if self.result is not None:
            if len(self.result.encode("utf-8")) > MAX_BROWSER_RESULT:
                raise ValueError("Browser result exceeds 64 KB")
            json.loads(self.result, parse_constant=_reject_json_constant)
        return self

    def screenshot_bytes(self) -> bytes:
        """Decode and bound-check one captured JPEG.

        Validation lives here so a malformed or oversized capture is refused at
        the transport, before any tool can write it into a session directory.
        """
        if self.image is None:
            raise ValueError("This result carries no image")
        if not self.image.startswith(SCREENSHOT_PREFIX):
            raise ValueError("A browser image must be a JPEG data URL")
        try:
            data = base64.b64decode(self.image[len(SCREENSHOT_PREFIX) :], validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("A browser image must be valid base64") from error
        if len(data) > MAX_BROWSER_IMAGE_BYTES:
            raise ValueError(f"A browser image may not exceed {MAX_BROWSER_IMAGE_BYTES} bytes")
        if not data.startswith(b"\xff\xd8\xff"):
            raise ValueError("A browser image must be a JPEG")
        return data


class BrowserReply(BrowserResult):
    """The correlation ID is transport-only, not part of the model receipt."""

    type: Literal["result"]
    id: str = Field(min_length=1, max_length=64)


@dataclass(eq=False)
class _PendingCall:
    """One in-flight command, remembered with the shape its reply must have."""

    operation: str
    future: asyncio.Future[BrowserResult]


@dataclass(eq=False)
class BrowserConnection:
    session_id: str
    token: str
    send: Callable[[dict[str, object]], Awaitable[None]]
    pending: dict[str, _PendingCall] = field(default_factory=dict)
    active: bool = True
    # A model may emit several tool calls at once. The panel runs one command at
    # a time and approves each separately, so calls queue here instead of failing.
    _turn: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def call(
        self,
        operation: Literal[
            "snapshot", "update", "interact", "inspect", "wait", "screenshot", "probe", "attribute", "audit"
        ],
        change: BrowserDOMPatch | None = None,
        *,
        query: BrowserPageQuery | None = None,
        interaction: BrowserInteraction | None = None,
        inspect: BrowserInspectQuery | None = None,
        wait: BrowserWaitQuery | None = None,
        probe: BrowserProbeQuery | None = None,
        attribute: BrowserAttributeChange | None = None,
    ) -> BrowserResult:
        async with self._turn:
            return await self._call(
                operation,
                change,
                query=query,
                interaction=interaction,
                inspect=inspect,
                wait=wait,
                probe=probe,
                attribute=attribute,
            )

    async def _call(
        self,
        operation: Literal[
            "snapshot", "update", "interact", "inspect", "wait", "screenshot", "probe", "attribute", "audit"
        ],
        change: BrowserDOMPatch | None,
        *,
        query: BrowserPageQuery | None,
        interaction: BrowserInteraction | None,
        inspect: BrowserInspectQuery | None = None,
        wait: BrowserWaitQuery | None = None,
        probe: BrowserProbeQuery | None = None,
        attribute: BrowserAttributeChange | None = None,
    ) -> BrowserResult:
        if not self.active:
            raise BrowserUnavailableError(DISCONNECTED)
        command = BrowserCommand(
            id=secrets.token_hex(16),
            operation=operation,
            change=change,
            query=query,
            interaction=interaction,
            inspect=inspect,
            wait=wait,
            probe=probe,
            attribute=attribute,
        )
        future: asyncio.Future[BrowserResult] = asyncio.get_running_loop().create_future()
        self.pending[command.id] = _PendingCall(operation=operation, future=future)
        completed = False
        logger.info(
            "Browser command started; session_id=%s command_id=%s operation=%s", self.session_id, command.id, operation
        )
        try:
            # A deadline must never turn a cancelled turn into a long wait:
            # `asyncio.wait_for` on Python 3.10/3.11 returns the inner result when
            # the cancellation lands after that awaitable finished, so it can
            # swallow the CancelledError and keep waiting for the reply.
            async with timeout(5):
                await self.send(command.model_dump(mode="json", exclude_none=True))
            async with timeout(120):
                result = await future
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
        pending = self.pending.get(reply.id)
        if pending is None or pending.future.done():
            return  # Late/duplicate results cannot complete another call.
        # A reply only completes the command whose shape it matches: an image
        # belongs to a capture, and text belongs to everything else. Otherwise a
        # panel could hand a read a multi-megabyte image the tool never asked for.
        if reply.image is not None and pending.operation != "screenshot":
            pending.future.set_result(
                BrowserResult(ok=False, error="The browser sent an image for a command that does not accept one.")
            )
            return
        if reply.ok and pending.operation == "screenshot" and reply.image is None:
            pending.future.set_result(BrowserResult(ok=False, error="The browser answered a capture without an image."))
            return
        pending.future.set_result(BrowserResult(ok=reply.ok, result=reply.result, image=reply.image, error=reply.error))

    def fail(self, command_id: str, message: str) -> None:
        """Answer one command whose reply this client refuses, keeping the socket."""
        pending = self.pending.get(command_id)
        if pending is None or pending.future.done():
            return
        pending.future.set_result(BrowserResult(ok=False, error=message[:1000]))

    def close(self) -> None:
        self.active = False
        for pending in self.pending.values():
            if not pending.future.done():
                pending.future.set_exception(BrowserUnavailableError(DISCONNECTED_MID_ACTION))
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
