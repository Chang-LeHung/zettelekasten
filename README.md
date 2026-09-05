<p align="center">
  <img src="frontend/public/logo.png" width="144" height="144" alt="Knowledge Cards System logo">
</p>

<h1 align="center">Knowledge Cards System</h1>

<p align="center">
  A local-first, AI-assisted workspace for turning conversations, rough notes, links, and assets into reusable knowledge.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-476957.svg"></a>
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB.svg?logo=python&logoColor=white">
  <img alt="Vue 3" src="https://img.shields.io/badge/Vue-3-42B883.svg?logo=vuedotjs&logoColor=white">
  <img alt="Local-first" src="https://img.shields.io/badge/storage-local--first-6B7F72.svg">
</p>

---

Knowledge Cards System (KCS) combines a streamed AI conversation, durable session context, flexible artifacts, and a unified card-and-article library in one private local application.

## Highlights

- Chat with KCS Agent through a streamed conversation interface.
- Stream assistant text, reasoning, tool calls, arguments, and results in timeline order.
- Create multiple card, article, and image artifacts in one conversation.
- Publish cards and articles into a unified searchable library.
- Edit Markdown in a full-screen split editor with linked scrolling and live preview.
- Render syntax-highlighted code, copyable code blocks, and mathematical formulas.
- Organize knowledge with recursively nested tags.
- Attach text, links, images, and files to isolated session workspaces.
- Persist sessions, immutable message logs, context snapshots, artifacts, usage metrics, and assets locally.
- Configure multiple AI providers and select a model and reasoning effort per conversation.

## Technology

- Python 3.14
- FastAPI and Typer
- SQLAlchemy and SQLite
- KCS Agent with native provider SDK adapters
- Vue 3 and TypeScript
- Vite
- `uv` for Python dependency management
- Ruff for Python formatting and linting

## Installation

Install the frontend dependencies, build the Vue application, and install the Python package from the repository root:

```bash
make install
```

The packaged `kcs` command serves both the API and the compiled frontend:

```bash
kcs start
```

The default application address is:

```text
http://127.0.0.1:6280
```

Use a different port when necessary:

```bash
kcs start --port 9000
```

Interactive API documentation is available at `/docs` while the service is running.

## Local Data

KCS keeps personal data under the current user's home directory by default:

```text
~/.knowledge_cards/
├── cards.db
├── agent.db
├── assets/
│   └── <session-id>/
└── logs/
    ├── kcs.log
    └── kcs.log.1
```

The rotating logger keeps two files with a maximum size of 64 MiB each. Session binaries are isolated in canonical UUID directories and filesystem paths are never exposed through the API.

## Configuration

Runtime configuration uses the `KCS_` environment variable prefix:

| Variable | Purpose |
| --- | --- |
| `KCS_HOST` | HTTP bind address |
| `KCS_PORT` | HTTP port |
| `KCS_DATABASE_PATH` | KCS domain and observability SQLite database path |
| `KCS_AGENT_DATABASE_PATH` | KCS Agent raw-message and snapshot SQLite database path |
| `KCS_ASSET_DIR` | Session asset directory |
| `KCS_MAX_ASSET_SIZE_BYTES` | Maximum binary asset size |
| `KCS_LOG_DIR` | Rotating log directory |
| `KCS_LOG_LEVEL` | Application log level |
| `KCS_CORS_ORIGINS` | Allowed CORS origins |
| `KCS_SECRET_KEY` | Local provider-secret encryption key |
| `KCS_AGENT_CONTEXT_MAX_TOKENS` | Token threshold that triggers agent context compaction |
| `KCS_AGENT_KEEP_RECENT_TOKENS` | Minimum recent token budget retained after compaction |

The frontend calls the same-origin `/api` path. During separate frontend development, point Vite at another backend without changing source code:

```bash
VITE_API_URL=http://127.0.0.1:9000/api npm run dev
```

## Development

Start the backend directly:

```bash
cd backend
uv sync
uv run kcs start
```

Start the Vue development server:

```bash
cd frontend
npm install
npm run dev
```

Run the complete verification suite from the repository root:

```bash
make check
```

This runs Python formatting checks, linting, backend tests, frontend tests, TypeScript type checking, and the production frontend build.

## CLI Examples

```bash
kcs tag add Technology
kcs tag add Python --parent-id 1
kcs add --type idea --tag-id 2 "Capture an idea"
kcs search idea
kcs tag tree
```

## Architecture

The backend follows domain-driven design:

```text
backend/kcs/
├── domain/       # Framework-independent domain rules and service boundaries
├── application/  # Use-case orchestration and process services
├── infra/        # SQLAlchemy storage, SQLite, logging, and provider adapters
├── agent/        # KCS Agent, context compaction, and typed tools
├── main.py       # FastAPI interface
└── cli.py        # Typer interface
```

HTTP and CLI interfaces call application services rather than storage implementations directly. Persistence uses typed SQLAlchemy ORM expressions. Database references are stored as IDs without foreign keys, `ondelete`, or cascade behavior; storage implementations perform cleanup explicitly.

The Vue frontend keeps all backend calls in typed clients under `frontend/src/api`. Components do not hard-code backend URLs.

The standalone [`kcs-agent`](backend/kcs-agent) package powers KCS conversations, tool execution, and streaming. Its current local development version uses direct message fields and a small model/tool loop. KCS passes prepared history from its context snapshot and raw-log tail, excluding the current input. Tools are supplied directly to the agent, with optional guidelines appended to system instructions. Title generation and compaction use schema-bound tool responses validated by Pydantic. This simplified API is not yet published; development and `make install` use the local `kcs-agent` package.

## Agent Sessions and Context

Each conversation can own zero or many typed artifacts. Artifacts have stable IDs, lifecycle states, versions, type-specific content, and optional links to permanent library resources. Saving a card or article publishes it to the unified library only when explicitly requested.

KCS Agent uses the standalone package's bounded model-and-tool loop. Its typed tools can create and update artifacts and operate inside the current session workspace. Filesystem tools include directory listing, file reading, writing, editing, globbing, searching, and restricted command execution. Commands run without a shell interpreter, use allowlists, reject traversal and shell operators, and enforce output and execution limits.

Conversation history is stored as immutable raw log messages plus versioned context snapshots. Context reconstruction loads the newest snapshot and replays only messages after its boundary. Once the configured token threshold is reached, the compaction middleware summarizes older messages while preserving a recent verbatim tail. Raw logs and previous snapshot versions remain available for auditing and rebuilding context.

## API Models

Pydantic request and response models in `backend/kcs/schemas.py` contain typed constraints and English field descriptions. Run the service and open `/docs` to inspect the generated OpenAPI schema.

## License

This project is available under the [MIT License](LICENSE).
