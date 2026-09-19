# Development Rules

## Architecture

- Follow domain-driven design.
- Keep domain rules independent from FastAPI, SQLAlchemy, SQLite, and CLI frameworks.
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

## Agent Context

- Do not add per-turn injections that rebuild the leading system prefix. A conversation starts with none of that state, and later tool calls and results already carry it, so rebuilding the prefix invalidates prompt-cache prefixes without adding unseen information. `ZettelkastenExtension.on_tool`, `AssetExtension.on_tool`, and `TagExtension.on_tool` record this decision for their own domains.
- Retrieve existing knowledge through tools (`query_artifacts`, `list_assets`, `list_tags`), not through injected snapshots.
- Keep model-facing artifact previews bounded: `ArtifactPruner` projects search results, complete documents are read only on explicit request, and server-owned paths such as a LaTeX `project_path` never appear in a preview.
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

- Retain the Session, Asset, Artifact, Tag, and Provider storage boundaries.
- Session records, immutable raw messages, and versioned context snapshots belong to zett-agent; do not duplicate their tables in Zett.
- Cards, articles, images, slide decks, and LaTeX PDFs are Artifact content variants, not separate library resources.
- Tag taxonomy is a first-class boundary again: write through `TagService` so paths stay normalized and missing ancestors are created, and remove `artifact_tags` rows explicitly when an artifact is deleted. Suggested tags stay proposals until a save confirms them.
- Do not reintroduce Workspace or permanent Resource adapters, legacy APIs, or migration code without a new requirement.
- Changing the standalone zett-agent package is allowed, including for runtime behavior such as steering. Keep its own Ruff and pytest checks green (`make zett-agent-check`) and keep Zett business vocabulary out of it.
- Serve the frontend and the API from `zett.main`; new behavior is added as application services and routes, not as compatibility shims.
- Asset metadata, Artifact records, Tag records, and encrypted Provider configurations use SQLAlchemy in the application database.
- Store binary assets under the configured asset directory, with one canonical UUID directory per session.
- Store LaTeX artifact projects under the configured artifact directory: one directory per session, one per artifact, validated for canonical IDs and symlink escape before every read.
- Never expose filesystem paths in public models.
- Delete owned artifacts, tag links, and asset files explicitly before removing the Agent session. Do not rely on foreign keys or cascades.
- Tests must exercise actual temporary SQLite databases and clean up their data.

## Documentation

- Update `backend/README.md` and this file in the same change that alters the API surface, storage boundaries, settings, or agent context behavior. Stale rules cost more than missing ones: both files previously described removed endpoints and prohibitions that the code had already moved past.
