"""MCP is best effort: one bad server or one bad file never fails a request."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from zett_agent.extensions.mcp import DEFAULT_MCP_SERVER_KEYS, McpExtension, McpHttpServer
from zett_agent.storage import SQLiteSessionStorage

from zett.agent.config import ZettelkastenAgentConfig
from zett.agent.extensions.mcp import build_mcp_extension
from zett.agent.zettelkasten import ZettelkastenAgent


def write_config(path: Path, servers: dict[str, object]) -> Path:
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return path


def test_an_invalid_server_entry_keeps_the_valid_servers(tmp_path: Path) -> None:
    path = write_config(
        tmp_path / "mcp.json",
        {
            "docs": {"type": "streamable-http", "url": "https://docs.test/mcp"},
            "broken": {"type": "streamable-http"},
            "also-broken": "not an object",
        },
    )

    extension = build_mcp_extension(servers=(), config_path=path, server_keys=DEFAULT_MCP_SERVER_KEYS)

    assert [server.name for server in extension.servers] == ["docs"]


def test_strict_configuration_is_still_available(tmp_path: Path) -> None:
    path = write_config(tmp_path / "mcp.json", {"broken": {"type": "streamable-http"}})

    # Strict mode rejects the file, and the fallback keeps the request alive.
    extension = build_mcp_extension(
        servers=(), config_path=path, server_keys=DEFAULT_MCP_SERVER_KEYS, strict_config=True
    )

    assert extension.servers == ()


@pytest.mark.parametrize("content", ["{not json", "[]", "{}", '{"mcpServers": 3}'])
def test_an_unparseable_file_contributes_no_servers_but_keeps_explicit_ones(tmp_path: Path, content: str) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(content, encoding="utf-8")
    explicit = McpHttpServer("internal", "https://internal.test/mcp")

    extension = build_mcp_extension(servers=(explicit,), config_path=path, server_keys=DEFAULT_MCP_SERVER_KEYS)

    assert extension.servers == (explicit,)


def test_a_mistake_in_explicit_servers_is_not_hidden() -> None:
    twice = (McpHttpServer("a", "https://a.test/mcp"), McpHttpServer("a", "https://b.test/mcp"))

    with pytest.raises(ValueError):
        build_mcp_extension(servers=twice, config_path=None, server_keys=DEFAULT_MCP_SERVER_KEYS)


async def test_an_agent_is_built_and_started_with_a_broken_mcp_file(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text("{not json", encoding="utf-8")
    storage = SQLiteSessionStorage(tmp_path / "agent.db")
    try:
        agent = await ZettelkastenAgent(
            ZettelkastenAgentConfig("broken-mcp", storage=storage, mcp_config_path=path)
        ).initialize()

        assert any(isinstance(item, McpExtension) for item in agent.agent.extensions)
    finally:
        await storage.close()


async def test_a_server_that_cannot_connect_only_drops_its_own_tools(tmp_path: Path) -> None:
    """The runtime skips an unavailable server; Zett's wiring must not undo that."""
    path = write_config(
        tmp_path / "mcp.json",
        {
            "down": {"type": "streamable-http", "url": "https://down.test/mcp"},
            "up": {"type": "streamable-http", "url": "https://up.test/mcp"},
        },
    )

    @asynccontextmanager
    async def factory(server):
        if server.name == "down":
            raise ConnectionError("refused")
        yield SimpleNamespace(
            list_tools=lambda cursor=None: _tools(),
        )

    async def _tools():
        tool = SimpleNamespace(name="search", description="Search", input_schema={"type": "object"})
        return SimpleNamespace(tools=[tool], next_cursor=None)

    extension = build_mcp_extension(servers=(), config_path=path, server_keys=DEFAULT_MCP_SERVER_KEYS)
    extension._client_factory = factory  # type: ignore[assignment]
    registered: list[str] = []

    class Context:
        tools: dict[str, object] = {}

        def register_tool(self, tool) -> None:
            registered.append(tool.name)

    context = Context()

    await extension.on_tool(context)  # type: ignore[arg-type]
    try:
        assert registered == ["up__search"]
    finally:
        await extension._close(context)  # type: ignore[arg-type]
