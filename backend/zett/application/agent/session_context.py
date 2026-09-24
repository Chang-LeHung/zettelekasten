"""Persist and reconstruct the latest context-composition view per session."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from zett_agent import ModelRequest, SQLiteSessionStorage, SystemMessage

from ...agent.extensions.context_composition import context_composition
from ...infra.persistence.dao import KeyValueStorage, key_value_storage

SESSION_CONTEXT_KEY_PREFIX = "sessions.context-composition."


class SessionContextComposition(BaseModel):
    """Normalized proportions used by the compact composer visualization."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: float = Field(ge=0, le=1)
    tool_prompt: float = Field(ge=0, le=1)
    tool_output: float = Field(ge=0, le=1)
    user: float = Field(ge=0, le=1)
    assistant: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> SessionContextComposition:
        """Require one complete distribution while tolerating float rounding."""
        if abs(sum(self.model_dump().values()) - 1) > 0.001:
            raise ValueError("Context composition ratios must sum to one")
        return self


class SessionContextCompositionService:
    """Remember the latest live estimate and recover it for historical sessions."""

    def __init__(self, storage: KeyValueStorage = key_value_storage) -> None:
        self._storage = storage

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{SESSION_CONTEXT_KEY_PREFIX}{session_id}"

    async def get(self, session_id: str) -> SessionContextComposition | None:
        """Return the most recently observed composition, when available."""
        record = await self._storage.get(self._key(session_id))
        return None if record is None else SessionContextComposition.model_validate(record.value)

    async def remember(self, session_id: str, ratios: dict[str, float]) -> SessionContextComposition:
        """Validate and replace the session's latest composition snapshot."""
        composition = SessionContextComposition.model_validate(ratios)
        await self._storage.update(self._key(session_id), composition.model_dump(mode="json"))
        return composition

    async def get_or_estimate(
        self,
        session_id: str,
        storage: SQLiteSessionStorage,
        system_prompt: str,
    ) -> SessionContextComposition:
        """Load a snapshot or estimate old history that predates this feature.

        The live extension records the complete request, including tool schemas
        and dynamic system context. A legacy session has no such snapshot, so
        its fallback is reconstructed from the current compacted Raw Log view
        and the base system prompt. The next real model call replaces it with
        the complete live estimate.
        """
        existing = await self.get(session_id)
        if existing is not None:
            return existing
        view = await storage.load(session_id)
        request = ModelRequest(messages=(SystemMessage(content=system_prompt), *view.messages))
        return await self.remember(session_id, context_composition(request))

    async def delete(self, session_id: str) -> bool:
        """Remove the UI snapshot when its owning Agent session is deleted."""
        return await self._storage.delete(self._key(session_id))


session_context_composition_service = SessionContextCompositionService()
