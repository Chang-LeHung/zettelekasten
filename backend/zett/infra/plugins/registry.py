"""Discover and build Zett plugins from installed entry points."""

from collections.abc import Callable, Mapping
from importlib.metadata import entry_points

from ...plugins import JsonValue, KVStorage, NamespacedKV, Plugin, PluginContext, PluginKind

PluginFactory = Callable[[PluginContext], Plugin]

# Each plugin kind discovers through its own entry-point group, so adding a new
# kind needs a new group rather than a rewrite of the registry.
ENTRY_POINT_GROUPS: dict[PluginKind, str] = {PluginKind.CHANNEL: "zett.channels"}


class PluginRegistry:
    """Map ``(kind, plugin_id)`` to a factory and build isolated instances."""

    def __init__(self) -> None:
        self._factories: dict[tuple[PluginKind, str], PluginFactory] = {}

    def register(
        self,
        plugin_id: str,
        factory: PluginFactory,
        *,
        kind: PluginKind = PluginKind.CHANNEL,
    ) -> None:
        """Register one factory under a plugin id."""
        self._factories[(kind, plugin_id)] = factory

    def ids(self, *, kind: PluginKind = PluginKind.CHANNEL) -> list[str]:
        """Return the registered plugin ids of one kind."""
        return sorted(plugin_id for (registered_kind, plugin_id) in self._factories if registered_kind is kind)

    def create(
        self,
        plugin_id: str,
        *,
        scope_id: str,
        kv: KVStorage,
        config: Mapping[str, JsonValue] | None = None,
        secrets: Mapping[str, str] | None = None,
        kind: PluginKind = PluginKind.CHANNEL,
    ) -> Plugin:
        """Build one plugin instance whose keys live under its own scope."""
        factory = self._factories.get((kind, plugin_id))
        if factory is None:
            raise KeyError(f"Plugin not registered: {kind.value}/{plugin_id}")
        context = PluginContext(
            plugin_id=plugin_id,
            scope_id=scope_id,
            kv=NamespacedKV(kv, f"{kind.value}:{plugin_id}:{scope_id}:"),
            config=dict(config or {}),
            secrets=dict(secrets or {}),
        )
        return factory(context)

    def discover(self, *, kind: PluginKind = PluginKind.CHANNEL) -> list[str]:
        """Load every installed entry point of one kind and return their ids."""
        discovered: list[str] = []
        for entry in entry_points(group=ENTRY_POINT_GROUPS[kind]):
            self.register(entry.name, entry.load(), kind=kind)
            discovered.append(entry.name)
        return discovered


def build_registry() -> PluginRegistry:
    """Return a registry populated from installed entry points."""
    registry = PluginRegistry()
    registry.discover()
    return registry


__all__ = ["ENTRY_POINT_GROUPS", "PluginFactory", "PluginRegistry", "build_registry"]
