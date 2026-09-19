# Zett backend

FastAPI service and Typer CLI for Zett. The backend owns two SQLite databases,
a few file directories, and serves the compiled Vue frontend from `zett/static`
when a build exists.

## Layers

| Path | Contents |
| --- | --- |
| `zett/agent/` | Composition root for conversations: extension stack, model factory, SSE dispatcher, session title agent |
| `zett/application/` | Routes, use-case services, and the framework-neutral `ObjectStore` contract |
| `zett/infra/` | SQLAlchemy models and DAOs, local ObjectStore adapter, agent runtime storage, logging |
| `zett/schemas.py`, `zett/models/` | Write and read models shared by routes and storage |
| `zett/main.py`, `zett/cli.py` | ASGI entry point and the packaged `zett` command |

Domain rules currently live in `schemas.py`, storage contracts in
`infra/storage.py`, and services in `application/`; there is no separate
`domain/` package.

## Storage boundaries

| Boundary | Owner | Tables and files |
| --- | --- | --- |
| Session | `zett-agent` | `agent_sessions`, `raw_messages`, `session_snapshots` |
| Asset | Zett | `session_assets` plus binary files stored by relative object key |
| Static asset | Zett | `static_assets` plus uploaded files stored by relative object key |
| Artifact | Zett | `session_artifacts`: card, article, image, slides, latex_pdf |
| Tag | Zett | `tags`, `artifact_tags` |
| Provider | Zett | `providers`, with credentials encrypted by the local provider key |
| Runtime settings | Zett | `key_values` under `settings.runtime` |

`infra/dao/session.py` delegates to the package session store and does not
create a second session table.

Records reference each other by ID only: there are no foreign keys,
`ondelete` rules, or cascades. Storage implementations clean relation rows and
owned files explicitly. Deleting a session therefore spans two SQLite
databases and the filesystem, so cleanup is idempotent and retryable rather
than one transaction.

Every persisted file location is a relative `ObjectKey` below
`settings.storage_root` (`~/.zettelekasten` by default). `ObjectStore` owns path
validation, writes, reads, deletion, and public-URL generation; DAOs never
construct filesystem paths directly. Importing a Static Asset into a session
stores the target object key in `source_path` and does not copy the binary.

## HTTP surface

Everything is mounted under `/api`.

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Liveness probe |
| `POST /api/agent/start`, `GET/DELETE /api/agent/sessions*` | Create, list, read, retitle, and delete conversations |
| `GET /api/agent/sessions/{id}/messages` | Page the immutable Raw Log for the conversation UI |
| `GET /api/agent/sessions/{id}/model`, `/context-composition` | Last provider choice and current context ratios |
| `POST /api/agent/{id}/messages` | Run one turn and stream zett-agent events as SSE |
| `POST /api/agent/{id}/events` | Deliver one UI answer, such as an `ask_user` choice, to the active request |
| `POST /api/agent/{id}/steer` | Insert an urgent user message into the active request |
| `/api/files/{key}` | The only binary content endpoint; streams one ObjectStore key |
| `/api/agent/{id}/assets*` | Session asset CRUD, upload, rename, and Static Asset object references |
| `/api/assets*` | Session-independent file listing, upload, metadata, and deletion |
| `/api/agent/{id}/artifacts*`, `GET /api/artifacts` | Artifact CRUD, save, per-session listing, and library-wide search |
| `/api/agent/{id}/artifacts/{artifact}` | Artifact metadata; `content_url` addresses its unified file key |
| `/api/ai/providers*` | Model endpoint configuration |
| `/api/settings` | Read or replace runtime limits |
| `/api/library/tags*` | Tag tree CRUD and artifact tag assignment |

`/messages`, `/events`, and `/steer` consult the same in-process
`ActiveRequestRegistry`: at most one request per session may run, and the
other two return 409 when no request is active.

## Streaming

`ZettelkastenEventDispatcher` encodes every `AgentEvent` as one SSE frame named
after the event type, with `session_id` and `phase` always present. Provider
replay blocks are intentionally not forwarded to the browser. Frames are
buffered in a deque and yielded only after the event has been consumed, which
preserves ordering and applies backpressure to the running turn.

Conversation context is restored from the newest snapshot plus the Raw Log
after its boundary; per-turn workspace and taxonomy injections were removed so
the leading system prefix stays stable.

## Local data

```
~/.zettelekasten/
├── zett.db         application records: artifacts, assets, tags, providers, settings
├── agent.db        sessions, immutable raw messages, context snapshots
├── assets/         `sessions/<session-id>/` binaries and `static/` uploads
├── artifacts/      one directory per session and LaTeX artifact project
├── provider.key    local key encrypting provider credentials
└── logs/           rotating log files
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `ZETT_HOST`, `ZETT_PORT` | Bind address and port, default `127.0.0.1:6280` |
| `ZETT_DATABASE_PATH` | Application database file |
| `ZETT_AGENT_DATABASE_PATH` | zett-agent session database file |
| `ZETT_STORAGE_ROOT` | Root for every persisted object key, default `~/.zettelekasten` |
| `ZETT_PROVIDER_KEY_PATH` | Local provider secret encryption key |
| `ZETT_MAX_ASSET_SIZE_BYTES` | Maximum binary asset and pasted-image size |
| `ZETT_LOG_DIR`, `ZETT_LOG_LEVEL` | Log directory and level |

Conversation limits are user settings rather than environment variables:
`max_message_images`, `max_turn_iterations`, `compaction_max_tokens`, and
`compaction_keep_recent_tokens`, read and replaced through `/api/settings`.

## Development

```bash
uv sync --directory backend
uv run --directory backend zett start --reload
```

`make check` runs Ruff, the backend test suite, the zett-agent and zettcode
checks, the Sphinx documentation check, frontend tests, TypeScript
typechecking, and the production frontend build.

Tests create temporary SQLite databases and asset directories and remove them
afterwards; they never touch the data under `~/.zettelekasten`.

## Frontend

Routes mount the compiled Vue application from `zett/static` at `/`. The UI
reaches the backend only through typed clients in `frontend/src/api`, so a new
or changed route belongs in the same change as its client.
