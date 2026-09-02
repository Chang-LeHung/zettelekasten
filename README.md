# Knowledge Cards

本地个人知识卡片系统：Python 3.14/FastAPI + SQLite/FTS5 + Typer + Vue 3。

默认数据库位置为用户家目录下的 `~/.knowledge_cards/cards.db`，可通过 `CARDS_DATABASE_PATH` 覆盖。
前端使用 Vue 3，入口为 `frontend/src/main.js`。

## Schema 字段说明

后端的 `backend/app/schemas.py` 为所有 API 输入和输出字段提供了 Pydantic 类型、约束和英文描述；启动服务后可以在 `/docs` 查看 OpenAPI 文档。

## 启动后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

The backend follows a domain-driven structure. Domain rules live under `app/domain`, application process services live under `app/application`, and HTTP/CLI adapters call application services.

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

CLI 示例：

```bash
uv run cards tag add Technology
uv run cards tag add Python --parent-id 1
uv run cards add --type idea --tag-id 2 "Capture an idea"
uv run cards search idea
cards tag tree
```

AI 设置通过 `PUT /api/settings/ai` 配置，支持 `openai`、`openai-compatible`、`anthropic`、`gemini` 和 `ollama`。
