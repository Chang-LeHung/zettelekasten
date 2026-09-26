"""Discover, configure, and run third-party agent plugins.

Discovery follows the channel-plugin rules: an entry point that cannot load,
construct, or answer for its own contract is skipped with a log line, and the
rest still load. Construction happens once per process, because a plugin may
open a client in ``start`` and Zett hands the same instances to every request.
"""

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points

from ...infra.log import get_logger
from ...plugins import (
    AGENT_PLUGIN_API_VERSION,
    AGENT_PLUGIN_ENTRY_POINT_GROUP,
    AgentPlugin,
    KVStorage,
    NamespacedKV,
    PluginContext,
    PluginLoadError,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LoadedAgentPlugin:
    """One installed agent plugin and the identity Zett knows it by."""

    plugin_id: str
    label: str
    plugin: AgentPlugin


def load_agent_plugins(
    *,
    entries: list[EntryPoint] | None = None,
    kv: KVStorage | None = None,
) -> tuple[LoadedAgentPlugin, ...]:
    """Construct every installed agent plugin, skipping the broken ones.

    ``entries`` and ``kv`` exist for tests and for a host that resolves plugins
    itself; production discovery reads the ``zett.agent`` entry-point group and
    the shared key-value store.
    """
    from ..plugins.kv import ZettKVStorage  # imported lazily so tests can inject a store

    candidates = sorted(
        entries if entries is not None else entry_points(group=AGENT_PLUGIN_ENTRY_POINT_GROUP), key=_entry_order
    )
    store = kv or ZettKVStorage()
    loaded: list[LoadedAgentPlugin] = []
    for entry in candidates:
        try:
            factory = entry.load()
            if not callable(factory):
                raise PluginLoadError("Entry point does not resolve to a factory")
            plugin = factory(
                PluginContext(
                    plugin_id=entry.name,
                    scope_id="agent",
                    kv=NamespacedKV(store, f"agent:{entry.name}:"),
                    config={},
                    secrets={},
                )
            )
            if not isinstance(plugin, AgentPlugin):
                raise PluginLoadError(f"Plugin is not an AgentPlugin: {type(plugin).__name__}")
            if plugin.api_version != AGENT_PLUGIN_API_VERSION:
                raise PluginLoadError(
                    f"Plugin targets agent plugin API {plugin.api_version}, this Zett implements "
                    f"{AGENT_PLUGIN_API_VERSION}"
                )
            if plugin.plugin_id and plugin.plugin_id != entry.name:
                logger.warning(
                    "Agent plugin id differs from its entry point; plugin_id=%s entry_point=%s",
                    plugin.plugin_id,
                    entry.name,
                )
        except Exception:
            logger.exception("Skipping agent plugin; plugin_id=%s", entry.name)
            continue
        loaded.append(LoadedAgentPlugin(plugin_id=entry.name, label=plugin.plugin_label or entry.name, plugin=plugin))
    logger.info(
        "Agent plugins loaded: %s",
        ", ".join(f"{item.plugin_id} ({item.label})" for item in loaded) or "none",
    )
    return tuple(loaded)


def _entry_order(entry: EntryPoint) -> str:
    return entry.name


class AgentPluginService:
    """Own the installed agent plugins and their process lifetime."""

    def __init__(self, *, loader: Callable[[], tuple[LoadedAgentPlugin, ...]] = load_agent_plugins) -> None:
        self._loader = loader
        self._loaded: tuple[LoadedAgentPlugin, ...] | None = None

    def describe(self) -> tuple[LoadedAgentPlugin, ...]:
        """Return every installed plugin, discovering once per process."""
        if self._loaded is None:
            self._loaded = self._loader()
        return self._loaded

    def plugins(self) -> tuple[AgentPlugin, ...]:
        """Return the plugin instances for one agent run."""
        return tuple(item.plugin for item in self.describe())

    async def start(self) -> None:
        """Start every installed plugin, keeping one failure to itself."""
        for item in self.describe():
            try:
                await item.plugin.start()
            except Exception:
                logger.exception("Agent plugin failed to start; plugin_id=%s", item.plugin_id)

    async def stop(self) -> None:
        """Stop every installed plugin in reverse order, keeping failures contained."""
        if self._loaded is None:
            return
        for item in reversed(self._loaded):
            try:
                await item.plugin.stop()
            except Exception:
                logger.exception("Agent plugin failed to stop; plugin_id=%s", item.plugin_id)

    def reset(self) -> None:
        """Forget discovered plugins so the next call discovers them again."""
        self._loaded = None


agent_plugin_service = AgentPluginService()

__all__ = ["AgentPluginService", "LoadedAgentPlugin", "agent_plugin_service", "load_agent_plugins"]
