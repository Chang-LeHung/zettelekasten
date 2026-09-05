# Development Rules

## Architecture

- Follow domain-driven design.
- Keep domain rules independent from FastAPI, SQLAlchemy, SQLite, LangChain, and CLI frameworks.
- Put use-case orchestration in the application layer.
- Put database, ORM, DAO, repository, and external-provider adapters in `kcs/infra`.
- Interfaces such as HTTP and CLI must call application services instead of DAOs directly.

## Persistence

- Use SQLAlchemy ORM models and typed SQLAlchemy expressions for persistence.
- Do not hand-write SQL for CRUD, filtering, joins, or relationships.
- Raw SQL is allowed only when SQLite-specific functionality has no practical ORM equivalent, and it must be isolated in `kcs/infra`.
- Do not use database foreign keys, `ondelete`, or cascade rules.
- Store references as IDs and clean relation rows explicitly in storage implementations.
- Storage methods must return typed Pydantic read models, never untyped dictionaries at the public boundary.

## Models and Types

- Separate write models from read models.
- Use generic storage contracts with entity, ID, and list-option type parameters.
- Each storage implementation must provide typed `create`, `get`, `update`, `delete`, and `list` methods.
- Append-only logs and immutable snapshots use specialized `append` or versioned `create` boundaries and must not expose mutation methods.
- Use enums for finite domain values and explicit option objects for complex queries.

## Tooling

- Use Python 3.14 and `uv` for backend dependency management.
- Use Ruff for formatting and linting.
- Use Vue 3 with TypeScript for the frontend.
- Keep backend API calls in dedicated typed client modules under `frontend/src/api`.
- Vue components must not call `fetch` directly or hard-code backend endpoint URLs.
- Do not run `git commit` unless the user explicitly requests a commit.
- Add regression tests for runtime bugs and run them from `make check`.
- Tests must use an isolated temporary database and never modify user data.

## Logging

- Obtain project loggers through `kcs.infra.logging.get_logger` instead of calling `logging.getLogger` directly.
- Configure logging through `kcs.infra.logging.configure_logging` at process entry points.
- Store logs under the configured user data directory and never log provider secrets or card contents by default.

## Agent Sessions

- Persist sessions, messages, artifacts, agent runs, tool calls, and observability metrics in SQLite.
- Keep session records provider-neutral and align usage and latency names with GenAI observability conventions.
- Define backend agent capabilities as typed KCS Agent tools under `kcs/agent`.
- Use schema-bound tool output with typed Pydantic validation whenever model output is consumed as structured data; do not parse model-authored prose as JSON.
- Use the custom KCS Agent loop; do not add Deep Agents or another prebuilt agent runtime.
- Keep raw conversation messages append-only and build model context from the latest versioned snapshot plus its replay tail.
- Implement context compaction as middleware before the primary model call; never rewrite or delete raw history during compaction.
- Implement streaming agents through the `StreamingAgent` boundary and keep each concrete agent in its own module.
- Group related typed tool operations in a class before adapting them to KCS Agent tools.
- Keep the agent runtime small: direct message fields, explicit history and tools, and a readable model/tool loop. Do not add generic state containers or an extension framework without a concrete new requirement.
- KCS owns session persistence, compaction, and observability; pass prepared history to the runtime explicitly.
- A conversation may own multiple durable card artifacts and each artifact must have a stable ID.
- Persist an artifact only when the user explicitly requests saving or invokes the save action.
- Stream conversational text and artifact updates as separate SSE events.
- Treat client disconnects as cancellation: persist partial assistant output and mark the run and active tool call cancelled.
- Store session asset metadata in SQLite and binary payloads under the configured user asset directory.
- Isolate binary assets in one canonical UUID directory per session and never expose filesystem paths through APIs.
- Delete session assets and their local directory explicitly; do not rely on foreign keys or cascade behavior.
