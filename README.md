> **Backend redesign in progress:** Zett currently retains Session, Asset,
> Artifact, and Provider storage. Cards and articles are artifact variants. The frontend
> is preserved, but former business APIs are removed. A minimal Agent/SSE facade
> is available for the new application design.
> See [the current backend scope](backend/README.md). Feature descriptions below
> describe the previous application, not the currently available backend.

<p align="center">
  <img src="frontend/public/logo.png" width="144" height="144" alt="Zett logo">
</p>

<h1 align="center">Zett</h1>

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

Zett combines a streamed AI conversation, durable session context, flexible artifacts, and a unified card-and-article library in one private local application.

## Highlights

- Chat with Zett Agent through a streamed conversation interface.
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
- Zett Agent with native provider SDK adapters
- Vue 3 and TypeScript
- Vite
- `uv` for Python dependency management
- Ruff for Python formatting and linting

## Installation

Install the frontend dependencies, build the Vue application, and install the Python package from the repository root:

```bash
make install
```

The packaged `zett` command serves both the API and the compiled frontend:

```bash
zett start
```

The default application address is:

```text
http://127.0.0.1:6280
```

Use a different port when necessary:

```bash
zett start --port 9000
```

Interactive API documentation is available at `/docs` while the service is running.

## Local Data

Zett keeps personal data under the current user's home directory by default:

```text
~/.zett/
├── cards.db
├── agent.db
├── assets/
│   └── <session-id>/
└── logs/
    ├── zett.log
    └── zett.log.1
```

The rotating logger keeps two files with a maximum size of 64 MiB each. Session binaries are isolated in canonical UUID directories and filesystem paths are never exposed through the API.

## Configuration

Runtime configuration uses the `ZETT_` environment variable prefix:

| Variable | Purpose |
| --- | --- |
| `ZETT_HOST` | HTTP bind address |
| `ZETT_PORT` | HTTP port |
| `ZETT_DATABASE_PATH` | Zett domain and observability SQLite database path |
| `ZETT_AGENT_DATABASE_PATH` | Zett Agent raw-message and snapshot SQLite database path |
| `ZETT_ASSET_DIR` | Session asset directory |
| `ZETT_MAX_ASSET_SIZE_BYTES` | Maximum binary asset size |
| `ZETT_LOG_DIR` | Rotating log directory |
| `ZETT_LOG_LEVEL` | Application log level |
| `ZETT_CORS_ORIGINS` | Allowed CORS origins |
| `ZETT_SECRET_KEY` | Local provider-secret encryption key |
| `ZETT_AGENT_CONTEXT_MAX_TOKENS` | Token threshold that triggers agent context compaction |
| `ZETT_AGENT_KEEP_RECENT_TOKENS` | Minimum recent token budget retained after compaction |

The frontend calls the same-origin `/api` path. During separate frontend development, point Vite at another backend without changing source code:

```bash
VITE_API_URL=http://127.0.0.1:9000/api npm run dev
```

## Development

Start the backend directly:

```bash
cd backend
uv sync
uv run zett start
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

Install the repository's commit checks once after cloning:

```bash
make pre-commit-install
```

Every commit then requires Ruff formatting and lint checks for both Python projects and the Vue TypeScript type check to pass.

## CLI Examples

```bash
zett tag add Technology
zett tag add Python --parent-id 1
zett add --type idea --tag-id 2 "Capture an idea"
zett search idea
zett tag tree
```

## Architecture

The backend follows domain-driven design:

```text
backend/zett/
├── domain/       # Framework-independent domain rules and service boundaries
├── application/  # Use-case orchestration and process services
├── infra/        # SQLAlchemy storage, SQLite, logging, and provider adapters
├── agent/        # Zett Agent, context compaction, and typed tools
├── main.py       # FastAPI interface
└── cli.py        # Typer interface
```

HTTP and CLI interfaces call application services rather than storage implementations directly. Persistence uses typed SQLAlchemy ORM expressions. Database references are stored as IDs without foreign keys, `ondelete`, or cascade behavior; storage implementations perform cleanup explicitly.

The Vue frontend keeps all backend calls in typed clients under `frontend/src/api`. Components do not hard-code backend URLs.

The standalone [`zett-agent`](backend/zett-agent) package powers Zett conversations, tool execution, and streaming. Its current local development version uses direct message fields and a small model/tool loop. Zett passes prepared history from its context snapshot and raw-log tail, excluding the current input. Tools are supplied directly to the agent, with optional guidelines appended to system instructions. Title generation and compaction use schema-bound tool responses validated by Pydantic. This simplified API is not yet published; development and `make install` use the local `zett-agent` package.

## Agent Sessions and Context

Each conversation can own zero or many typed artifacts. Artifacts have stable IDs, lifecycle states, versions, type-specific content, and optional links to permanent library resources. Saving a card or article publishes it to the unified library only when explicitly requested.

Zett Agent uses the standalone package's bounded model-and-tool loop. Its typed tools can create and update artifacts and operate inside the current session workspace. Filesystem tools include directory listing, file reading, writing, editing, globbing, searching, and restricted command execution. Commands run without a shell interpreter, use allowlists, reject traversal and shell operators, and enforce output and execution limits.

Conversation history is stored as immutable raw log messages plus versioned context snapshots. Context reconstruction loads the newest snapshot and replays only messages after its boundary. Once the configured token threshold is reached, the compaction middleware summarizes older messages while preserving a recent verbatim tail. Raw logs and previous snapshot versions remain available for auditing and rebuilding context.

## API Models

Pydantic request and response models in `backend/zett/schemas.py` contain typed constraints and English field descriptions. Run the service and open `/docs` to inspect the generated OpenAPI schema.

## License

This project is available under the [MIT License](LICENSE).
