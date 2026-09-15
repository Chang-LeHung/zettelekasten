"""Agent extension for persistent library tag management."""

import asyncio
import json

from zett_agent import AgentExtension, AgentRunContext, SystemMessage, tool

from ..application.tagging import tag_service
from ..infra.dao import artifact_storage
from ..schemas import AgentArtifact, TagOut, TagTreeOut


class TagExtension(AgentExtension):
    """Let the model inspect and explicitly manage the real tag taxonomy."""

    async def on_tool(self, context: AgentRunContext) -> None:
        session_id = context.config.session_id

        @tool
        def create_tag(path: str, description: str | None = None, color: str | None = None) -> TagOut:
            """Create a persistent library tag and any missing parent tags.

            Args:
                path: Slash-delimited hierarchy such as "Engineering/Python".
                description: Optional short explanation of the category.
                color: Optional CSS color used by the Library UI.

            Snippet:
                create_tag(path="Engineering/Python", description="Python language knowledge")

            Guidelines:
                - Create a real tag only when the user explicitly asks for it or approves a durable classification.
                - Reuse an existing path when it already expresses the same category.
                - Keep segments short, stable, and meaningful; do not encode dates or confidence in the path.
            """
            return tag_service.create_path(path, description=description, color=color)

        @tool
        def list_tags() -> list[TagTreeOut]:
            """List the complete persistent tag tree and artifact counts.

            Snippet:
                list_tags()

            Guidelines:
                - Inspect existing tags before creating a near-duplicate category.
            """
            tag_service.backfill_legacy_artifacts()
            return tag_service.list_tree()

        @tool
        def update_tag(
            tag_id: str,
            path: str | None = None,
            description: str | None = None,
            color: str | None = None,
        ) -> TagOut:
            """Rename, move, or restyle one persistent leaf tag.

            Args:
                tag_id: Stable tag UUID returned by list_tags.
                path: Optional replacement hierarchy path.
                description: Optional replacement description.
                color: Optional replacement CSS color.

            Guidelines:
                - Use the stable ID returned by list_tags; never guess it.
                - Tags with children cannot be moved or renamed individually.
            """
            return tag_service.update(tag_id, path=path, description=description, color=color)

        @tool
        def delete_tag(tag_id: str, recursive: bool = False, force: bool = False) -> bool:
            """Delete a persistent tag with explicit safeguards.

            Args:
                tag_id: Stable tag UUID returned by list_tags.
                recursive: Also delete descendant tags.
                force: Remove assignments from saved artifacts.

            Guidelines:
                - Delete only after an explicit user request.
                - Never set recursive or force unless the user has approved the wider effect.
            """
            return tag_service.delete(tag_id, recursive=recursive, force=force)

        @tool
        def set_artifact_tags(artifact_id: str, paths: list[str]) -> AgentArtifact:
            """Replace the confirmed persistent tags assigned to one saved artifact.

            Args:
                artifact_id: Artifact UUID from the current conversation workspace.
                paths: Complete replacement set of hierarchical tag paths; an empty list clears it.

            Snippet:
                set_artifact_tags(artifact_id="...", paths=["Engineering/Python", "Concurrency"])

            Guidelines:
                - The artifact must belong to this conversation and already be saved.
                - This is a complete replacement, not an append operation.
                - Missing paths are created as real tags, including their parent nodes.
            """
            if artifact_storage.get_for_session(session_id, artifact_id) is None:
                raise ValueError(f"Artifact not found in this session: {artifact_id}")
            return tag_service.replace_artifact_tags(artifact_id, paths)

        for registered in (create_tag, list_tags, update_tag, delete_tag, set_artifact_tags):
            context.register_tool(registered)

    async def on_state(self, context: AgentRunContext) -> None:
        """Expose the real taxonomy so suggestions can reuse stable paths."""
        await asyncio.to_thread(tag_service.backfill_legacy_artifacts)
        tags = await asyncio.to_thread(tag_service.list_tree)
        if not tags:
            return
        message = SystemMessage(
            content="Current persistent library tags:\n"
            + json.dumps([tag.model_dump(mode="json") for tag in tags], ensure_ascii=False)
        )
        instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
        dialogue = [item for item in context.state.messages if not isinstance(item, SystemMessage)]
        context.state.messages[:] = [*instructions, message, *dialogue]
