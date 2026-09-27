"""Application services for persistent library classification."""

from __future__ import annotations

from dataclasses import dataclass

from ...infra.persistence.dao import artifact_storage, tag_storage
from ...schemas import (
    AgentArtifactEntity,
    ArtifactContent,
    ArtifactStatus,
    SuggestedTag,
    TagEntity,
    TagListOptions,
    TagTreeEntity,
    TagWrite,
)


def _suggested_tags(content: ArtifactContent | None) -> tuple[SuggestedTag, ...]:
    """Return the tag proposals one content carries, or none when it carries no list."""
    return tuple(getattr(content, "suggested_tags", ()) or ())


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
        if path is None and description is None and color is None:
            raise ValueError("At least one tag field must be supplied")
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
        await self._tagged_artifact(artifact_id)
        tags = [await self.create_path(path) for path in dict.fromkeys(paths)]
        await tag_storage.replace_artifact_tags(artifact_id, tuple(tag.id for tag in tags))
        refreshed = await artifact_storage.get(artifact_id)
        if refreshed is None:  # pragma: no cover - guarded above
            raise KeyError(f"Artifact not found: {artifact_id}")
        return refreshed

    async def assign_tag(self, artifact_id: str, tag_id: str) -> AgentArtifactEntity:
        """Attach one tag to one artifact without disturbing its other tags.

        The shell names a tag by path but the taxonomy keys it by id, so this is
        the one-assignment form of ``replace_artifact_tags``: it reads the
        current set, adds the tag when it is missing, and writes the union back.
        """
        tag = await self.require(tag_id)
        current = await self._tagged_artifact(artifact_id)
        paths = [assignment.path for assignment in current.tags]
        if tag.path in paths:
            return current
        return await self.replace_artifact_tags(artifact_id, [*paths, tag.path])

    async def unassign_tag(self, artifact_id: str, tag_id: str) -> AgentArtifactEntity:
        """Detach one tag from one artifact, leaving every other assignment alone."""
        tag = await self.require(tag_id)
        current = await self._tagged_artifact(artifact_id)
        paths = [assignment.path for assignment in current.tags if assignment.path != tag.path]
        if len(paths) == len(current.tags):
            return current
        return await self.replace_artifact_tags(artifact_id, paths)

    @staticmethod
    async def _tagged_artifact(artifact_id: str) -> AgentArtifactEntity:
        """Return one artifact that may carry persistent tags."""
        artifact = await artifact_storage.get(artifact_id)
        if artifact is None:
            raise KeyError(f"Artifact not found: {artifact_id}")
        if artifact.status != ArtifactStatus.SAVED:
            raise ValueError("Only saved artifacts can receive persistent tags")
        return artifact

    async def sync_confirmed_suggestions(
        self,
        artifact: AgentArtifactEntity,
        *,
        superseded_content: ArtifactContent | None = None,
    ) -> AgentArtifactEntity:
        """Apply the suggestions the user confirmed without resetting the taxonomy.

        A suggestion is a proposal until a save confirms it, so the published
        content decides — never the model's draft. Saving is not a whole-set
        rewrite, though: a tag this save never proposed is left alone, because
        the Library's tag editor, `zett tag add`, and `set_artifact_tags` attach
        real assignments that an unrelated save must not delete. The one removal
        a save owns is a suggestion the user unchecked: the caller passes the
        content this save replaces as ``superseded_content``, and only paths that
        were proposed there drop out.
        """
        content = artifact.content
        if artifact.status != ArtifactStatus.SAVED or not hasattr(content, "suggested_tags"):
            return artifact
        stored = await artifact_storage.get(artifact.id)
        if stored is None:  # pragma: no cover - the artifact was just written
            return artifact
        superseded = {tag.path for tag in _suggested_tags(superseded_content)}
        keep = [tag.path for tag in stored.tags if tag.path not in superseded]
        confirmed = [tag.path for tag in content.suggested_tags]
        return await self.replace_artifact_tags(artifact.id, [*keep, *confirmed])

    @staticmethod
    async def require(tag_id: str) -> TagEntity:
        tag = await tag_storage.get(tag_id)
        if tag is None:
            raise KeyError(f"Tag not found: {tag_id}")
        return tag


tag_service = TagService()
