# Development Rules

## Architecture

- Follow domain-driven design.
- Keep domain rules independent from FastAPI, SQLAlchemy, SQLite, LangChain, and CLI frameworks.
- Put use-case orchestration in the application layer.
- Put database, ORM, DAO, repository, and external-provider adapters in `zett/infra`.
- Interfaces such as HTTP and CLI must call application services instead of DAOs directly.

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

- Obtain project loggers through `zett.infra.log.get_logger` instead of calling `logging.getLogger` directly.
- Configure logging through `zett.infra.log.configure_logging` at process entry points.
- Store logs under the configured user data directory and never log provider secrets or card contents by default.

## Current Rebuild Scope

- Zett is currently a storage foundation, not a complete application.
- Retain Session, Asset, Artifact, and Provider storage boundaries.
- Session records, immutable raw messages, and versioned context snapshots belong to zett-agent; do not duplicate their tables in Zett.
- Cards and articles are Artifact content variants, not separate library resources.
- Do not reintroduce Tag, Workspace, permanent Resource adapters, legacy APIs, or migration code without a new requirement.
- Keep the standalone zett-agent package unchanged when rebuilding application logic.
- Preserve frontend UI source unless a frontend change is explicitly requested. Missing APIs are expected during this rebuild; do not invent compatibility responses.
- Serve the frontend and the async health endpoint; design new business services and APIs separately.
- Asset metadata, Artifact records, and encrypted Provider configurations use SQLAlchemy in the application database.
- Store binary assets under the configured user asset directory, with one canonical UUID directory per session.
- Never expose filesystem paths in public asset models.
- Delete owned artifacts and asset files explicitly before removing the Agent session. Do not rely on foreign keys or cascades.
- Tests must exercise actual temporary SQLite databases and clean up their data.
