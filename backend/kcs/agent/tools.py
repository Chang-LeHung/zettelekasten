import builtins
from collections.abc import Callable

from kcs_agent import AgentTool
from pydantic import BaseModel, Field

from ..domain.services import ArtifactDomainService, ArtifactDraft
from ..infra.agent_session_dao import agent_session_storage
from ..infra.artifact_dao import artifact_storage
from ..infra.tool_adapter import typed_tool
from ..models import ArtifactListOptions
from ..schemas import (
    AgentArtifact,
    AgentArtifactWrite,
    ArticleArtifactContent,
    ArticleCreate,
    ArtifactContent,
    ArtifactStatus,
    ArtifactType,
    CardArtifactContent,
    CardCreate,
    ImageArtifactContent,
)


class CreateCardInput(BaseModel):
    """Arguments for creating one knowledge-card artifact."""

    content: CardArtifactContent = Field(description="Complete editable card content")


class CreateArticleInput(BaseModel):
    """Arguments for creating one long-form article artifact."""

    content: ArticleArtifactContent = Field(description="Complete editable article content")


class CreateImageInput(BaseModel):
    """Arguments for creating one image artifact or image-generation brief."""

    content: ImageArtifactContent = Field(description="Image prompt, description, and optional source")


class UpdateArtifactInput(BaseModel):
    """Arguments for replacing one artifact with type-safe content."""

    artifact_id: str = Field(description="Artifact ID returned by create or list operations")
    content: ArtifactContent = Field(description="Complete replacement content with the same artifact type")


class ArtifactIdInput(BaseModel):
    """Arguments identifying one artifact in the current conversation."""

    artifact_id: str = Field(description="Artifact ID returned by create or list operations")


