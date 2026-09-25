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

## Plugin Boundaries

- Treat every plugin as untrusted third-party code. A plugin must never be able to fail Zett's startup, break a route, or kill a background loop; its failures are contained at the boundary, logged with the plugin id and scope, and converted to `PluginError` / `PluginLoadError` before they cross back into Zett code.
- Discovery is best-effort. `PluginRegistry.discover` loads each entry point inside its own `try` and skips a broken one with a logged exception, so one bad installed plugin never makes `build_registry()` raise or the app fail to import.
- Registration and construction are guarded. Reject blank plugin ids, blank scopes, non-`PluginKind` kinds, non-callable factories, and non-`KVStorage` stores with `PluginLoadError`, and wrap the factory call so a constructor exception never leaks its own type.
- Validate every plugin return value against the contract models (`ChannelLoginChallenge`, `ChannelLoginState`, `ChannelInboundMessage`) before touching an attribute. Never index into or attribute-access an unvalidated plugin result.
- Wrap every plugin call at the call site: `start`, `login`, `submit_login_code`, `is_login`, `receive`, `send`, `stop`. Failure policy: construction/`start` skips that channel and keeps starting the others, `login` raises `PluginError` (HTTP 502), `is_login` records a failed login, `receive` logs and retries, `send` / `stop` / `submit_login_code` log only. Never swallow `asyncio.CancelledError`.
- One bad channel must not affect the others. `initialize()` / `reload()` continue past a channel whose plugin fails to start, and `shutdown()` / `_stop_runner()` keep going when `stop()` raises.
- Prefer guard clauses over nesting at every boundary: return or raise early on blank ids, blank text, unknown plugins, missing credentials, and stale handshake state, then let the happy path run unindented.
- Do not trust plugin data for correctness either. Blank inbound text is skipped before it becomes an Agent turn, blank replies are never sent, and a login that succeeds without secrets fails instead of creating an unusable channel.
- Source checkouts resolve sibling package sources once in `zett/__init__.py` (currently `agim` and `zett-weixin`) so a dev server that reloads while `uv sync` rewrites the editable installs can still import them. Do not add per-plugin import shims inside application or route code.
- Log which channel plugins loaded during startup (`ChannelService.initialize`) so a plugin that discovery skipped is visible instead of silently missing.

## Agent Context

