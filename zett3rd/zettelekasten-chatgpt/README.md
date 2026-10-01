# Zettelekasten for ChatGPT

A loopback MCP Apps integration that saves cards and articles to
Zettelekasten's shared Library Session, classifies them, and reads or edits
them from ChatGPT. No ChatGPT conversation data is stored.

## Run locally

1. From this repository root start the server:
   `uv run --directory backend zett start`. An older installed server may lack
   `published_only` and `expected_version`; stop it first if it owns the port.
2. In this directory: `npm ci`, `npm run build`, then
   `ZETT_BASE_URL=http://127.0.0.1:6280 npm run dev`. `ZETT_MCP_PORT` changes
   the MCP port (default 6281); the base URL must be a loopback origin.
3. Connect `http://127.0.0.1:6281/mcp` from ChatGPT or Codex developer mode.
   The web app cannot reach `127.0.0.1` directly, so use
   [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

The server is loopback-only and unauthenticated: never forward Zettelekasten's
`/api` or this MCP endpoint through a public tunnel or proxy.

## Tools

- `list_categories`, `search_knowledge`, `get_knowledge` — published cards and
  articles only; drafts and `raw_content` never reach the model.
- `save_knowledge` — creates a saved artifact with `metadata.source=codex`;
  repeating the call creates a duplicate.
- `show_knowledge_card`, `edit_knowledge` — render and edit the in-chat card.
  Edits pass `expected_version` and refuse stale or draft-carrying artifacts.
  If classification fails after a body edit, reload before retrying.

## Checks

`npm run typecheck` and `npm test` run against mocked responses and ephemeral
ports. Backend coverage runs in `make check`.
