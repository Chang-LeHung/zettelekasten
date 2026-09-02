from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .application.services import (
    AISettingsApplicationService,
    CardApplicationService,
    CardOrganizationApplicationService,
    TagApplicationService,
)
from .config import settings
from .database import init_db
from .schemas import AISettingsIn, AnalyzeRequest, CardCreate, TagCreate

app = FastAPI(title="Knowledge Cards API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/cards")
def cards(q: str | None = None, type: str | None = None, tag_id: int | None = None):
    return CardApplicationService.search(q, type, tag_id)


@app.post("/api/cards")
def create_card(payload: CardCreate):
    return CardApplicationService.create(payload)


@app.get("/api/cards/{card_id}")
def card(card_id: str):
    return CardApplicationService.get(card_id)


@app.put("/api/cards/{card_id}")
def update_card(card_id: str, payload: CardCreate):
    return CardApplicationService.update(card_id, payload)


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: str):
    return CardApplicationService.delete(card_id)


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


@app.post("/api/cards/analyze")
async def analyze_card(payload: AnalyzeRequest):
    return await CardOrganizationApplicationService.preview(payload)
