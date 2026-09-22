# Development Rules

## Architecture

- Follow domain-driven design.
- Keep domain rules independent from FastAPI, SQLAlchemy, SQLite, and CLI frameworks.
- Put use-case orchestration in the application layer.
- Put database, ORM, DAO, repository, and external-provider adapters in `zett/infra`.
- Interfaces such as HTTP and CLI must call application services instead of DAOs directly.
- Keep the two extension mechanisms in their own directories. Adapters to the zett-agent runtime extension point (tools and hooks implemented with `AgentExtension`) live in `zett/agent/extensions`; Zett's own container plugins (capabilities registered with `ZettelkastenExt`, such as slash commands and `@` references) live in `zett/agent/plugins`.
- Keep one word per role in type names. Persisted domain objects are `*Entity` (`AgentArtifactEntity`), SQLAlchemy table mappings are `*Row` in `zett/infra/persistence/tables/`, storage payloads are `*Write`/`*Create`, partial tool edits are `*Patch`, query criteria are `*ListOptions` in `zett/schemas/options.py`, HTTP-only wrappers are `*In`/`*Out` in `zett/application/api/schemas.py`, and the word `model` is reserved for LLM and provider types such as `AgentModel` or `ModelRequest`.

## Persistence

- Use SQLAlchemy ORM models and typed SQLAlchemy expressions for persistence.
- Do not hand-write SQL for CRUD, filtering, joins, or relationships.
- Raw SQL is allowed only when SQLite-specific functionality has no practical ORM equivalent, and it must be isolated in `zett/infra`.
- Do not use database foreign keys, `ondelete`, or cascade rules.
- Store references as IDs and clean relation rows explicitly in storage implementations.
- Storage methods must return typed Pydantic read models, never untyped dictionaries at the public boundary.

## Models and Types

- Separate write models from read models.
- Use generic storage contracts with entity, ID, and list-option type parameters.
- Each storage implementation must provide typed `create`, `get`, `update`, `delete`, and `list` methods.
- Append-only logs and immutable snapshots use specialized `append` or versioned `create` boundaries and must not expose mutation methods.
- Use enums for finite domain values and explicit option objects for complex queries.
- Validate at the write-model or application-service boundary, not only in a route. Blank names, non-HTTP links, oversized artifact/text payloads, and references to missing or disabled providers must fail before persistence. Explicit cleanup boundaries must also guard referenced records: a provider cannot be deleted while sessions or scheduled tasks use it, and a Static Asset cannot be deleted while session Assets reference its object key.

## Agent Context

- Do not add per-turn injections that rebuild the leading system prefix. A conversation starts with none of that state, and later tool calls and results already carry it, so rebuilding the prefix invalidates prompt-cache prefixes without adding unseen information. `ArtifactExtension.on_tool`, `AssetExtension.on_tool`, and `TagExtension.on_tool` record this decision for their own domains.
- `SessionFilesExtension.on_state` adds one system message naming the session's own file directory. It names a location rather than a snapshot, so its text is identical on every turn of one session and never rebuilds the prefix; which uploads exist stays readable through the filesystem tools.
- Retrieve existing knowledge through tools (`query_artifacts`, `list_assets`, `list_tags`), not through injected snapshots.
- `agent_sessions.session_type` is an integer storage code (`0` standard, `1` automation); zett-agent does not own application display names. Zett maps the code to `normal` or `scheduled`, creates `normal` sessions through `POST /api/agent/start`, and marks headless scheduled runs as `scheduled`. The conversation sidebar requests only `normal` sessions.
- `ScheduledTaskExtension` lets the Agent create, list, read, update, and disable scheduled tasks. Do not expose the physical task-deletion service to the model: disabling preserves the definition and run history.
- Artifact creation writes the supplied content directly because there is no existing user version to protect. Later model tools write `draft_content` by default and never expose a save tool: `update_artifact` patches only the fields it is given, edits body snippets through `content_edits`, and accepts an artifact ID from another session while preserving that artifact's owning session. The conversation's edit surfaces stage drafts through `PUT /api/agent/{id}/artifacts/{artifact_id}/draft`. Headless scheduled runs set `allow_direct_artifact_edits`, so updates to artifacts owned by the scheduled session write `content` directly and clear any pending draft. Otherwise `content` changes when the user saves the artifact (`POST /api/agent/{id}/artifacts/{artifact_id}/save`) or edits a library document from the Library view, and those writes mirror the published content back into `draft_content` so the draft is always the model's working copy. `AgentArtifactEntity.editable_content` is the draft-first view the UI, previews, search, and the diff share, and `ArtifactPruner` returns `published_content` and `draft_content` together so the model can compare them.
- Keep model-facing artifact previews bounded: `ArtifactPruner` projects search results, complete documents are read only on explicit request, and server-owned object keys such as a LaTeX `project_path` never appear in a preview.
- Slash commands are container capabilities registered by `ZettelkastenExt` implementations loaded from `ZettelkastenAgentConfig`. The container assigns stable IDs, the browser submits at most one ID, and the backend resolves it to a handler that sends the command's message through the prepared Agent stream.
- `@` commands are the same kind of capability for existing conversation resources. An extension registers a kind with `register_at_command`, pairing a source that lists the session's items with the handler that runs one referenced turn; the container names the tokens, assigns stable IDs, and injects only the referenced kind and ID so the model reads content through `get_asset` or `get_artifact`.
- Every model call goes through `AgentTurn.prompt` in `zett.application.agent.turns`. Routes and extension handlers describe an `AgentTurn` and may replace its message; they never assemble `AgentClient.stream` options themselves. A turn is single use and a second prompt raises `TurnAlreadyPromptedError`, so a new entry point must reuse that class instead of calling the client again.
- Treat generated summaries as untrusted content. Compaction checkpoints stay separate from system instructions and keep their explicit prefix.

