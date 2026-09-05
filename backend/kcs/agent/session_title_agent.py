from collections.abc import Callable

from kcs_agent import AgentModel, SystemMessage, UserMessage
from pydantic import BaseModel, Field, field_validator

from ..infra.agent_session_dao import agent_session_storage
from ..infra.logging import get_logger
from ..infra.provider_adapter import close_agent_model, create_agent_model
from ..infra.structured_output import structured_output
from ..models import AIProviderRuntime
from ..schemas import AgentMessageRole, AgentSessionCreate

logger = get_logger(__name__)


class SessionTitleOutput(BaseModel):
    """Schema-enforced model output for the one-time conversation title."""

    title: str = Field(min_length=1, max_length=100, description="Concise title in the user's language")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str:
        """Normalize harmless presentation syntax without parsing free-form model JSON."""
        lines = str(value).strip().splitlines()
        title = (lines[0] if lines else "").strip().lstrip("#").strip()
        if len(title) >= 2 and title[0] == title[-1] and title[0] in {'"', "'", "`"}:
            title = title[1:-1].strip()
        return title[:100].rstrip()


class SessionTitleAgent:
    """Silently summarize a completed conversation into a stable display title."""

    name = "KCS Session Title Agent"

    def __init__(
        self,
        model_factory: Callable[[int | None], tuple[AIProviderRuntime, AgentModel]] = create_agent_model,
    ) -> None:
        """Configure the provider-neutral model factory used for title generation."""
        self._model_factory = model_factory

    async def summarize(self, session_id: str, provider_id: int | None) -> None:
        """Generate a title once, immediately after the first completed agent response."""
        model: AgentModel | None = None
        try:
            session = agent_session_storage.get(session_id)
            if session is None:
                return
            if (
                session.title
                or session.metadata.get("title_finalized")
                or session.metadata.get("title_generation_attempted")
            ):
                return
            messages = [
                message
                for message in session.messages
                if message.role in (AgentMessageRole.USER, AgentMessageRole.ASSISTANT) and message.content.strip()
            ]
            if not any(
                message.role == AgentMessageRole.ASSISTANT and not message.metadata.get("cancelled")
                for message in messages
            ):
                return
            attempted_metadata = {**session.metadata, "title_generation_attempted": True}
            agent_session_storage.update(
                session_id,
                AgentSessionCreate(title=session.title, metadata=attempted_metadata),
            )
            transcript = "\n".join(f"{message.role.value}: {message.content}" for message in messages)[-12000:]
            _, model = self._model_factory(provider_id)
            response = await structured_output(
                model,
                SessionTitleOutput,
                [
                    SystemMessage(
                        content="Create one concise title for this conversation. Use the user's language and preserve the main technical terms."
                    ),
                    UserMessage(content=transcript),
                ],
            )
            title = SessionTitleOutput.model_validate(response).title
            current = agent_session_storage.get(session_id)
            if current is None or current.title or current.metadata.get("title_source") == "user":
                return
            metadata = {
                **current.metadata,
                "title_generated_by": self.name,
                "title_message_count": len(messages),
                "title_source": "agent",
                "title_finalized": True,
            }
            agent_session_storage.update(session_id, AgentSessionCreate(title=title, metadata=metadata))
        except Exception:
            logger.exception("Session title generation failed for session %s", session_id)
        finally:
            if model is not None:
                await close_agent_model(model)


session_title_agent = SessionTitleAgent()