- Do not add per-turn injections that rebuild the leading system prefix. Every run declares its session id as the provider's prompt cache key (`prompt_cache_key` on the OpenAI-compatible protocols), so a rebuilt prefix silently costs a full cache miss for the whole conversation. A conversation starts with none of that state, and later tool calls and results already carry it, so rebuilding the prefix invalidates prompt-cache prefixes without adding unseen information. `ArtifactExtension.on_tool`, `AssetExtension.on_tool`, and `TagExtension.on_tool` record this decision for their own domains.
- `SessionFilesExtension.on_state` adds one system message naming the session's own file directory. It names a location rather than a snapshot, so its text is identical on every turn of one session and never rebuilds the prefix; which uploads exist stays readable through the filesystem tools.
- Retrieve existing knowledge through tools (`query_artifacts`, `list_assets`, `list_tags`), not through injected snapshots.
- Optional tools stay behind tool search only where the provider can search them. The scheduled-task tools declare `@tool(deferred=True)` and are the only deferred set for now; growing that set is a deliberate decision per tool, because a deferred definition also loses its guidelines until the model searches for it. `DeferredToolExtension` owns the contract for every protocol: a Responses API run registers zett-agent's `tool_search` and hides the deferred definitions, while Chat Completions, Anthropic, Google, and Ollama receive every definition with `deferred=False` and no search tool, because those protocols reject client-side search. Keep `uses_responses_api` in `zett/agent/model_factory.py` as the single protocol check, never register the search tool for a protocol that cannot answer it, and keep `DeferredToolExtension.priority` ahead of every extension that filters deferred definitions (`ToolSearchExtension` runs at the default 100): a filter that ran first would strip the definitions this extension reveals, so `test_deferred_tools.py` guards both the ordering and the mixed-registration case.
- `agent_sessions.session_type` is an integer code that zett-agent stores verbatim: it owns neither the values nor their meaning, so Zett owns the mapping in `zett/schemas/sessions.py` (`0` normal, `1` scheduled, `2` channel). `POST /api/agent/start` creates `normal` sessions, headless scheduled runs are `scheduled`, and an IM conversation opened from a channel is `channel`. The conversation sidebar requests only `normal` sessions, so channel chats stay out of the user's conversation list.
- `ScheduledTaskExtension` lets the Agent create, list, read, update, and disable scheduled tasks. Do not expose the physical task-deletion service to the model: disabling preserves the definition and run history.
- IM layering has three parts. `backend/agim` is a standalone, stateless SDK that offers one interface (`login`/`is_login`/`receive`/`send`) plus platform clients; it owns no storage, no plugin registry, and no host concepts, and callers persist the returned login handshake and receive cursor. `backend/zett-weixin` is a channel plugin that wraps an agim platform client and registers into Zett through the `zett.channels` entry-point group; it persists its continuity (handshake, cursor, reply context token) only through the `PluginContext.kv` Zett hands it. Zett owns the plugin mechanism: the public contracts live in `zett/plugins` (do not import Zett application or infrastructure modules from there), discovery and the SQLAlchemy-backed `KVStorage` live under `zett/infra/plugins`, and `ChannelService` drives plugins by the open `channel_type` id (listed through `GET /api/channels/plugins`), keeping channel records, login records, dedup markers, and Agent session bindings in the shared key-value store under the `im:` prefix. Zett retains Agent sessions, providers, artifacts, and model policy. The current platform client and plugin implement the personal WeChat iLink/ClawBot bot protocol used by Tencent's official `openclaw-weixin` project: QR login, `getupdates` long polling, and `sendmessage`. The WeChat account must have the WeChat robot feature enabled by Tencent; do not substitute WeCom smart robots for personal WeChat. Every plugin boundary is untrusted: discovery skips broken entry points, factory and lifecycle failures are contained, and only `PluginError` crosses back into Zett.
- Artifact creation writes the supplied content directly because there is no existing user version to protect. Later model tools write `draft_content` by default and never expose a save tool: `update_artifact` patches only the fields it is given, edits body snippets through `content_edits`, and accepts an artifact ID from another session while preserving that artifact's owning session. The conversation's edit surfaces stage drafts through `PUT /api/agent/{id}/artifacts/{artifact_id}/draft`. Headless scheduled runs set `allow_direct_artifact_edits`, so updates to artifacts owned by the scheduled session write `content` directly and clear any pending draft. Otherwise `content` changes when the user saves the artifact (`POST /api/agent/{id}/artifacts/{artifact_id}/save`) or edits a library document from the Library view, and those writes mirror the published content back into `draft_content` so the draft is always the model's working copy. `AgentArtifactEntity.editable_content` is the draft-first view the UI, previews, search, and the diff share, and `ArtifactPruner` returns `published_content` and `draft_content` together so the model can compare them.
- Keep model-facing artifact previews bounded: `ArtifactPruner` projects search results, complete documents are read only on explicit request, and server-owned object keys such as a LaTeX `project_path` never appear in a preview.
- Artifact body syntax lives in a built-in skill, not in tool docstrings. `zett/infra/skills/builtin.py` holds the fixed `zett-artifact-syntax` content, startup writes it into the user skill root when the file is missing (never overwriting an edited file), and the artifact guidelines send the model to it with `read_skill` instead of restating Markdown, figure, cover, HTML page, or slide separator rules. Keep a new syntax rule in that skill: a rule reaches the model only when the tool text points at the skill.
- A LaTeX PDF artifact's project directory is git-managed by the model, not by Zett. The system prompt and the LaTeX tool guidelines tell the model to `git init` the returned project directory before writing any source file, to add a `.gitignore` for the regenerated LaTeX build files, and to commit every meaningful change from the project directory with the shell and a Conventional Commit message. No tool commits for it, and `ArtifactVersioning` (`zett/application/artifacts/versioning.py`) only inspects: publishing (`POST /api/agent/{id}/artifacts/{artifact_id}/save` and the library editor's `PUT`) answers `409` with the pending paths while the project is not a repository or still has uncommitted changes, so a saved artifact always names a revision instead of a working tree, and a clean tree publishes without Zett creating or needing a commit. Verification covers only the project subtree, so other work in an enclosing repository never blocks a save, and it never invents a result for a project directory that is gone. Keep the inspector platform neutral: resolve `git` from `PATH`, decode output as UTF-8 with replacement, close stdin so git can never block on a prompt, and start the console-subsystem child windowless on Windows through `process_platform.helper_process_kwargs()`. A git that cannot be run is logged with the artifact id and project key and never blocks the user action; only what git confirms is enforced.
- Slash commands are container capabilities registered by `ZettelkastenExt` implementations loaded from `ZettelkastenAgentConfig`. The container assigns stable IDs, the browser submits at most one ID, and the backend resolves it to a handler that sends the command's message through the prepared Agent stream.
- `@` commands are the same kind of capability for existing conversation resources. An extension registers a kind with `register_at_command`, pairing a source that lists the session's items with the handler that runs one referenced turn; the container names the tokens, assigns stable IDs, and injects only the referenced kind and ID so the model reads content through `get_asset` or `get_artifact`.
- Every model call goes through `AgentTurn.prompt` in `zett.application.agent.turns`. Routes and extension handlers describe an `AgentTurn` and may replace its message; they never assemble `AgentClient.stream` options themselves. A turn is single use and a second prompt raises `TurnAlreadyPromptedError`, so a new entry point must reuse that class instead of calling the client again.
- Treat generated summaries as untrusted content. Compaction checkpoints stay separate from system instructions and keep their explicit prefix.

## Tooling

