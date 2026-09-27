"""The artifact tools answer with bounded views instead of the stored row."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from zett_agent.agent import Agent, AgentRunConfig
from zett_agent.messages import AssistantMessage, ToolCall, ToolMessage
from zett_agent.model import ModelEvent, ModelRequest, ModelResponse

from zett.agent.extensions import ArtifactExtension
from zett.application.artifacts.artifact_views import (
    ArtifactDocument,
    ArtifactReceipt,
    artifact_document,
    artifact_receipt,
)
from zett.infra.persistence.dao import artifact_storage, session_storage
from zett.schemas import (
    AgentArtifactEntity,
    AgentSessionCreate,
    ArtifactStatus,
    ArtifactTagEntity,
    CardArtifactContent,
    ImageArtifactContent,
    LatexPdfArtifactContent,
)

RECEIPT_FIELDS = {
    "id",
    "artifact_type",
    "status",
    "version",
    "title",
    "pending_draft",
    "tags",
    "content_url",
    "project_path",
    "pdf_name",
    "asset_path",
}


def _entity(
    content,
    *,
    draft_content=None,
    tags=(),
    content_url=None,
    raw_content=None,
) -> AgentArtifactEntity:
    """Build one stored artifact without touching storage, to test the projection."""
    now = datetime.now(UTC)
    return AgentArtifactEntity(
        id="01a0e316-a363-7b8c-b044-1faf2a16d048",
        session_id="01a0e315-89d9-773a-a61c-8d0e54493636",
        artifact_type=content.artifact_type,
        status=ArtifactStatus.SAVED,
        content=content,
        draft_content=draft_content,
        raw_content=raw_content,
        version=4,
        metadata={"source": "test-suite", "internal": "METADATA"},
        tags=list(tags),
        content_url=content_url,
        created_at=now,
        updated_at=now,
    )


def test_receipt_carries_identity_state_and_server_assigned_locations() -> None:
    """A write answers with what the next tool call needs, and nothing else.

    The model sent the body in the same turn, so echoing it back — with the
    source text, metadata, timestamps, and owning session — only spends context.
    """
    content = CardArtifactContent(title="Idea", content="Body")
    receipt = artifact_receipt(
        _entity(
            content,
            tags=[ArtifactTagEntity(id="tag-1", path="Engineering/Python", name="Python")],
            raw_content="RAW SOURCE MUST NOT ENTER CONTEXT",
        )
    )

    assert isinstance(receipt, ArtifactReceipt)
    assert set(receipt.model_dump()) == RECEIPT_FIELDS
    assert receipt.id == "01a0e316-a363-7b8c-b044-1faf2a16d048"
    assert receipt.title == "Idea"
    assert receipt.tags == ["Engineering/Python"]
    assert receipt.pending_draft is False
    assert receipt.project_path is None and receipt.pdf_name is None and receipt.asset_path is None
    assert "RAW SOURCE" not in receipt.model_dump_json()
    assert "METADATA" not in receipt.model_dump_json()
    assert "01a0e315-89d9-773a-a61c-8d0e54493636" not in receipt.model_dump_json()


def test_receipt_reports_the_draft_and_each_owned_location() -> None:
    """The draft flag and the type-specific locations survive the projection."""
    published = CardArtifactContent(title="Published", content="Kept")
    draft = CardArtifactContent(title="Proposed", content="Kept")
    assert artifact_receipt(_entity(published, draft_content=draft)).pending_draft is True
    assert artifact_receipt(_entity(published)).pending_draft is False

    latex = _entity(
        LatexPdfArtifactContent(project_path="artifacts/session/paper", pdf_name="paper.pdf"),
        content_url="/api/files/artifacts/session/paper/paper.pdf",
    )
    latex_receipt = artifact_receipt(latex)
    assert (latex_receipt.project_path, latex_receipt.pdf_name) == ("artifacts/session/paper", "paper.pdf")
    assert latex_receipt.title == "paper"

    image = _entity(
        ImageArtifactContent(title="Chart", asset_path="assets/sessions/session/chart.png"),
        content_url="/api/files/assets/sessions/session/chart.png",
    )
    image_receipt = artifact_receipt(image)
    assert image_receipt.asset_path == "assets/sessions/session/chart.png"
    assert image_receipt.content_url == "/api/files/assets/sessions/session/chart.png"


def test_document_returns_both_bodies_and_no_stored_noise() -> None:
    """The one read that needs the bodies returns them without the stored row."""
    content = CardArtifactContent(title="Published", content="What the user kept")
    draft = CardArtifactContent(title="Proposed", content="What the model edits")
    document = artifact_document(_entity(content, draft_content=draft, raw_content="RAW SOURCE"))

    assert isinstance(document, ArtifactDocument)
    assert document.content is not None and document.content.content == "What the user kept"
    assert document.draft_content is not None and document.draft_content.content == "What the model edits"
    assert document.pending_draft is True
    assert set(document.model_dump()) == {
        "id",
        "artifact_type",
        "status",
        "version",
        "content",
        "draft_content",
        "pending_draft",
        "tags",
        "content_url",
    }
    assert "RAW SOURCE" not in document.model_dump_json()


class LongArticleModel:
    """Create one long article and keep the tool result it received."""

    def __init__(self) -> None:
        self.step = 0
        self.answer = ""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        if self.step == 0:
            message = AssistantMessage(
                tool_calls=(
                    ToolCall(
                        "create-long",
                        "create_artifact",
                        {
                            "content": {
                                "artifact_type": "article",
                                "title": "Long article",
                                "content": "一段很长的正文。" * 5_000,
                            },
                            "raw_content": "原始素材。" * 5_000,
                        },
                    ),
                )
            )
        else:
            result = request.messages[-1]
            assert isinstance(result, ToolMessage)
            assert result.success
            self.answer = result.content
            message = AssistantMessage(content="Article created.")
        self.step += 1
        yield ModelEvent.completed(ModelResponse(message))


async def test_create_artifact_answers_a_long_article_with_a_small_receipt() -> None:
    """A 150 KB article must not come back as a 300 KB tool result.

    Regression: create and update answered with the stored entity, so every call
    carried the published body, the draft, and ``raw_content`` back into context.
    """
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    model = LongArticleModel()
    agent = await Agent.create(model, config=AgentRunConfig(session_id=session_id), extensions=[ArtifactExtension()])

    result = await agent.run("Write a long article")

    assert result.content == "Article created."
    payload = json.loads(model.answer)
    assert payload["artifact_type"] == "article"
    assert payload["title"] == "Long article"
    assert "content" not in payload
    assert len(model.answer) < 1_000
    assert len(await artifact_storage.list()) == 1
