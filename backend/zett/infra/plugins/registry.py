"""Discover and build Zett plugins from installed entry points.

Plugin code is third-party code, so this module treats every boundary as
untrusted: a broken entry point is skipped, and a failing factory surfaces as
``PluginLoadError`` instead of an arbitrary exception from the plugin.
"""

from collections.abc import Callable, Mapping
from importlib.metadata import entry_points

from ...infra.log import get_logger
from ...plugins import (
    JsonValue,
    KVStorage,
    NamespacedKV,
    Plugin,
    PluginContext,
    PluginKind,
    PluginLoadError,
)

logger = get_logger(__name__)

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
        """Register one factory under a plugin id.

        Raises:
            PluginLoadError: when the id is blank, the kind is not a
                ``PluginKind``, or the factory is not callable.
        """
        if not plugin_id.strip():
            raise PluginLoadError("Plugin id cannot be blank")
        if not isinstance(kind, PluginKind):
            raise PluginLoadError(f"Unknown plugin kind: {kind!r}")
        if not callable(factory):
            raise PluginLoadError(f"Plugin factory is not callable: {kind.value}/{plugin_id}")
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
        """Build one plugin instance whose keys live under its own scope.

        Raises:
            KeyError: when no plugin is registered for ``(kind, plugin_id)``.
            PluginLoadError: when the id or scope is blank, the store is not a
                ``KVStorage``, or the plugin factory raises. A broken plugin
                never leaks its own exception type across the boundary.
        """
        if not plugin_id.strip():
            raise PluginLoadError("Plugin id cannot be blank")
        if not scope_id.strip():
            raise PluginLoadError(f"Plugin scope cannot be blank: {kind.value}/{plugin_id}")
        if not isinstance(kv, KVStorage):
            raise PluginLoadError(f"Plugin KV store must be a KVStorage: {kind.value}/{plugin_id}")
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
        try:
            return factory(context)
        except Exception as error:
            raise PluginLoadError(f"Plugin failed to construct: {kind.value}/{plugin_id}") from error

    def discover(self, *, kind: PluginKind = PluginKind.CHANNEL) -> list[str]:
        """Load every installed entry point of one kind, skipping broken ones."""
        group = ENTRY_POINT_GROUPS[kind]
        discovered: list[str] = []
        try:
            candidates = list(entry_points(group=group))
        except Exception:
            logger.exception("Plugin entry-point discovery failed; group=%s", group)
            return discovered
        for entry in candidates:
            if not entry.name.strip():
                logger.warning("Skipping plugin entry point without a name; group=%s", group)
                continue
            try:
                self.register(entry.name, entry.load(), kind=kind)
            except Exception:
                logger.exception("Plugin entry point failed to load; group=%s name=%s", group, entry.name)
                continue
            discovered.append(entry.name)
        return discovered


def build_registry() -> PluginRegistry:
    """Return a registry populated from installed entry points."""
    registry = PluginRegistry()
    registry.discover()
    return registry


__all__ = ["ENTRY_POINT_GROUPS", "PluginFactory", "PluginRegistry", "build_registry"]
