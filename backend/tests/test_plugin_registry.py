"""Zett plugin registry registration, scoping, and KV adapter behavior."""

import pytest

from zett.infra.plugins import PluginRegistry, ZettKVStorage
from zett.plugins import Plugin, PluginContext, PluginKind


class StubPlugin(Plugin):
    """Minimal plugin that keeps its context and lifecycle flags."""

    kind = PluginKind.CHANNEL
    plugin_id = "stub"

    def __init__(self, context: PluginContext) -> None:
        self.context = context
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False


def test_registry_registers_and_lists_ids() -> None:
    registry = PluginRegistry()
    registry.register("stub", StubPlugin)
    registry.register("other", StubPlugin)

    assert registry.ids() == ["other", "stub"]
    assert registry.ids(kind=PluginKind.CHANNEL) == ["other", "stub"]


def test_registry_rejects_unknown_plugin() -> None:
    registry = PluginRegistry()

    with pytest.raises(KeyError):
        registry.create("missing", scope_id="scope", kv=ZettKVStorage())


async def test_registry_scopes_plugin_kv_per_scope() -> None:
    registry = PluginRegistry()
    registry.register("stub", StubPlugin)
    kv = ZettKVStorage()

    first = registry.create("stub", scope_id="a", kv=kv)
    second = registry.create("stub", scope_id="b", kv=kv)
    await first.context.kv.set("cursor", 1)
    await second.context.kv.set("cursor", 2)

    assert await first.context.kv.get("cursor") == 1
    assert await second.context.kv.get("cursor") == 2
    assert await kv.get("channel:stub:a:cursor") == 1
    assert await kv.get("channel:stub:b:cursor") == 2


async def test_registry_passes_config_and_secrets() -> None:
    registry = PluginRegistry()
    registry.register("stub", StubPlugin)

    plugin = registry.create(
        "stub",
        scope_id="scope",
        kv=ZettKVStorage(),
        config={"base_url": "https://example.invalid"},
        secrets={"bot_token": "token-1"},
    )

    assert plugin.context.config == {"base_url": "https://example.invalid"}
    assert plugin.context.secrets == {"bot_token": "token-1"}
    assert plugin.context.plugin_id == "stub"
    assert plugin.context.scope_id == "scope"


async def test_zet_kv_storage_round_trips_and_iterates_by_prefix() -> None:
    kv = ZettKVStorage()
    await kv.set("im:test:a", {"n": 1})
    await kv.set("im:test:b", [1, 2, 3])

    assert await kv.get("im:test:a") == {"n": 1}
    assert await kv.iter_prefix("im:test:") == [("im:test:a", {"n": 1}), ("im:test:b", [1, 2, 3])]
    assert await kv.delete("im:test:a") is True
    assert await kv.delete("im:test:a") is False
    assert await kv.get("im:test:a") is None
