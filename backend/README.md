# Zett backend

FastAPI service and Typer CLI for Zett. The backend owns two SQLite databases,
a few file directories, and serves the compiled Vue frontend from `zett/static`
when a build exists.

## Layers

| Path | Contents |
| --- | --- |
| `zett/agent/` | Composition root for conversations: container, capability contracts, model factory, SSE dispatcher, session title agent |
| `zett/agent/extensions/` | Zett's adapters to the zett-agent `AgentExtension` point: the asset, artifact, tag, and context-composition tools |
| `zett/agent/plugins/` | Zett's own `ZettelkastenExt` plugins: the skill slash commands and the `@` reference kinds |
| `zett/application/` | Routes, use-case services, and the framework-neutral `ObjectStore` contract |
| `zett/infra/scheduler/` | Scheduler control loop, execution worker loop, action registry, and executor contracts |
| `zett/infra/tables/` | SQLAlchemy table mappings (`*Row`) that own the physical schema |
| `zett/infra/` | DAOs, local ObjectStore adapter, agent runtime storage, logging |
| `zett/schemas/` | Typed read, write, and `*ListOptions` query models shared by routes, tools, and storage |
| `zett/main.py`, `zett/cli.py` | ASGI entry point and the packaged `zett` command |

Domain rules currently live in `schemas.py`, storage contracts in
`infra/persistence/storage.py`, and services in `application/`; there is no separate
`domain/` package.

## Storage boundaries

| Boundary | Owner | Tables and files |
| --- | --- | --- |
| Session | `zett-agent` | `agent_sessions`, `raw_messages`, `session_snapshots` |
| Asset | Zett | `session_assets` plus binary files stored by relative object key |
| Message upload | Zett | `assets/sessions/<session-id>/uploads/` files written at submit time; no metadata row |
| Static asset | Zett | `static_assets` plus uploaded files stored by relative object key |
| Artifact | Zett | `session_artifacts`: card, article, image, slides, latex_pdf with published `content_json` and model `draft_content_json` |
| Tag | Zett | `tags`, `artifact_tags` |
| Provider | Zett | `providers`, with credentials encrypted by the local provider key |
| Runtime settings | Zett | `key_values` under `settings.runtime` |
| Scheduled task | Zett | `scheduled_tasks` and `scheduled_task_runs`; `zett scheduler` queues due runs and `zett worker` executes them |
| Process heartbeat | Zett | In-memory FastAPI registry populated through `/api/health/processes/heartbeat` |

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

Submitting a message with images writes those images to the session's own
directory as well, under `assets/sessions/<session-id>/uploads/`, named by
submission time. The user message keeps its inline data URL, so the browser
still renders from the message and the raw log stays a complete immutable
record; the files are the handle a model needs for `view_image`, a LaTeX build,
or a shell command. They are not Session Assets: nothing is listed by
`list_assets`, and deleting the session removes the whole session directory, so
uploads no row points at cannot leak.

Artifact creation writes the supplied content directly to `content_json`
because there is no existing user version to protect. Later model updates write
only `draft_content_json`, and the tool list has no save operation. The
conversation's editing surfaces (panel, inline editor, and full editor) stage
their edits through the draft endpoint. `update_artifact` takes a `patch`:
fields it omits keep their current value, an empty string or list clears a
field, `content_edits` replaces exact body snippets (`old_text`/`new_text`,
unique match required unless `replace_all` is set) so a long article never
travels back in full for one paragraph, and only a changed `artifact_type`
replaces the whole content. `update_artifact` accepts an artifact ID from
another session, preserves that artifact's owning session, and still writes
only its draft. `content_json` otherwise changes when the user publishes a
draft with the save endpoint or edits a library document from the Library view;
those writes mirror the published content into `draft_content_json`, so the
draft is always the working copy and matches `content_json` right after a save.
An empty `content_json` means the artifact has no initial or published content.
`AgentArtifactEntity.editable_content` is the draft-first view shared by the
conversation UI, previews, search, and the draft-versus-published diff, and
`ArtifactPruner` returns `published_content` and `draft_content` previews
together so a querying model can compare what the user kept with what it
proposes.

## HTTP surface

