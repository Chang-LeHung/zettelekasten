"""Application services for persistent library classification."""

from dataclasses import dataclass

from ...infra.persistence.dao import artifact_storage, tag_storage
from ...schemas import AgentArtifactEntity, ArtifactStatus, TagEntity, TagListOptions, TagTreeEntity, TagWrite


def normalize_tag_path(path: str) -> tuple[str, str, tuple[str, ...]]:
    """Validate a slash-delimited path and return display/canonical forms."""
    segments = tuple(segment.strip() for segment in path.split("/"))
    if not segments or any(not segment for segment in segments):
        raise ValueError("Tag paths cannot contain empty segments")
    if any(len(segment) > 100 for segment in segments):
        raise ValueError("Each tag path segment must be at most 100 characters")
    display = "/".join(segments)
    if len(display) > 500:
        raise ValueError("Tag path must be at most 500 characters")
    return display, display.casefold(), segments


@dataclass(slots=True)
class TagService:
    """Coordinate taxonomy changes and artifact assignments."""

    async def create_path(
        self,
        path: str,
        *,
        description: str | None = None,
        color: str | None = None,
    ) -> TagEntity:
        display, _, segments = normalize_tag_path(path)
        parent: TagEntity | None = None
        for index in range(len(segments)):
            node_path = "/".join(segments[: index + 1])
            normalized = node_path.casefold()
            current = await tag_storage.get_by_normalized_path(normalized)
            if current is None:
                is_leaf = index == len(segments) - 1
                current = await tag_storage.create(
                    TagWrite(
                        path=node_path,
                        normalized_path=normalized,
                        name=segments[index],
                        parent_id=parent.id if parent else None,
                        description=description if is_leaf else None,
                        color=color if is_leaf else None,
                    )
                )
            parent = current
        if parent is None:  # pragma: no cover - normalize_tag_path rejects this state
            raise ValueError(f"Invalid tag path: {display}")
        if (description is not None and parent.description != description) or (
            color is not None and parent.color != color
        ):
            parent = await tag_storage.update(
                parent.id,
                TagWrite(
                    path=parent.path,
                    normalized_path=parent.normalized_path,
                    name=parent.name,
                    parent_id=parent.parent_id,
                    description=description if description is not None else parent.description,
                    color=color if color is not None else parent.color,
                ),
            )
        return parent

    async def update(
        self,
        tag_id: str,
        *,
        path: str | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> TagEntity:
        current = await self.require(tag_id)
        target_path, target_normalized, segments = normalize_tag_path(path or current.path)
        if target_normalized != current.normalized_path and await tag_storage.child_count(tag_id):
            raise ValueError("A tag with children cannot be moved or renamed")
        parent = await self.create_path("/".join(segments[:-1])) if len(segments) > 1 else None
        return await tag_storage.update(
            tag_id,
            TagWrite(
                path=target_path,
                normalized_path=target_normalized,
                name=segments[-1],
                parent_id=parent.id if parent else None,
                description=description if description is not None else current.description,
                color=color if color is not None else current.color,
            ),
        )

    async def delete(self, tag_id: str, *, recursive: bool = False, force: bool = False) -> bool:
        current = await self.require(tag_id)
        subtree = await tag_storage.list(TagListOptions(prefix=current.normalized_path, limit=2_000))
        descendants = [tag for tag in subtree if tag.id != current.id]
        if descendants and not recursive:
            raise ValueError("Tag has children; set recursive=true to delete the subtree")
        targets = [*descendants, current]
        if not force:
            counts = [await tag_storage.assignment_count(tag.id) for tag in targets]
            if any(counts):
                raise ValueError("Tag is assigned to artifacts; set force=true to remove those assignments")
        for tag in sorted(targets, key=lambda item: item.normalized_path.count("/"), reverse=True):
            await tag_storage.delete(tag.id)
        return True

    async def list_tree(self) -> list[TagTreeEntity]:
        tags = list(await tag_storage.list(TagListOptions(limit=2_000)))
        assignments = await tag_storage.assignments()
        children: dict[str | None, list[TagEntity]] = {}
        for tag in tags:
            children.setdefault(tag.parent_id, []).append(tag)

        def build(tag: TagEntity) -> tuple[TagTreeEntity, set[str]]:
            built_children = [build(child) for child in children.get(tag.id, [])]
            child_nodes = [child for child, _ in built_children]
            direct_artifacts = assignments.get(tag.id, set())
            subtree_artifacts = set(direct_artifacts)
            for _, child_artifacts in built_children:
                subtree_artifacts.update(child_artifacts)
            return TagTreeEntity(
                **tag.model_dump(),
                direct_count=len(direct_artifacts),
                total_count=len(subtree_artifacts),
                children=child_nodes,
            ), subtree_artifacts

        return [node for node, _ in (build(root) for root in children.get(None, []))]

    async def subtree_ids(self, tag_ids: list[str]) -> tuple[str, ...]:
        """Expand selected taxonomy nodes to include every descendant."""
        expanded: dict[str, None] = {}
        for tag_id in tag_ids:
            tag = await self.require(tag_id)
            candidates = await tag_storage.list(TagListOptions(prefix=tag.normalized_path, limit=2_000))
            for candidate in candidates:
                expanded[candidate.id] = None
        return tuple(expanded)

    async def replace_artifact_tags(self, artifact_id: str, paths: list[str]) -> AgentArtifactEntity:
        artifact = await artifact_storage.get(artifact_id)
        if artifact is None:
            raise KeyError(f"Artifact not found: {artifact_id}")
        if artifact.status != ArtifactStatus.SAVED:
            raise ValueError("Only saved artifacts can receive persistent tags")
        tags = [await self.create_path(path) for path in dict.fromkeys(paths)]
        await tag_storage.replace_artifact_tags(artifact_id, tuple(tag.id for tag in tags))
        refreshed = await artifact_storage.get(artifact_id)
        if refreshed is None:  # pragma: no cover - guarded above
            raise KeyError(f"Artifact not found: {artifact_id}")
        return refreshed

    async def sync_confirmed_suggestions(self, artifact: AgentArtifactEntity) -> AgentArtifactEntity:
        """Promote the suggestions retained by the UI into persistent assignments."""
        content = artifact.editable_content
        if artifact.status != ArtifactStatus.SAVED or not hasattr(content, "suggested_tags"):
            return artifact
        paths = [tag.path for tag in content.suggested_tags]
        return await self.replace_artifact_tags(artifact.id, paths)

    @staticmethod
    async def require(tag_id: str) -> TagEntity:
        tag = await tag_storage.get(tag_id)
        if tag is None:
            raise KeyError(f"Tag not found: {tag_id}")
        return tag


tag_service = TagService()
