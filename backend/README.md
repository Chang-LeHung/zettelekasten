# Zett storage foundation

The application backend has been reset for a new design. The existing Vue UI
and the standalone `zett-agent` package are unchanged by this reset.

## Retained storage

| Boundary | Owner | Contents |
| --- | --- | --- |
| Session | `zett-agent` | Session records, immutable raw messages, context snapshots |
| Asset | Zett | Text, links, image/file metadata, session-scoped binary files |
| Artifact | Zett | Card, article, and image content in one typed table |
| Provider | Zett | Model endpoint metadata and encrypted API credentials |

`infra/dao/session.py` delegates to the package session store. It does not create a
second session table. Deleting a session explicitly removes its assets and
artifacts before deleting its Agent history. These operations cross two SQLite
databases and the filesystem, so they are retryable cleanup, not one transaction.

Cards and articles are artifact variants, not separate library resources. There
are no Tag, Workspace, or permanent Resource tables or adapters.

## HTTP and CLI

`zett start` serves the existing frontend and `GET /api/health`. Former business
endpoints remain removed. A minimal `ZettelkastenAgent` facade now composes the
standard `zett-agent` client with an injected asynchronous SSE sender, but it is
not yet exposed through FastAPI. UI layout is preserved; data loading, chat,
settings, and editing workflows remain unavailable until new application
services and APIs are designed. No compatibility routes are installed.

## Local data

New data uses `~/.zett/zett.db`, `~/.zett/agent.db`, and `~/.zett/assets` unless
overridden by the corresponding `ZETT_*` settings. Startup creates only the
current tables; there is no old-data migration path.

Tests use temporary SQLite databases and asset directories and clean them up
after execution. Run `make check` from the repository root.
