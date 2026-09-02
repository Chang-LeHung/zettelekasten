from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .application.services import (
    AISettingsApplicationService,
    CardApplicationService,
    CardOrganizationApplicationService,
    TagApplicationService,
)
from .config import settings
from .infra.database import init_db
from .infra.list_options import CardListOptions, CardSortField, SortDirection
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
def cards(
    q: str | None = None,
    type: str | None = None,
    tag_id: int | None = None,
    card_types: list[str] = Query(default=[]),
    statuses: list[str] = Query(default=[]),
    include_tag_ids: list[int] = Query(default=[]),
    exclude_tag_ids: list[int] = Query(default=[]),
    match_all_tags: bool = False,
    include_descendants: bool = True,
    source: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    has_summary: bool | None = None,
    sort_by: CardSortField = CardSortField.UPDATED_AT,
    sort_direction: SortDirection = SortDirection.DESC,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if type and type not in card_types:
        card_types.append(type)
    if tag_id and tag_id not in include_tag_ids:
        include_tag_ids.append(tag_id)
    return CardApplicationService.search_options(
        CardListOptions(
            query=q,
            card_types=tuple(card_types),
            statuses=tuple(statuses),
            include_tag_ids=tuple(include_tag_ids),
            exclude_tag_ids=tuple(exclude_tag_ids),
            match_all_tags=match_all_tags,
            include_descendants=include_descendants,
            source=source,
            created_from=created_from,
            created_to=created_to,
            updated_from=updated_from,
            updated_to=updated_to,
            has_summary=has_summary,
            sort_by=sort_by,
            sort_direction=sort_direction,
            limit=limit,
            offset=offset,
        )
    )


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