Everything is mounted under `/api`.

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Liveness probe |
| `GET /api/health/processes` | Scheduler and worker heartbeat health |
| `POST /api/agent/start`, `GET/DELETE /api/agent/sessions*` | Create, list, read, retitle, and delete conversations |
| `GET /api/agent/sessions/{id}/messages` | Page the immutable Raw Log for the conversation UI |
| `GET /api/agent/sessions/{id}/model`, `/context-composition` | Last provider choice and current context ratios |
| `POST /api/agent/{id}/messages` | Run one turn and stream zett-agent events as SSE |
| `GET /api/agent/{id}/slash-commands` | List commands registered by configured Zettelkasten extensions |
| `POST /api/agent/{id}/slash-commands/{command_id}` | Execute one slash command and stream its Agent events |
| `GET /api/agent/{id}/at-commands` | List the conversation resources the composer may reference with `@` |
| `POST /api/agent/{id}/at-commands/{item_id}` | Run one turn that references an `@` resource and stream its Agent events |
| `POST /api/agent/{id}/events` | Deliver one UI answer, such as an `ask_user` choice, to the active request |
| `POST /api/agent/{id}/steer` | Insert an urgent user message into the active request |
| `/api/scheduled-tasks*` | Manage Cron task definitions, enable or disable them, queue manual runs, and read execution history |
| `/api/files/{key}` | The only binary content endpoint; streams one ObjectStore key |
| `/api/agent/{id}/assets*` | Session asset CRUD, upload, rename, and Static Asset object references |
| `/api/assets*` | Session-independent file listing, upload, metadata, and deletion |
| `/api/agent/{id}/artifacts*`, `GET /api/artifacts` | Artifact CRUD, per-session listing, and library-wide search |
| `/api/agent/{id}/artifacts/{artifact_id}/draft` | Stage edited content as the draft without touching published content |
| `/api/agent/{id}/artifacts/{artifact_id}/save` | Publish the pending draft as the artifact's content (user action) |
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
yielded after the event has been consumed, which preserves ordering and applies
backpressure to the running turn.

Conversation context is restored from the newest snapshot plus the Raw Log
after its boundary; per-turn workspace and taxonomy injections were removed so
the leading system prefix stays stable.

`SessionFilesExtension` adds one stable system message naming the conversation's
own file directory, alongside the runtime's `# Filesystem environment` and
`# Tool snippets` instructions. It is byte-identical on every turn of a session
because it names a directory rather than listing state: which uploads exist is
left to the filesystem tools, so submitting another image never rewrites the
leading prefix.

The `ZettelkastenAgent` container loads application extensions from its
configuration. Each `ZettelkastenExt` can register slash commands with a name,
description, type, and handler. The container assigns a stable ID to every
command; the frontend lists those IDs and submits at most one command ID with an
input. The backend resolves that ID and runs the registered handler, which
receives the prepared turn, may replace its message, and streams the result. A
skill command names the skill for the current turn and lets the model load its
instructions with `read_skill`, and it records the original browser message as
`slash_command.raw_parts` so the conversation UI shows what the user sent
instead of the rewritten prompt.

The same extensions register `@` commands, one per referenceable resource kind.
An `@` command pairs a source that lists the current conversation's resources
with a handler that runs one referenced turn, and the container assigns stable
IDs plus unique token names to the listed items. `SessionReferenceExtension`
registers the built-in `asset` and `artifact` kinds, so the composer menu offers
the session's own material. A submitted reference injects only its kind and ID,
the model reads content with `get_asset` or `get_artifact`, and the original
browser message is recorded as `at_command.raw_parts`.

Every model call goes through `AgentTurn.prompt` in
`zett.application.agent.turns`. The HTTP message route, slash command handlers, and
`@` reference handlers each describe their turn as an `AgentTurn` (session,
request-owned client, model, run config, reasoning effort, metadata, and tags),
optionally replace its message, and prompt it; run options are assembled once
instead of at each call site. A turn is single use, so prompting it twice raises
`TurnAlreadyPromptedError` instead of starting a second request against the same
reserved session.

## Scheduled tasks

Scheduled tasks are persisted in `zett.db`. The Web process only creates,
updates, enables, disables, deletes, and manually queues tasks. The
`zett scheduler` process polls for due occurrences and writes `pending` run
rows. One or more independent `zett worker` processes claim those rows, change
them to `running`, execute a registered `ActionExecutor`, and write the terminal
result in `scheduled_task_runs`.

