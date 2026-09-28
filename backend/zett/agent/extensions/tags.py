"""Agent extension for persistent library tag management."""

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

from ...application.artifacts.artifact_views import ArtifactReceipt, artifact_receipt
from ...application.assets.asset_views import StaticAssetReceipt, static_asset_receipt
from ...application.assets.static_assets import static_asset_service
from ...application.tags.tagging import tag_service
from ...infra.persistence.dao import artifact_storage
from ...schemas import TagEntity, TagTargetType, TagTreeEntity


class TagExtension(AgentExtension):
    """Let the model inspect and explicitly manage the real tag taxonomy."""

    # Do not add an on_state() tag taxonomy system message. A conversation
    # starts with no session-created tags, and later tag operations already
    # remain in model context as tool calls and results. Rebuilding the complete
    # taxonomy in the leading system prefix would invalidate prompt-cache
    # prefixes whenever a tag changes without adding unseen information.

    async def on_tool(self, context: AgentRunContext) -> None:
        session_id = context.config.session_id

        @tool
        async def create_tag(path: str, description: str | None = None, color: str | None = None) -> TagEntity:
            """Create a tag in the artifact library and any missing parent tags.

            Args:
                path: Slash-delimited hierarchy such as "Engineering/Python".
                description: Optional short explanation of the category.
                color: Optional CSS color used by the Library UI.

            Snippet:
                create_tag(path="Engineering/Python", description="Python language knowledge")

            Guidelines:
                - Tags classify artifacts here; the static asset library keeps its own separate tree.
                - Create a real tag only when the user explicitly asks for it or approves a durable classification.
                - Reuse an existing path when it already expresses the same category.
                - Keep segments short, stable, and meaningful; do not encode dates or confidence in the path.
            """
            return await tag_service.create_path(
                path,
                TagTargetType.ARTIFACT,
                description=description,
                color=color,
            )

        @tool
        async def list_tags() -> list[TagTreeEntity]:
            """List the artifact library's tag tree and assignment counts.

            Snippet:
                list_tags()

            Guidelines:
                - Inspect existing tags before creating a near-duplicate category.
            """
            return await tag_service.list_tree(TagTargetType.ARTIFACT)

        @tool
        async def update_tag(
            tag_id: str,
            path: str | None = None,
            description: str | None = None,
            color: str | None = None,
        ) -> TagEntity:
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
            return await tag_service.update(tag_id, path=path, description=description, color=color)

        @tool
        async def delete_tag(tag_id: str, recursive: bool = False, force: bool = False) -> bool:
            """Delete a persistent tag with explicit safeguards.

            Args:
                tag_id: Stable tag UUID returned by list_tags.
                recursive: Also delete descendant tags.
                force: Remove assignments from saved artifacts.

            Guidelines:
                - Delete only after an explicit user request.
                - Never set recursive or force unless the user has approved the wider effect.
            """
            return await tag_service.delete(tag_id, recursive=recursive, force=force)

        @tool
        async def set_artifact_tags(
            artifact_id: str,
            paths: Annotated[list[str], Field(max_length=100)],
        ) -> ArtifactReceipt:
            """Replace the confirmed persistent tags assigned to one saved artifact.

            Args:
                artifact_id: Artifact UUID from the current conversation workspace.
                paths: Complete replacement set of hierarchical tag paths; an empty list clears it.

            Snippet:
                set_artifact_tags(artifact_id="...", paths=["Engineering/Python", "Concurrency"])

            Guidelines:
                - The artifact must belong to this conversation and already be saved.
                - This is the artifact library's tool; a file's collections are set with `set_asset_tags`.
                - This is a complete replacement, not an append operation.
                - Missing paths are created as real tags, including their parent nodes.
                - The answer is a bounded receipt whose `tags` is the complete set you just wrote.
            """
            if await artifact_storage.get_for_session(session_id, artifact_id) is None:
                raise ValueError(f"Artifact not found in this session: {artifact_id}")
            return artifact_receipt(await tag_service.replace_artifact_tags(artifact_id, paths))

        @tool
        async def create_asset_tag(
            path: str,
            description: str | None = None,
            color: str | None = None,
        ) -> TagEntity:
            """Create a collection in the static asset library, and any missing parent.

            Args:
                path: Slash-delimited hierarchy such as "Assets/Covers".
                description: Optional short explanation of the category.
                color: Optional CSS color used by the Library UI.

            Snippet:
                create_asset_tag(path="Assets/Covers", description="Book covers")

            Guidelines:
                - The static asset library keeps its own tree: a path created here is a different collection from the artifact library's same path, and `create_tag` is the artifact-side tool.
                - Create a real collection only when the user asks for it or approves a durable classification.
                - Reuse an existing path when it already expresses the same category.
            """
            return await tag_service.create_path(
                path,
                TagTargetType.ASSET,
                description=description,
                color=color,
            )

        @tool
        async def list_asset_tags() -> list[TagTreeEntity]:
            """List the static asset library's collection tree and file counts.

            Snippet:
                list_asset_tags()

            Guidelines:
                - Inspect existing collections before creating a near-duplicate category.
                - Counts describe files only; the artifact library keeps its own tree.
            """
            return await tag_service.list_tree(TagTargetType.ASSET)

        @tool
        async def set_asset_tags(
            asset_id: str,
            paths: Annotated[list[str], Field(max_length=100)],
        ) -> StaticAssetReceipt:
            """Replace the collections one static asset belongs to.

            Args:
                asset_id: Static asset id, as `upload_static_asset` returns it.
                paths: Complete replacement set of collection paths; an empty list clears it.

            Snippet:
                set_asset_tags(asset_id="...", paths=["Assets/Covers"])

            Guidelines:
                - The file has to exist in the global Static Assets library; a session asset is not this library's file.
                - This is a complete replacement, not an append operation; read `list_asset_tags` first when adding one.
                - Missing paths are created as real collections, including their parent nodes.
                - The answer is a bounded receipt whose `tags` is the complete set you just wrote.
            """
            if await static_asset_service.get(asset_id) is None:
                raise ValueError(f"Static asset not found: {asset_id}")
            return static_asset_receipt(await tag_service.replace_asset_tags(asset_id, paths))

        for registered in (
            create_tag,
            list_tags,
            update_tag,
            delete_tag,
            set_artifact_tags,
            create_asset_tag,
            list_asset_tags,
            set_asset_tags,
        ):
            context.register_tool(registered)
