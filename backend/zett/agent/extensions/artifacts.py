"""Zett-specific artifact tools."""

from typing import Annotated

from pydantic import Field
from zett_agent.agent import (
    AgentRunContext,
)
from zett_agent.extensions.base import (
    AgentExtension,
)
from zett_agent.tools.base import (
    tool,
)

from ...application.artifacts.artifact_pruner import AgentArtifactPreview, ArtifactPruner
from ...application.tags.tagging import tag_service
from ...infra.persistence.dao import artifact_storage
from ...schemas import (
    AgentArtifactEntity,
    AgentArtifactWrite,
    ArtifactContentPatch,
    ArtifactCreateContent,
    ArtifactListOptions,
    ArtifactStatus,
    ArtifactType,
    apply_artifact_patch,
)

artifact_pruner = ArtifactPruner()


class ArtifactExtension(AgentExtension):
    """Expose typed artifact operations to the model."""

    def __init__(self, *, allow_direct_current_session_edits: bool = False) -> None:
        """Configure whether headless runs may write current-session content directly."""
        self.allow_direct_current_session_edits = allow_direct_current_session_edits

    # Do not add an on_state() workspace system message. A conversation starts
    # with no artifacts, and later create/update/delete tool calls and results
    # already remain in model context. Rebuilding a full snapshot in the leading
    # system prefix would invalidate prompt-cache prefixes without adding new
    # information the model has not already seen.

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register artifact tools bound to the current conversation."""
        session_id = context.config.session_id

        @tool
        async def create_artifact(
            content: ArtifactCreateContent, raw_content: str | None = None
        ) -> AgentArtifactEntity:
            """Create a draft card, article, image, slide deck, or LaTeX PDF in this conversation.

            Args:
                content: Complete type-specific artifact content.
                raw_content: Optional original user text represented by the artifact.

            Snippet:
                create_artifact(content={"artifact_type": "card", "title": "...", "content": "..."})
                create_artifact(content={"artifact_type": "image", "title": "...", "asset_path": "assets/sessions/<session>/<asset>.png"})
                create_artifact(content={"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"})
                create_artifact(content={"artifact_type": "slides", "title": "...", "content": "# Topic\\n\\n--\\n\\n## Detail\\n\\n---\\n\\n# Next topic"})
                create_artifact(content={"artifact_type": "slides", "title": "Processes", "content": "<!-- slide:cover -->\\n# Processes\\n\\n## From programs to execution\\n\\nAuthor name\\n\\n[Website](https://example.com)\\n\\n---\\n# Overview\\n\\n--\\n## Process state\\n\\n- One idea"})

            Guidelines:
                - Read the 'zett-artifact-syntax' skill with read_skill before writing any body; it carries the exact Markdown, figure, cover, HTML page, and slide separator rules.
                - Create an artifact only when it is a useful output of the conversation, and keep it in draft state until the user saves it.
                - Creation stores the supplied content directly; later updates write draft content only, and never claim an artifact is saved unless the user saves it.
                - For a LaTeX PDF, pass only pdf_name and treat the returned content.project_path as authoritative: never guess it, and preserve it when updating.
                - For an image you produced locally, write or download the file first, upload it with upload_asset, and pass the storage_path it returns as asset_path; an external image uses source_url instead. An asset_path this conversation does not own, or one that names no file, is refused.
                - A LaTeX project is your git repository: init it, keep the build output in a '.gitignore', and commit each meaningful change from the project directory with a Conventional Commit message. Zett never touches that history, and it refuses to save while the project is not a committed git repository.
                - Compile with the shell tools: a missing or invalid PDF leaves metadata and saving intact, and the preview appears once project_path/pdf_name exists.
            """
            created = await artifact_storage.create(
                AgentArtifactWrite(session_id=session_id, content=content, raw_content=raw_content)
            )
            return await tag_service.sync_confirmed_suggestions(created)

        @tool
        async def get_artifact(artifact_id: str) -> AgentArtifactEntity:
            """Return one artifact with its published content and its draft.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                get_artifact(artifact_id="...")

            Guidelines:
                - Use to fetch the latest content of an artifact after changes.
                - `content` is what the user published; `draft_content` is the working copy you edit, and the two are equal right after a save.
            """
            return await self._artifact(session_id, artifact_id)

        @tool
        async def query_artifacts(
            query: str | None = None,
            artifact_types: tuple[ArtifactType, ...] = (),
            statuses: tuple[ArtifactStatus, ...] = (),
            all_sessions: bool = False,
            limit: Annotated[int, Field(ge=1, le=500)] = 20,
        ) -> list[AgentArtifactPreview]:
            """Search artifacts by title text, type, and status.

            Every result carries `published_content`, which is what the user saved,
            and `draft_content`, which is the working copy you edit.

            Args:
                query: Case-insensitive text matched against artifact titles.
                artifact_types: Optional kinds such as card, article, image, slides, or latex_pdf.
                statuses: Optional lifecycle states such as draft or saved.
                all_sessions: When true, search across every session instead of only this conversation.
                limit: Maximum number of artifacts to return.

            Snippet:
                query_artifacts(query="paper", statuses=["saved"])
                query_artifacts(artifact_types=["card"], all_sessions=True)

            Guidelines:
                - Use it to find an artifact ID before reading or updating one, and set all_sessions when the user asks about other conversations.
                - Results are bounded previews, so call get_artifact before updating when the complete content matters.
            """
            artifacts = await artifact_storage.list(
                ArtifactListOptions(
                    session_id=None if all_sessions else session_id,
                    artifact_types=tuple(item.value for item in artifact_types),
                    statuses=tuple(item.value for item in statuses),
                    query=query,
                    limit=limit,
                )
            )
            return artifact_pruner.prune(artifacts)

        @tool
        async def update_artifact(artifact_id: str, patch: ArtifactContentPatch) -> AgentArtifactEntity:
            """Change part of one artifact's draft, including an artifact from another conversation.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.
                patch: Fields to change, selected by artifact_type. Omitted or null fields keep their
                    current value, an empty string or list clears one, and content_edits replaces exact
                    body snippets instead of resending the body. Changing artifact_type replaces the
                    whole content, so include every required field of the new type.

            Snippet:
                update_artifact(artifact_id="...", patch={"artifact_type": "card", "title": "Sharper title"})
                update_artifact(artifact_id="...", patch={"artifact_type": "article", "content_edits": [{"old_text": "Old paragraph", "new_text": "Sharper paragraph"}]})
                update_artifact(artifact_id="...", patch={"artifact_type": "article", "content_edits": [{"old_text": "Zettelkasten", "new_text": "Zettelkasten Agent", "replace_all": True}]})
                update_artifact(artifact_id="...", patch={"artifact_type": "slides", "content": "<!-- slide:cover -->\\n# Processes\\n\\n## Optional subtitle\\n\\n---\\n# Overview\\n\\n--\\n## Details"})

            Guidelines:
                - Read the 'zett-artifact-syntax' skill with read_skill before changing a body, and preserve the structure that skill defines.
                - Send only the fields you change; untouched fields keep their current value, and the update writes draft content only. The published artifact changes only when the user saves.
                - Fix part of a body with content_edits instead of resending it: old_text must match exactly once unless replace_all is set, and content and content_edits never travel together.
                - The artifact may belong to another conversation when its ID came from query_artifacts(all_sessions=True); the owning session is preserved.
                - A latex_pdf patch only changes the reference: edit the project files and commit each meaningful change from the project directory, because saving is refused while the project has uncommitted changes.
            """
            current = await artifact_storage.get(artifact_id)
            if current is None:
                raise ValueError(f"Artifact not found: {artifact_id}")
            base = current.editable_content
            if base is None:
                raise ValueError(f"Artifact has no content to update: {artifact_id}")
            updated_content = apply_artifact_patch(base, patch)
            direct_edit = self.allow_direct_current_session_edits and current.session_id == session_id
            updated = await artifact_storage.update(
                artifact_id,
                AgentArtifactWrite(
                    session_id=current.session_id,
                    content=updated_content if direct_edit else current.content,
                    draft_content=None if direct_edit else updated_content,
                    raw_content=current.raw_content,
                    status=current.status,
                    metadata=current.metadata,
                ),
            )
            return await tag_service.sync_confirmed_suggestions(updated)

        if self.allow_direct_current_session_edits:
            update_artifact.guidelines = (
                *update_artifact.guidelines,
                "Direct current-session edits are enabled: updating an artifact owned by this "
                "session replaces content directly and clears any pending draft.",
            )

        @tool
        async def delete_artifact(artifact_id: str) -> bool:
            """Delete one artifact from this conversation.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                delete_artifact(artifact_id="...")

            Guidelines:
                - Delete only when the user's intent is explicit.
            """
            await self._artifact(session_id, artifact_id)
            return await artifact_storage.delete(artifact_id)

        for registered in (
            create_artifact,
            get_artifact,
            query_artifacts,
            update_artifact,
            delete_artifact,
        ):
            context.register_tool(registered)

    @staticmethod
    async def _artifact(session_id: str, artifact_id: str) -> AgentArtifactEntity:
        artifact = await artifact_storage.get_for_session(session_id, artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact not found in this session: {artifact_id}")
        return artifact
