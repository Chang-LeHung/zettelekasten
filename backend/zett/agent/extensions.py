"""Zett-specific artifact tools and conversation context."""

import asyncio
import json

from zett_agent import AgentExtension, AgentRunContext, SystemMessage, tool

from ..infra.dao import artifact_storage
from ..models import ArtifactListOptions
from ..schemas import AgentArtifact, AgentArtifactWrite, ArtifactContent, ArtifactStatus


class ZettelkastenExtension(AgentExtension):
    """Expose typed artifact operations and current artifacts to the model."""

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register artifact tools bound to the current conversation."""
        session_id = context.config.session_id

        @tool
        def create_artifact(content: ArtifactContent, raw_content: str | None = None) -> AgentArtifact:
            """Create a draft card, article, or image artifact in this conversation.

            Args:
                content: Complete type-specific artifact content.
                raw_content: Optional original user text represented by the artifact.

            Snippet:
                create_artifact(content={"artifact_type": "card", "title": "...", "content": "..."})

            Guidelines:
                - Create an artifact only when it is a useful output of the conversation.
                - Keep newly generated artifacts in draft state until the user asks to save them.
            """
            return artifact_storage.create(
                AgentArtifactWrite(session_id=session_id, content=content, raw_content=raw_content)
            )

        @tool
        def update_artifact(artifact_id: str, content: ArtifactContent) -> AgentArtifact:
            """Replace the editable content of an existing conversation artifact.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.
                content: Complete replacement content.

            Snippet:
                update_artifact(artifact_id="...", content={"artifact_type": "article", "title": "..."})

            Guidelines:
                - Read the artifact information already present in context before replacing it.
            """
            current = self._artifact(session_id, artifact_id)
            return artifact_storage.update(
                artifact_id,
                AgentArtifactWrite(
                    session_id=session_id,
                    content=content,
                    raw_content=current.raw_content,
                    status=current.status,
                    metadata=current.metadata,
                ),
            )

        @tool
        def save_artifact(artifact_id: str) -> AgentArtifact:
            """Mark one draft artifact as saved after explicit user approval.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                save_artifact(artifact_id="...")

            Guidelines:
                - Call this only when the user explicitly requests saving the artifact.
            """
            current = self._artifact(session_id, artifact_id)
            return artifact_storage.update(
                artifact_id,
                AgentArtifactWrite(
                    session_id=session_id,
                    content=current.content,
                    raw_content=current.raw_content,
                    status=ArtifactStatus.SAVED,
                    metadata=current.metadata,
                ),
            )

        @tool
        def delete_artifact(artifact_id: str) -> bool:
            """Delete one artifact from this conversation.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                delete_artifact(artifact_id="...")

            Guidelines:
                - Delete only when the user's intent is explicit.
            """
            self._artifact(session_id, artifact_id)
            return artifact_storage.delete(artifact_id)

        for registered in (create_artifact, update_artifact, save_artifact, delete_artifact):
            context.register_tool(registered)

    async def on_state(self, context: AgentRunContext) -> None:
        """Expose current artifacts as model context."""
        session_id = context.config.session_id
        artifacts = await asyncio.to_thread(
            artifact_storage.list,
            ArtifactListOptions(session_id=session_id, limit=500),
        )
        payload = {
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        }
        if payload["artifacts"]:
            workspace = SystemMessage(
                content="Current Zett conversation workspace:\n" + json.dumps(payload, ensure_ascii=False)
            )
            instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
            dialogue = [item for item in context.state.messages if not isinstance(item, SystemMessage)]
            context.state.messages[:] = [*instructions, workspace, *dialogue]

    @staticmethod
    def _artifact(session_id: str, artifact_id: str) -> AgentArtifact:
        artifact = artifact_storage.get_for_session(session_id, artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact not found in this session: {artifact_id}")
        return artifact