The scheduler never loads action executors and never runs model work. A slow or
crashed worker therefore cannot block new scheduling decisions. The task lease
keeps at most one run active per task, and expired leases are recovered as
`interrupted`.

The Web lifespan writes server PID, port, scheduler PIDs, and worker PIDs to
``runtime.json`` below `storage_root`. `zett stop` reads that file, stops the
recorded server and child processes, and removes the file. Stale or partial
runtime state is cleaned before a new server starts.

Scheduler and worker processes also run a watchdog against that file. They exit
after repeated failures when the file is missing or incomplete, when the owning
FastAPI PID is gone, or when their own PID is no longer registered. This prevents
orphaned workers from continuing after an unclean Web-process crash.

The FastAPI lifespan runs a lightweight process supervisor. Scheduler and
worker processes post heartbeats to `/api/health/processes/heartbeat`; FastAPI
keeps the latest values in an in-memory registry. The supervisor keeps local
`Popen` handles, starts missing CLI processes as independent subprocesses, and
uses `Popen.poll()` as the authoritative local liveness check. It does not
execute scheduler or worker loops inside FastAPI.

The first executor, `agent_prompt`, always creates a new isolated Agent session
and runs a headless turn. It disables interactive `ask_user` and coding tools so
a background job never waits for browser approval. Scheduled runs never target
a user's existing session.

All process types configure SQLite with WAL, a bounded busy timeout, and short
transactions. The Web process writes `logs/zett.log`, the scheduler writes
`logs/scheduler.log`, and workers write `logs/worker.log`.

## Local data

```
~/.zettelekasten/
├── zett.db         application records: artifacts, assets, tags, providers, settings
├── agent.db        sessions, immutable raw messages, context snapshots
├── assets/         `sessions/<session-id>/` binaries and `static/` uploads
├── artifacts/      one directory per session and LaTeX artifact project
├── provider.key    local key encrypting provider credentials
├── runtime.json    active server, scheduler, and worker process state
└── logs/           rotating log files
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `ZETT_HOST`, `ZETT_PORT` | Bind address and port, default `127.0.0.1:6280` |
| `ZETT_DATABASE_PATH` | Application database file |
| `ZETT_AGENT_DATABASE_PATH` | zett-agent session database file |
| `ZETT_STORAGE_ROOT` | Root for every persisted object key, default `~/.zettelekasten` |
| `ZETT_RUNTIME_STATE_PATH` | PID/port state file, default `<storage_root>/runtime.json` |
| `ZETT_PROVIDER_KEY_PATH` | Local provider secret encryption key |
| `ZETT_MAX_ASSET_SIZE_BYTES` | Maximum binary asset and pasted-image size |
| `ZETT_LOG_DIR`, `ZETT_LOG_LEVEL` | Log directory and level |
| `ZETT_PROCESS_SUPERVISOR_ENABLED` | Start missing scheduler and worker processes from the Web service |
| `ZETT_SUPERVISOR_POLL_SECONDS` | Process supervision interval |
| `ZETT_HEARTBEAT_INTERVAL_SECONDS` | Scheduler and worker heartbeat interval |
| `ZETT_HEARTBEAT_TIMEOUT_SECONDS` | Age after which a process heartbeat is stale |
| `ZETT_PROCESS_WATCHDOG_ENABLED` | Enable the orphan-process watchdog for scheduler and worker |
| `ZETT_PROCESS_WATCHDOG_INTERVAL_SECONDS` | Interval between runtime ownership checks |
| `ZETT_PROCESS_WATCHDOG_FAILURE_THRESHOLD` | Consecutive failures required before a child exits |
| `ZETT_WORKER_PROCESSES` | Required number of execution worker processes |

Conversation limits are user settings rather than environment variables:
`max_message_images`, `max_turn_iterations`, `compaction_max_tokens`, and
`compaction_keep_recent_tokens`, read and replaced through `/api/settings`.

Run the API, scheduler, and at least one worker as separate long-lived processes
that share the same `ZETT_*` paths:

```bash
uv run --directory backend zett start
uv run --directory backend zett scheduler
uv run --directory backend zett worker
uv run --directory backend zett stop
```

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
