"""Probe provider settings with one minimal model request before persistence."""

from contextlib import aclosing

from zett_agent.messages import (
    UserMessage,
)
from zett_agent.model import (
    ModelEventType,
    ModelRequest,
    ReasoningEffort,
)

from ..._compat import timeout
from ...agent.model_factory import create_model
from ...infra.log import get_logger
from ...schemas import ProviderConnection

logger = get_logger(__name__)

PROVIDER_TEST_TIMEOUT_SECONDS = 20.0


class ProviderConnectionTestError(RuntimeError):
    """Raised when a provider stream does not produce a successful response."""


async def verify_provider_connection(connection: ProviderConnection) -> None:
    """Verify credentials and model routing before the settings row is stored.

    The probe intentionally exposes no tools and asks for a tiny response. A
    terminal provider response is the success boundary; merely opening a
    transport or receiving partial deltas is not enough.
    """
    model = create_model(connection)
    request = ModelRequest(
        messages=[UserMessage(content="Reply only with OK.")],
        reasoning_effort=ReasoningEffort.OFF,
        parallel_tool_call=False,
    )
    try:
        async with timeout(PROVIDER_TEST_TIMEOUT_SECONDS):
            async with aclosing(model.stream(request)) as events:
                async for event in events:
                    if event.type == ModelEventType.RESPONSE:
                        return
        raise ProviderConnectionTestError("Provider stream ended without a response")
    finally:
        try:
            await model.aclose()
        except Exception:
            logger.exception("Provider test cleanup failed")
