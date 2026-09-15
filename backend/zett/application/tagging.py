"""Application services for persistent library classification."""

from dataclasses import dataclass

from ..infra.dao import artifact_storage, key_value_storage, tag_storage
from ..models import ArtifactListOptions, TagListOptions
from ..schemas import AgentArtifact, ArtifactStatus, TagOut, TagTreeOut, TagWrite

LEGACY_TAG_BACKFILL_KEY = "library.tags.backfilled.v1"


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

    def create_path(
        self,
        path: str,
        *,
        description: str | None = None,
        color: str | None = None,
    ) -> TagOut:
        display, _, segments = normalize_tag_path(path)
        parent: TagOut | None = None
        for index in range(len(segments)):
            node_path = "/".join(segments[: index + 1])
            normalized = node_path.casefold()
            current = tag_storage.get_by_normalized_path(normalized)
            if current is None:
                is_leaf = index == len(segments) - 1
                current = tag_storage.create(
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
            parent = tag_storage.update(
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

    def update(
        self,
        tag_id: str,
        *,
        path: str | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> TagOut:
        current = self.require(tag_id)
        target_path, target_normalized, segments = normalize_tag_path(path or current.path)
        if target_normalized != current.normalized_path and tag_storage.child_count(tag_id):
            raise ValueError("A tag with children cannot be moved or renamed")
        parent = self.create_path("/".join(segments[:-1])) if len(segments) > 1 else None
        return tag_storage.update(
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

    def delete(self, tag_id: str, *, recursive: bool = False, force: bool = False) -> bool:
        current = self.require(tag_id)
        descendants = [
            tag
            for tag in tag_storage.list(TagListOptions(prefix=current.normalized_path, limit=2_000))
            if tag.id != current.id
        ]
        if descendants and not recursive:
            raise ValueError("Tag has children; set recursive=true to delete the subtree")
        targets = [*descendants, current]
        if not force and any(tag_storage.assignment_count(tag.id) for tag in targets):
            raise ValueError("Tag is assigned to artifacts; set force=true to remove those assignments")
        for tag in sorted(targets, key=lambda item: item.normalized_path.count("/"), reverse=True):
            tag_storage.delete(tag.id)
        return True

    def list_tree(self) -> list[TagTreeOut]:
        tags = list(tag_storage.list(TagListOptions(limit=2_000)))
        assignments = tag_storage.assignments()
        children: dict[str | None, list[TagOut]] = {}
        for tag in tags:
            children.setdefault(tag.parent_id, []).append(tag)

        def build(tag: TagOut) -> tuple[TagTreeOut, set[str]]:
            built_children = [build(child) for child in children.get(tag.id, [])]
            child_nodes = [child for child, _ in built_children]
            direct_artifacts = assignments.get(tag.id, set())
            subtree_artifacts = set(direct_artifacts)
            for _, child_artifacts in built_children:
                subtree_artifacts.update(child_artifacts)
            return TagTreeOut(
                **tag.model_dump(),
                direct_count=len(direct_artifacts),
                total_count=len(subtree_artifacts),
                children=child_nodes,
            ), subtree_artifacts

        return [node for node, _ in (build(root) for root in children.get(None, []))]

    def subtree_ids(self, tag_ids: list[str]) -> tuple[str, ...]:
        """Expand selected taxonomy nodes to include every descendant."""
        expanded: dict[str, None] = {}
        for tag_id in tag_ids:
            tag = self.require(tag_id)
            for candidate in tag_storage.list(TagListOptions(prefix=tag.normalized_path, limit=2_000)):
                expanded[candidate.id] = None
        return tuple(expanded)

    def replace_artifact_tags(self, artifact_id: str, paths: list[str]) -> AgentArtifact:
        artifact = artifact_storage.get(artifact_id)
        if artifact is None:
            raise KeyError(f"Artifact not found: {artifact_id}")
        if artifact.status != ArtifactStatus.SAVED:
            raise ValueError("Only saved artifacts can receive persistent tags")
        tags = [self.create_path(path) for path in dict.fromkeys(paths)]
        tag_storage.replace_artifact_tags(artifact_id, tuple(tag.id for tag in tags))
        refreshed = artifact_storage.get(artifact_id)
        if refreshed is None:  # pragma: no cover - guarded above
            raise KeyError(f"Artifact not found: {artifact_id}")
        return refreshed

    def sync_confirmed_suggestions(self, artifact: AgentArtifact) -> AgentArtifact:
        """Promote the suggestions retained by the UI into persistent assignments."""
        if artifact.status != ArtifactStatus.SAVED or not hasattr(artifact.content, "suggested_tags"):
            return artifact
        paths = [tag.path for tag in artifact.content.suggested_tags]
        return self.replace_artifact_tags(artifact.id, paths)

    def backfill_legacy_artifacts(self) -> None:
        """Materialize tags embedded by releases predating the assignment table."""
        if key_value_storage.get(LEGACY_TAG_BACKFILL_KEY) is not None:
            return
        offset = 0
        while True:
            artifacts = artifact_storage.list(
                ArtifactListOptions(statuses=(ArtifactStatus.SAVED,), limit=500, offset=offset)
            )
            for artifact in artifacts:
                if not artifact.tags and hasattr(artifact.content, "suggested_tags"):
                    paths = [tag.path for tag in artifact.content.suggested_tags]
                    if paths:
                        self.replace_artifact_tags(artifact.id, paths)
            if len(artifacts) < 500:
                key_value_storage.update(LEGACY_TAG_BACKFILL_KEY, True)
                return
            offset += len(artifacts)

    @staticmethod
    def require(tag_id: str) -> TagOut:
        tag = tag_storage.get(tag_id)
        if tag is None:
            raise KeyError(f"Tag not found: {tag_id}")
        return tag


tag_service = TagService()