## Tooling

- Use Python 3.14 and `uv` for backend dependency management.
- Use Ruff for formatting and linting.
- Use Vue 3 with TypeScript for the frontend.
- Keep backend API calls in dedicated typed client modules under `frontend/src/api`.
- Vue components must not call `fetch` directly or hard-code backend endpoint URLs.
- Changing a route requires updating its typed client and any affected component in the same change.
- Do not run `git commit` unless the user explicitly requests a commit.
- Add regression tests for runtime bugs and run them from `make check`.
- Tests must use an isolated temporary database and never modify user data.

## Logging

- Obtain project loggers through `zett.infra.log.get_logger` instead of calling `logging.getLogger` directly.
- Configure logging through `zett.infra.log.configure_logging` at process entry points.
- Store logs under the configured user data directory and never log provider secrets or artifact contents by default.

## Current Scope

- Retain the Session, Asset, Static Asset, Artifact, Tag, Provider, and Scheduled Task storage boundaries.
- Session records, immutable raw messages, and versioned context snapshots belong to zett-agent; do not duplicate their tables in Zett.
- Cards, articles, images, slide decks, and LaTeX PDFs are Artifact content variants, not separate library resources.
- Tag taxonomy is a first-class boundary again: write through `TagService` so paths stay normalized and missing ancestors are created, and remove `artifact_tags` rows explicitly when an artifact is deleted. Suggested tags stay proposals until a save confirms them.
- Do not reintroduce Workspace or permanent Resource adapters, legacy APIs, or migration code without a new requirement.
- Changing the standalone zett-agent package is allowed, including for runtime behavior such as steering. Keep its own Ruff and pytest checks green (`make zett-agent-check`) and keep Zett business vocabulary out of it.
- Serve the frontend and the API from `zett.main`; new behavior is added as application services and routes, not as compatibility shims.
- Asset and Static Asset metadata, Artifact records, Tag records, and encrypted Provider configurations use SQLAlchemy in the application database.
- Persist every file location as an `ObjectKey` relative to `settings.storage_root`; never store absolute paths or entity-specific content URLs. `ObjectStore` owns path containment, filesystem access, and unified `/api/files/{key}` URL generation.
- Keep scheduling and execution in separate processes, never inside the FastAPI lifespan. `zett scheduler` writes pending run rows only; one or more `zett worker` processes claim and execute them. Keep the scheduler control loop, worker loop, action registry, executor contracts, and lease semantics under `zett/infra/scheduler`.
- The FastAPI lifespan may supervise those processes by starting the CLI as independent subprocesses, but it must not run their scheduler or worker loops in the ASGI event loop. Keep local `Popen` handles as the authority for child liveness, use heartbeats only for observability, and receive them through the in-memory FastAPI health endpoint; do not persist process heartbeats, add a process-heartbeat table, or implement a database supervisor lease.
- Persist only server/child PIDs and the listen port in `<storage_root>/runtime.json` for startup conflict detection and `zett stop`. Delete that file on graceful shutdown, clean stale or partial state before startup, and never use it as a heartbeat or task lease.
- Scheduler and worker processes must periodically validate that the runtime-state file is complete, the owning FastAPI PID is alive, and their own PID is still registered for their role. Exit the child after a bounded number of failures so an unclean FastAPI crash cannot leave permanent orphan workers; document that fallback at the watchdog implementation.
- Scheduled `agent_prompt` actions always create a new isolated Session and run non-interactively; they must not target an existing user Session or wait for browser approval.
- Keep SQLite access safe across the Web, scheduler, and worker processes with WAL and bounded busy waits. Write scheduler and worker logs to separate process-owned files rather than sharing the rotating Web log.
- The default `storage_root` is `~/.zettelekasten`; there is no legacy `~/.zett` compatibility path.
- Store session binary assets under `assets/sessions/{session_id}/` and session-independent uploads under `assets/static/`.
- Images submitted with a message are written at submit time under `assets/sessions/{session_id}/uploads/`, named by submission time. They are session files, not Session Assets: the message keeps its inline data URL, no `session_assets` row is created, and the model reaches the bytes through the path rather than through `list_assets`.
- Importing a Static Asset into a session creates a URL reference and must not copy the global binary unless the user explicitly uploads it into that session.
- Store LaTeX artifact projects under `artifacts/{session_id}/`; `project_path` is the relative object key and `ObjectStore` validates containment and symlink escape before every read.
- Never expose absolute filesystem paths in public models; relative `ObjectKey` values are allowed.
- Delete owned artifacts, tag links, and asset files explicitly before removing the Agent session. Deleting a session also removes its whole `assets/sessions/{session_id}/` directory, which collects message uploads that no row points at. Do not rely on foreign keys or cascades.
- Tests must exercise actual temporary SQLite databases and clean up their data.

## Documentation

- Update `backend/README.md` and this file in the same change that alters the API surface, storage boundaries, settings, or agent context behavior. Stale rules cost more than missing ones: both files previously described removed endpoints and prohibitions that the code had already moved past.