class ArtifactTools:
    """Provide typed artifact operations scoped to one KCS Agent session."""

    def __init__(self, session_id: str, raw_content: str | None = None) -> None:
        self._session_id = session_id
        self._raw_content = raw_content
        if not agent_session_storage.exists(session_id):
            raise KeyError(f"Agent session not found: {session_id}")

    def create_card(self, content: CardArtifactContent) -> AgentArtifact:
        """Create a knowledge-card artifact for one distinct knowledge item."""
        return self._create(content)

    def create_article(self, content: ArticleArtifactContent) -> AgentArtifact:
        """Create a long-form Markdown article artifact."""
        return self._create(content)

    def create_image(self, content: ImageArtifactContent) -> AgentArtifact:
        """Create an image artifact from an asset, URL, or generation brief."""
        return self._create(content)

    def _create(self, content: ArtifactContent) -> AgentArtifact:
        self._validate(content)
        return artifact_storage.create(
            AgentArtifactWrite(session_id=self._session_id, content=content, raw_content=self._raw_content)
        )

    def get(self, artifact_id: str) -> AgentArtifact:
        """Read one typed artifact from the current conversation."""
        artifact = artifact_storage.get(artifact_id)
        if artifact is None or artifact.session_id != self._session_id:
            raise ValueError(f"Artifact not found: {artifact_id}")
        return artifact

    def update(self, artifact_id: str, content: ArtifactContent) -> AgentArtifact:
        """Replace an artifact while preserving its identity and type."""
        artifact = self.get(artifact_id)
        if artifact.artifact_type != content.artifact_type:
            raise ValueError("Artifact type cannot be changed during an update")
        self._validate(content)
        return artifact_storage.update(
            artifact_id,
            AgentArtifactWrite(
                session_id=self._session_id,
                content=content,
                raw_content=artifact.raw_content,
                status=artifact.status,
                linked_resource_id=artifact.linked_resource_id,
                metadata=artifact.metadata,
            ),
        )

    @staticmethod
    def _validate(content: ArtifactContent) -> None:
        body = content.prompt if isinstance(content, ImageArtifactContent) else content.content
        locator = None
        if isinstance(content, ImageArtifactContent):
            locator = content.asset_id or content.source_url
        ArtifactDomainService.validate(ArtifactDraft(content.artifact_type, content.title, body, locator))

    def delete(self, artifact_id: str) -> bool:
        """Delete one artifact and explicitly remove its linked library resource, if any."""
        from ..application.services import ArticleApplicationService, CardApplicationService

        artifact = self.get(artifact_id)
        if artifact.artifact_type == ArtifactType.CARD and artifact.linked_resource_id:
            CardApplicationService.delete(artifact.linked_resource_id)
        if artifact.artifact_type == ArtifactType.ARTICLE and artifact.linked_resource_id:
            ArticleApplicationService.delete(artifact.linked_resource_id)
        return artifact_storage.delete(artifact_id)

    def list(self) -> builtins.list[AgentArtifact]:
        """List every typed artifact in the current conversation."""
        return list(artifact_storage.list(ArtifactListOptions(session_id=self._session_id)))

    def save(self, artifact_id: str) -> AgentArtifact:
        """Finalize an artifact and publish supported resources to the permanent library."""
        artifact = self.get(artifact_id)
        if artifact.artifact_type == ArtifactType.CARD:
            return self._save_card(artifact)
        if artifact.artifact_type == ArtifactType.ARTICLE:
            return self._save_article(artifact)
        return self._save_non_library_artifact(artifact)

    def _save_article(self, artifact: AgentArtifact) -> AgentArtifact:
        """Publish or update a long-form artifact in the permanent article library."""
        from ..application.services import ArticleApplicationService

        if not isinstance(artifact.content, ArticleArtifactContent):
            raise ValueError("Article artifact content is invalid")
        content = artifact.content
        payload = ArticleCreate(
            title=content.title,
            subtitle=content.subtitle,
            summary=content.summary,
            content=content.content,
            raw_content=artifact.raw_content,
            tag_paths=[tag.path for tag in content.suggested_tags],
        )
        article = (
            ArticleApplicationService.update(artifact.linked_resource_id, payload)
            if artifact.linked_resource_id and ArticleApplicationService.get(artifact.linked_resource_id)
            else ArticleApplicationService.create(payload)
        )
        return artifact_storage.update(
            artifact.id,
            AgentArtifactWrite(
                session_id=self._session_id,
                content=content,
                raw_content=artifact.raw_content,
                status=ArtifactStatus.SAVED,
                linked_resource_id=article.id,
                metadata=artifact.metadata,
            ),
        )

    def _save_non_library_artifact(self, artifact: AgentArtifact) -> AgentArtifact:
        """Mark an artifact saved when its kind has no permanent library aggregate."""
        return artifact_storage.update(
            artifact.id,
            AgentArtifactWrite(
                session_id=self._session_id,
                content=artifact.content,
                raw_content=artifact.raw_content,
                status=ArtifactStatus.SAVED,
                linked_resource_id=artifact.linked_resource_id,
                metadata=artifact.metadata,
            ),
        )

    def _save_card(self, artifact: AgentArtifact) -> AgentArtifact:
        from ..application.services import CardApplicationService
        from ..infra.tag_dao import tag_storage
        from ..models import TagListOptions

        if not isinstance(artifact.content, CardArtifactContent):
            raise ValueError("Card artifact content is invalid")
        content = artifact.content
        selected_paths = {tag.path for tag in content.suggested_tags if tag.existing}
        tag_ids = [tag.id for tag in tag_storage.list(TagListOptions(tree=False)) if tag.path in selected_paths]
        payload = CardCreate(
            type=content.card_type,
            title=content.title,
            content=content.content,
            raw_content=artifact.raw_content,
            summary=content.summary,
            tag_ids=tag_ids,
        )
        card = (
            CardApplicationService.update(artifact.linked_resource_id, payload)
            if artifact.linked_resource_id and CardApplicationService.get(artifact.linked_resource_id)
            else CardApplicationService.create(payload)
        )
        return artifact_storage.update(
            artifact.id,
            AgentArtifactWrite(
                session_id=self._session_id,
                content=content,
                raw_content=artifact.raw_content,
                status=ArtifactStatus.SAVED,
                linked_resource_id=card.id,
                metadata=artifact.metadata,
            ),
        )

    def as_agent_tools(self) -> builtins.list[AgentTool]:
        """Expose schema-validated operations with explicit artifact lifecycle guidance."""
        specifications: builtins.list[tuple[str, str, Callable[..., object], type[BaseModel] | None]] = [
            ("create_card", self.create_card.__doc__ or "", self.create_card, CreateCardInput),
            ("create_article", self.create_article.__doc__ or "", self.create_article, CreateArticleInput),
            ("create_image", self.create_image.__doc__ or "", self.create_image, CreateImageInput),
            ("get_artifact", self.get.__doc__ or "", self.get, ArtifactIdInput),
            ("update_artifact", self.update.__doc__ or "", self.update, UpdateArtifactInput),
            ("delete_artifact", self.delete.__doc__ or "", self.delete, ArtifactIdInput),
            ("list_artifacts", self.list.__doc__ or "", self.list, None),
            ("save_artifact", self.save.__doc__ or "", self.save, ArtifactIdInput),
        ]
        return [
            typed_tool(
                name,
                operation,
                args_schema,
                "Save to the permanent library only when the user explicitly requests saving."
                if name == "save_artifact"
                else "Create or change artifacts only on user request; use returned stable IDs for subsequent operations.",
            )
            for name, description, operation, args_schema in specifications
        ]
