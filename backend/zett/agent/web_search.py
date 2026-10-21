"""Turn a provider's web search setting into the hosted tool its protocol declares.

Web search is not a local tool: the model endpoint runs it and returns the cited
results inside the same response. A configuration therefore only decides whether
to declare the tool and under which wire type, and the declaration has to match
the protocol the adapter speaks.
"""

from zett_agent.model import ServerToolDefinition

from zett.schemas import ProviderConnection, ProviderType
from zett.schemas.providers import default_web_search_name

#: Name Anthropic's wire schema requires beside a versioned ``web_search_*`` type.
ANTHROPIC_SEARCH_NAME = "web_search"


def web_search_enabled(connection: ProviderConnection) -> bool:
    """Return whether the provider configuration asks for hosted web search."""
    return connection.metadata.get("web_search", False) is True


def web_search_tools(connection: ProviderConnection) -> tuple[ServerToolDefinition, ...]:
    """Return the hosted search declaration for one connection, or nothing when it is off.

    A stored name wins over the protocol default so a gateway that documents its
    own search type can be reached without a code change. Anthropic's schema
    needs a ``name`` next to a versioned type, which is filled in here because
    every other protocol rejects the extra key.
    """
    if not web_search_enabled(connection):
        return ()
    response = connection.metadata.get("response", False) is True
    configured = connection.metadata.get("web_search_name")
    name = configured.strip() if isinstance(configured, str) else ""
    name = name or default_web_search_name(connection.provider, connection.model, response=response)
    if not name:
        return ()
    anthropic = connection.provider in {ProviderType.ANTHROPIC, ProviderType.ANTHROPIC_COMPATIBLE}
    if anthropic and name.startswith("web_search_"):
        return (ServerToolDefinition(name, {"name": ANTHROPIC_SEARCH_NAME}),)
    return (ServerToolDefinition(name),)


__all__ = ["ANTHROPIC_SEARCH_NAME", "web_search_enabled", "web_search_tools"]
