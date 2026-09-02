import json
from datetime import UTC, datetime

from cryptography.fernet import Fernet
from fastapi import HTTPException
from langchain_core.prompts import ChatPromptTemplate

from .database import db
from .schemas import AISettingsIn, AnalyzeRequest, CardAnalysis


def _fernet():
    # Override the development key with CARDS_SECRET_KEY in production.
    import base64
    import hashlib
    import os

    secret = os.getenv("CARDS_SECRET_KEY", "knowledge-cards-local-secret")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def get_settings():
    with db() as conn:
        row = conn.execute("SELECT * FROM ai_settings WHERE id=1").fetchone()
        if not row:
            return None
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["api_key_masked"] = "configured" if d["encrypted_api_key"] else "not configured"
        d.pop("encrypted_api_key", None)
        return d


def save_settings(payload: AISettingsIn):
    with db() as conn:
        old = conn.execute("SELECT encrypted_api_key FROM ai_settings WHERE id=1").fetchone()
        encrypted = old[0] if old else None
        if payload.api_key is not None and payload.api_key.strip():
            encrypted = _fernet().encrypt(payload.api_key.encode()).decode()
        conn.execute(
            "INSERT INTO ai_settings(id,provider,model,base_url,encrypted_api_key,temperature,enabled,updated_at) VALUES(1,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET provider=excluded.provider,model=excluded.model,base_url=excluded.base_url,encrypted_api_key=excluded.encrypted_api_key,temperature=excluded.temperature,enabled=excluded.enabled,updated_at=excluded.updated_at",
            (
                payload.provider,
                payload.model,
                payload.base_url,
                encrypted,
                payload.temperature,
                int(payload.enabled),
                datetime.now(UTC).isoformat(),
            ),
        )
    return get_settings()


def _model():
    with db() as conn:
        row = conn.execute("SELECT * FROM ai_settings WHERE id=1").fetchone()
    if not row or not row["enabled"]:
        raise HTTPException(400, "Enable and configure an AI provider first")
    key = _fernet().decrypt(row["encrypted_api_key"].encode()).decode() if row["encrypted_api_key"] else None
    provider = row["provider"].lower()
    if provider in ("openai", "openai-compatible", "deepseek"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=row["model"], api_key=key, base_url=row["base_url"] or None, temperature=row["temperature"]
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=row["model"], api_key=key, temperature=row["temperature"])
    if provider in ("gemini", "google"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=row["model"], google_api_key=key, temperature=row["temperature"])
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=row["model"], base_url=row["base_url"] or "http://localhost:11434", temperature=row["temperature"]
        )
    raise HTTPException(400, f"Unsupported provider: {row['provider']}")


async def analyze(request: AnalyzeRequest):
    with db() as conn:
        tag_paths = []
        for r in conn.execute("SELECT id,name,parent_id FROM tags ORDER BY name"):
            names = [r[1]]
            parent = r[2]
            while parent:
                p = conn.execute("SELECT name,parent_id FROM tags WHERE id=?", (parent,)).fetchone()
                names.append(p[0])
                parent = p[1]
            tag_paths.append("/".join(reversed(names)))
        config = conn.execute("SELECT provider,model FROM ai_settings WHERE id=1").fetchone()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You organize personal knowledge cards. Return valid JSON only, without markdown. Required fields: type,title,summary,content,suggested_tags,keywords. suggested_tags is an array of objects with path,existing,confidence,reason. Prefer existing tags and never create tags without user confirmation. Existing tag tree: {tags}",
            ),
            ("human", "Organize this raw text:\n{raw}"),
        ]
    )
    try:
        result = await (prompt | _model()).ainvoke(
            {"tags": "\n".join(tag_paths) or "(no tags)", "raw": request.raw_content}
        )
        parsed = CardAnalysis.model_validate(
            json.loads(result.content if isinstance(result.content, str) else str(result.content))
        )
        with db() as conn:
            conn.execute(
                "INSERT INTO ai_analysis_runs(provider,model,input_text,output_json,status,created_at) VALUES(?,?,?,?,?,?)",
                (
                    config[0],
                    config[1],
                    request.raw_content,
                    parsed.model_dump_json(),
                    "success",
                    datetime.now(UTC).isoformat(),
                ),
            )
        return parsed
    except Exception as exc:
        raise HTTPException(502, f"AI analysis failed: {exc}") from exc
