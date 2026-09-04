from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .application.services import (
    AIProviderApplicationService,
    AISettingsApplicationService,
    CardApplicationService,
    KnowledgeLibraryApplicationService,
    KnowledgeWorkspaceApplicationService,
    SessionAssetApplicationService,
    TagApplicationService,
)
from .config import settings
from .infra.database import init_db
from .infra.logging import configure_logging, get_logger, shutdown_logging
from .models import AgentSessionListOptions, AIProviderListOptions, CardListOptions, LibraryListOptions
from .schemas import (
    AgentSessionTitleUpdate,
    AIProviderIn,
    AISettingsIn,
    AnalyzeRequest,
    ArtifactContent,
    CardCreate,
    LibraryItemType,
    LibraryItemUpdate,
    SessionLinkAssetIn,
    SessionTextAssetIn,
    TagCreate,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log_path = configure_logging()
    init_db()
    logger.info("KCS service started; log_file=%s", log_path)
    try:
        yield
    finally:
        logger.info("KCS service stopped")
        shutdown_logging()


app = FastAPI(title="Knowledge Cards API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/cards")
def cards(options: Annotated[CardListOptions, Query()]):
    return CardApplicationService.search_options(options)


@app.post("/api/cards")
def create_card(payload: CardCreate):
    return CardApplicationService.create(payload)


@app.get("/api/cards/{card_id}")
def card(card_id: str):
    result = CardApplicationService.get(card_id)
    if result is None:
        raise HTTPException(404, "Card not found")
    return result


@app.put("/api/cards/{card_id}")
def update_card(card_id: str, payload: CardCreate):
    try:
        return CardApplicationService.update(card_id, payload)
    except KeyError as error:
        raise HTTPException(404, "Card not found") from error


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: str):
    return CardApplicationService.delete(card_id)


@app.get("/api/library", tags=["Library"], summary="List permanent knowledge resources")
def library(options: Annotated[LibraryListOptions, Query()]):
    """Return cards and articles in one reverse-chronological collection."""
    return KnowledgeLibraryApplicationService.list(options)


@app.delete("/api/library/{item_type}/{item_id}", tags=["Library"], summary="Delete a library resource")
def delete_library_item(item_type: LibraryItemType, item_id: str):
    """Delete one permanent card or article through its owning application service."""
    return KnowledgeLibraryApplicationService.delete(item_type, item_id)


@app.put("/api/library/{item_type}/{item_id}", tags=["Library"], summary="Update a library resource")
def update_library_item(item_type: LibraryItemType, item_id: str, payload: LibraryItemUpdate):
    """Update editable card or article fields without changing its resource kind."""
    try:
        return KnowledgeLibraryApplicationService.update(item_type, item_id, payload)
    except KeyError as error:
        raise HTTPException(404, "Library resource not found") from error


@app.get("/api/tags")
def tags():
    return TagApplicationService.tree()


@app.post("/api/tags")
def add_tag(payload: TagCreate):
    return TagApplicationService.create(payload)


@app.get("/api/settings/ai")
def ai_settings():
    return AISettingsApplicationService.get()


@app.put("/api/settings/ai")
def update_ai_settings(payload: AISettingsIn):
    return AISettingsApplicationService.update(payload)


@app.get("/api/ai/providers")
def ai_providers(options: Annotated[AIProviderListOptions, Query()]):
    return AIProviderApplicationService.list_providers(options)


@app.post("/api/ai/providers")
def create_ai_provider(payload: AIProviderIn):
    return AIProviderApplicationService.create_provider(payload)


@app.put("/api/ai/providers/{provider_id}")
def update_ai_provider(provider_id: int, payload: AIProviderIn):
    return AIProviderApplicationService.update_provider(provider_id, payload)


@app.delete("/api/ai/providers/{provider_id}")
def delete_ai_provider(provider_id: int):
    return AIProviderApplicationService.delete_provider(provider_id)


@app.post("/api/agent/start", tags=["Agent"], summary="Start an agent conversation")
def start_agent_conversation():
    """Create an empty persisted KCS Agent conversation and return its unique ID."""
    return KnowledgeWorkspaceApplicationService.start_conversation()


@app.get("/api/agent/sessions", tags=["Agent"], summary="List agent sessions")
def agent_sessions(options: Annotated[AgentSessionListOptions, Query()]):
    """List persisted sessions ordered by their most recent activity."""
    return KnowledgeWorkspaceApplicationService.list_sessions(options)


@app.get("/api/agent/sessions/{conversation_id}", tags=["Agent"], summary="Get an agent session")
def agent_session(conversation_id: str):
    """Return complete history, observability runs, tool spans, and card artifacts."""
    return KnowledgeWorkspaceApplicationService.get_session(conversation_id)


@app.patch("/api/agent/sessions/{conversation_id}/title", tags=["Agent"], summary="Update a session title")
def update_agent_session_title(conversation_id: str, payload: AgentSessionTitleUpdate):
    """Replace the conversation title with a user-authored value."""
    session = KnowledgeWorkspaceApplicationService.update_session_title(conversation_id, payload)
    if session is None:
        raise HTTPException(404, "Agent session not found")
    return session


@app.delete("/api/agent/sessions/{conversation_id}", tags=["Agent"], summary="Delete an agent session")
def delete_agent_session(conversation_id: str):
    """Delete a session and explicitly remove its messages, runs, tool calls, and artifacts."""
    return KnowledgeWorkspaceApplicationService.delete_session(conversation_id)


