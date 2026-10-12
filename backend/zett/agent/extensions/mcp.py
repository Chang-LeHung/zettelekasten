"""Build the runtime's MCP extension so one bad piece of MCP configuration cannot fail a request.

The runtime's ``McpExtension`` already skips a server that is down or slow while
it discovers tools, and keeps the last good server list when the file changes
mid-request. Two strict edges remain, and both sit in Zett's hands: it rejects a
whole file when one server entry is invalid, and it raises while being
constructed when the file cannot be parsed. An Agent is built per request, so
either one would fail every conversation, scheduled run, and channel turn
until the user edited ``mcp.json``.
"""

from collections.abc import Sequence
from pathlib import Path

from zett_agent.extensions.mcp import McpExtension, McpServer

from ...infra.log import get_logger

logger = get_logger(__name__)


def build_mcp_extension(
    *,
    servers: Sequence[McpServer],
    config_path: str | Path | None,
    server_keys: Sequence[str],
    strict_config: bool = False,
) -> McpExtension:
    """Return an MCP extension that degrades to fewer servers instead of raising.

    A file whose entries are individually invalid keeps its valid servers when
    ``strict_config`` is false. A file that is unreadable or not valid JSON has
    nothing to salvage, so the request carries only the explicitly supplied
    servers and the failure is logged; the next request reads the file again.
    """
    try:
        return McpExtension(
            servers=servers,
            config_path=config_path,
            server_keys=server_keys,
            strict_config=strict_config,
        )
    except (OSError, ValueError) as error:
        if config_path is None:
            # Nothing was read from a file, so this is a mistake in explicit servers.
            raise
        logger.warning("Ignoring unusable MCP configuration %s: %s", config_path, error)
    return McpExtension(servers=servers, config_path=None, server_keys=server_keys)