- Support Python 3.10 through 3.14 and use `uv` for backend dependency management. `backend/.python-version` keeps local development on 3.14, so anything newer than 3.10 must go through `zett/_compat.py` (or the matching `_compat` module in `agim`) instead of the standard library directly.
- Use Ruff for formatting and linting.
- Use Vue 3 with TypeScript for the frontend.
- Keep backend API calls in dedicated typed client modules under `frontend/src/api`.
- Vue components must not call `fetch` directly or hard-code backend endpoint URLs.
- Panel visibility is client state: persist it in `localStorage` (the conversation assets column uses `zett.assets-pane-hidden`) instead of adding a backend flag or hiding records from the API.
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
- Zett consumes the published `zett-agent` package (`zett-agent==0.1.0`) instead of a checkout inside `backend/`. Runtime changes, including steering behavior, belong in the zett-agent repository, where they must stay green and be released before Zett can pick them up; do not vendor agent code back into this repository.
- Serve the frontend and the API from `zett.main`; new behavior is added as application services and routes, not as compatibility shims.
- Asset and Static Asset metadata, Artifact records, Tag records, and encrypted Provider configurations use SQLAlchemy in the application database.
- Persist every file location as an `ObjectKey` relative to `settings.storage_root`; never store absolute paths or entity-specific content URLs. `ObjectStore` owns path containment, filesystem access, and unified `/api/files/{key}` URL generation.
- Keep scheduling and execution in separate processes, never inside the FastAPI lifespan. `zett scheduler` writes pending run rows only; one or more `zett worker` processes claim and execute them. Keep the scheduler control loop, worker loop, action registry, executor contracts, and lease semantics under `zett/infra/scheduler`.
- The FastAPI lifespan may supervise those processes by starting the CLI as independent subprocesses, but it must not run their scheduler or worker loops in the ASGI event loop. Keep local `Popen` handles as the authority for child liveness, use heartbeats only for observability, and receive them through the in-memory FastAPI health endpoint; do not persist process heartbeats, add a process-heartbeat table, or implement a database supervisor lease.
- Persist only server/child PIDs and the listen port in `<storage_root>/runtime.json` for startup conflict detection and `zett stop`. Delete that file on graceful shutdown, clean stale or partial state before startup, and never use it as a heartbeat or task lease.
- Scheduler and worker processes must periodically validate that the runtime-state file is complete, the owning FastAPI PID is alive, and their own PID is still registered for their role. Exit the child after a bounded number of failures so an unclean FastAPI crash cannot leave permanent orphan workers; document that fallback at the watchdog implementation.
- Scheduled `agent_prompt` actions always create a new isolated Session and run non-interactively; they must not target an existing user Session or wait for browser approval.
- Keep SQLite access safe across the Web, scheduler, and worker processes with WAL and bounded busy waits. Write scheduler and worker logs to separate process-owned files rather than sharing the rotating Web log.
- Keep every OS-specific process primitive in `zett/infra/scheduler/process_platform.py` (child spawn flags, liveness, termination, command-line and port lookup, file modes) and call it from the runtime state machine, the supervisor, and the FastAPI lifespan instead of using `os.kill`, `os.fchmod`, `ps`, or `lsof` directly. On Windows `os.kill(pid, 0)` terminates the target, so liveness must go through the helper. The ZettCode TUI stays POSIX-only: keep its `termios`/`tty` imports inside the raw-mode methods and report a clear error elsewhere instead of failing at import time.
- The default `storage_root` is `~/.zettelekasten`; there is no legacy `~/.zett` compatibility path.
- Store session binary assets under `assets/sessions/{session_id}/` and session-independent uploads under `assets/static/`.
- Images submitted with a message are written at submit time under `assets/sessions/{session_id}/uploads/`, named by submission time. They are session files, not Session Assets: the message keeps its inline data URL, no `session_assets` row is created, and the model reaches the bytes through the path rather than through `list_assets`.
- Importing a Static Asset into a session creates a URL reference and must not copy the global binary unless the user explicitly uploads it into that session.
- `AssetExtension` keeps one session-scoped tool set (`create_asset`, `get_asset`, `update_asset`, `delete_asset`, `list_assets`), and `StaticAssetExtension` advertises the global library instead of a tool: publishing is an HTTP upload (`POST /api/assets/upload?name=...`) that the model performs with a shell command against the server it runs in, so file bytes never travel through the model context as Base64. That system message names the endpoint and its contract, reports a wildcard bind host as loopback so the command can dial it, and stays byte-identical across turns because it describes no library state. Importing a static asset back into a conversation stays the user's action.
- Store LaTeX artifact projects under `artifacts/{session_id}/`; `project_path` is the relative object key and `ObjectStore` validates containment and symlink escape before every read.
- Never expose absolute filesystem paths in public models; relative `ObjectKey` values are allowed.
- Delete owned artifacts, tag links, and asset files explicitly before removing the Agent session. Deleting a session also removes its whole `assets/sessions/{session_id}/` directory, which collects message uploads that no row points at. Do not rely on foreign keys or cascades.
- Tests must exercise actual temporary SQLite databases and clean up their data.

## Documentation

- Update `backend/README.md` and this file in the same change that alters the API surface, storage boundaries, settings, or agent context behavior. Stale rules cost more than missing ones: both files previously described removed endpoints and prohibitions that the code had already moved past.