@app.get("/api/agent/{conversation_id}/artifacts", tags=["Agent"], summary="List conversation artifacts")
def agent_artifacts(conversation_id: str):
    """Return every transient or saved card artifact owned by the conversation."""
    return KnowledgeWorkspaceApplicationService.list_artifacts(conversation_id)


@app.get("/api/agent/{conversation_id}/artifacts/{artifact_id}", tags=["Agent"], summary="Get an artifact")
def agent_artifact(conversation_id: str, artifact_id: str):
    """Return one typed artifact from its persisted conversation."""
    return KnowledgeWorkspaceApplicationService.get_artifact(conversation_id, artifact_id)


@app.put("/api/agent/{conversation_id}/artifacts/{artifact_id}", tags=["Agent"], summary="Update an artifact")
def update_agent_artifact(conversation_id: str, artifact_id: str, payload: ArtifactContent):
    """Replace type-specific artifact content while preserving its stable identity."""
    return KnowledgeWorkspaceApplicationService.update_artifact(conversation_id, artifact_id, payload)


@app.delete("/api/agent/{conversation_id}/artifacts/{artifact_id}", tags=["Agent"], summary="Delete an artifact")
def delete_agent_artifact(conversation_id: str, artifact_id: str):
    """Delete an artifact and explicitly remove a linked library card when present."""
    return KnowledgeWorkspaceApplicationService.delete_artifact(conversation_id, artifact_id)


@app.post(
    "/api/agent/{conversation_id}/artifacts/{artifact_id}/save",
    tags=["Agent"],
    summary="Save an artifact",
)
def save_agent_artifact(conversation_id: str, artifact_id: str):
    """Finalize an artifact and publish cards to the permanent library."""
    return KnowledgeWorkspaceApplicationService.save_artifact(conversation_id, artifact_id)


@app.post("/api/agent/{conversation_id}/assets/text", tags=["Agent assets"], summary="Attach text")
def create_session_text_asset(conversation_id: str, payload: SessionTextAssetIn):
    """Store a UTF-8 text asset in the session aggregate."""
    return SessionAssetApplicationService.create_text(conversation_id, payload)


@app.post("/api/agent/{conversation_id}/assets/link", tags=["Agent assets"], summary="Attach a link")
def create_session_link_asset(conversation_id: str, payload: SessionLinkAssetIn):
    """Store a validated external HTTP or HTTPS link in the session aggregate."""
    return SessionAssetApplicationService.create_link(conversation_id, payload)


@app.post("/api/agent/{conversation_id}/assets/upload", tags=["Agent assets"], summary="Upload an asset")
async def upload_session_asset(conversation_id: str, request: Request, name: Annotated[str, Query(min_length=1)]):
    """Store a raw image or file body in the session-specific local asset directory."""
    content = await request.body()
    mime_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    return SessionAssetApplicationService.create_binary(conversation_id, name, mime_type, content)


@app.get("/api/agent/{conversation_id}/assets", tags=["Agent assets"], summary="List session assets")
def session_assets(conversation_id: str):
    """List every text, link, image, and file asset owned by a session."""
    return SessionAssetApplicationService.list_assets(conversation_id)


@app.get("/api/agent/{conversation_id}/assets/{asset_id}", tags=["Agent assets"], summary="Get an asset")
def session_asset(conversation_id: str, asset_id: str):
    """Return typed metadata for one session-owned asset."""
    asset = SessionAssetApplicationService.get_asset(conversation_id, asset_id)
    if asset is None:
        raise HTTPException(404, "Session asset not found")
    return asset


@app.get(
    "/api/agent/{conversation_id}/assets/{asset_id}/content",
    tags=["Agent assets"],
    summary="Read asset content",
)
def session_asset_content(conversation_id: str, asset_id: str):
    """Return inline text or a locally stored binary without exposing its filesystem path."""
    asset, path = SessionAssetApplicationService.get_content(conversation_id, asset_id)
    if asset is None:
        raise HTTPException(404, "Session asset not found")
    if asset.text_content is not None:
        return PlainTextResponse(asset.text_content, media_type=asset.mime_type or "text/plain")
    if path is None:
        raise HTTPException(409, "This asset does not contain locally stored content")
    return FileResponse(path, media_type=asset.mime_type, filename=asset.name)


@app.delete("/api/agent/{conversation_id}/assets/{asset_id}", tags=["Agent assets"], summary="Delete an asset")
def delete_session_asset(conversation_id: str, asset_id: str):
    """Delete one session-owned asset and its local binary file when present."""
    return SessionAssetApplicationService.delete_asset(conversation_id, asset_id)


@app.post("/api/agent/{conversation_id}/messages", tags=["Agent"], summary="Run a streaming agent turn")
def stream_agent_message(conversation_id: str, payload: AnalyzeRequest):
    """Stream the complete observable agent turn over SSE.

    The stream uses `status`, `message`, `tool`, `usage`, `metrics`, `artifacts`,
    `result`, and `error` event names. Conversation history, observability records,
    and artifacts are persisted to SQLite.
    """
    title_background = (
        BackgroundTask(
            KnowledgeWorkspaceApplicationService.summarize_session_title,
            conversation_id,
            payload.provider_id,
        )
        if KnowledgeWorkspaceApplicationService.should_generate_session_title(conversation_id)
        else None
    )
    return StreamingResponse(
        KnowledgeWorkspaceApplicationService.stream_conversation(conversation_id, payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=title_background,
    )


static_directory = Path(__file__).with_name("static")
if static_directory.joinpath("index.html").is_file():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
