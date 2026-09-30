# Zett backend

FastAPI service and argparse CLI for Zett. The backend owns two SQLite databases,
a few file directories, and serves the compiled Vue frontend from `zett/static`
when a build exists.

## Layers

| Path | Contents |
| --- | --- |
| `zett/agent/` | Composition root for conversations: container, capability contracts, model factory, SSE dispatcher, session title agent |
| `zett/agent/extensions/` | Zett's adapters to the zett-agent `AgentExtension` point: the asset, artifact, tag, upload, and context-composition tools |
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

### Chrome panel browser tools

The Chrome integration under `zett3rd/chrome-extension` embeds an isolated
extension frame in a webpage through its content script. Each tab/page URL
maps to its own persisted Agent session; reopening restores history through
`GET /api/agent/sessions/{id}`. The panel automatically connects the current
document on open using `WS /api/agent/{session_id}/browser`: an extension-origin
handshake returns a `ready` frame with a temporary token. A normal
`POST /api/agent/{session_id}/messages` supplies that value as `browser_token`.
The application validates the live connection before constructing the Agent;
missing, stale, or cross-session tokens fail with 409. Without a token there are
no browser tools, including in normal Web, CLI, scheduled, and channel turns.

`BrowserExtension` exposes two tools:

- `get_browser_page(selector=None)`: the connected document's title, URL, bounded
  visible text and form-control descriptions with usable CSS selectors. An
  optional selector reads exactly one subtree. Hidden, password, file-input,
  and script contents are excluded.
- `update_browser_dom(change)`: one CSS selector, an action, a value and a short
  description. Actions are `set_text` (plain text elements), `fill` (text-like
  inputs/textareas and `contenteditable="true"` editors), `select` (existing enabled options), and `set_checked`
  (checkboxes). The panel displays the edit and waits for **Allow once** or
  **Reject**. Updates target exactly one visible, supported, enabled element.
- `interact_with_browser(interaction)`: one reviewed click, double-click,
  hover, focus, scroll, bounded key press or drag/drop, with a single
  unambiguous selector and action-specific parameters. The content script
  dispatches synthetic DOM events. A result confirms dispatch, not the
  website's final state; callers must read the page again to verify.

`application/agent/browser.py` orchestrates commands without a FastAPI dependency;
the WebSocket route is a transport adapter and the extension is the executor.
Frames use command IDs, one pending operation per connection, and bounded
payloads (500-character selectors, 10,000-character values, 64 KB result, 100 KB incoming frame).
Approval expires after 90 seconds, the server waits at most 120 seconds, and
content-script replies have a ten-second client wait bound and message expiry.
Disconnect/cancellation fails outstanding work and never retries a mutation.
No connection, token, command queue, or page snapshot is stored in the database.
Normal Agent tool history still records tool arguments and results.

The panel injects the bundled `content-script.js` using `chrome.scripting`, then
uses `chrome.tabs.sendMessage` pinned to the top-frame `documentId`. A per-connection
nonce, sender validation, expiry and duplicate detection guard the content-script
boundary. There is no debugger permission or arbitrary JS execution: values
remain plain data, `set_text` uses `textContent`, and HTML, arbitrary attributes,
arbitrary JavaScript and direct navigation are not supported. A reviewed click
or key press can activate a site's submit control, but synthetic events may be
ignored by sites requiring trusted input. Filling fields dispatches
input/change events, which may trigger the website's own autosave handlers.
Rich text editors use the browser's `insertText` editing command on a selected
contenteditable root, allowing frameworks such as ProseMirror to process a real
input event rather than having their nested DOM overwritten. Rejected input
returns an error; form submission is never implied.
Switching tabs leaves each tab's connection separate. Navigating to another
URL opens that page's own conversation and new document connection; stopping
or closing the panel disconnects control, with explicit retry available.
Cross-origin iframes, background/offline automation, and rollback are not provided.
An error/timeout does not prove an edit had no effect. Inspect before retrying.

Extension-origin checks block ordinary websites, not native clients that can
forge an Origin header. This local server is not a multi-user authentication
service: use loopback, or an authenticated TLS proxy for remote deployments.
The token goes in WebSocket frames and message bodies, never URL logs.

### Persisted resources

| Boundary | Owner | Tables and files |
| --- | --- | --- |
| Session | `zett-agent` | `agent_sessions`, `raw_messages`, `session_snapshots` |
| Asset | Zett | `session_assets` plus binary files stored by relative object key |
| Message upload | Zett | `assets/sessions/<session-id>/uploads/` files written at submit time; no metadata row |
| Static asset | Zett | `static_assets` plus uploaded files stored by relative object key |
| Artifact | Zett | `session_artifacts`: card, article, image, slides, latex_pdf with published `content_json` and model `draft_content_json` |
| Tag | Zett | `tags`, `tag_links` (one relation for artifacts and static assets) |
| Provider | Zett | `providers`, with credentials encrypted by the local provider key |
| Runtime settings | Zett | `key_values` under `settings.runtime` |
| Scheduled task | Zett | `scheduled_tasks` and `scheduled_task_runs`; `zett scheduler` queues due runs and `zett worker` executes them |
| Process heartbeat | Zett | In-memory FastAPI registry populated through `/api/health/processes/heartbeat` |

`infra/dao/session.py` delegates to the package session store and does not
create a second session table.

`agent_sessions.session_type` stores an integer code that zett-agent keeps
verbatim; the codes and their meaning belong to Zett, which maps them in
`zett/schemas/sessions.py`: `0` is `normal`, `1` is `scheduled`, and `2` is
`channel`. `POST /api/agent/start` creates `normal` sessions, the scheduled
Agent executor creates `scheduled` sessions, and an IM conversation opened from a
channel creates a `channel` session. The conversation sidebar requests only
`normal` sessions, so channel chats stay out of it, while scheduled runs can
still open their session by ID.
Schema initialization adds the column to existing databases, but historical
rows are not reclassified: they receive the default `0` code, so channel
conversations created before this change keep showing up as `normal`.

Records reference each other by ID only: there are no foreign keys,
`ondelete` rules, or cascades. Storage implementations clean relation rows and
owned files explicitly. Deleting a session therefore spans two SQLite
databases and the filesystem, so cleanup is idempotent and retryable rather
than one transaction.

Public write models reject blank display names, require absolute HTTP(S) link
URLs, and bound artifact text and JSON payloads. Deleting a provider is blocked
while a session preference or scheduled task still references it. Deleting a
Static Asset is blocked while any session Asset references its object key.

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

`AssetExtension` exposes the session-scoped tools `create_asset`, `get_asset`,
`update_asset`, `delete_asset`, and `list_assets`; importing a static asset into
a conversation remains the user's action. `StaticAssetExtension` owns the global
Static Assets library: `upload_static_asset` publishes a file by its absolute
path, so bytes never travel through an argument or as Base64, and
`create_asset_tag`, `list_asset_tags`, and `set_asset_tags` classify it inside
that library's own collection tree. One system message states what the library is
for; it names no route and describes no library state, so it stays byte-identical
across turns, and the HTTP route stays available for scripts and shells without
being part of the agent's prefix.

The scheduled-task tools are declared `deferred` and are the only deferred set
for now, so they leave a request until the model finds them through search.
`DeferredToolExtension` owns which protocol sees what: a Responses API run
registers zett-agent's `tool_search` and hides every deferred definition, while
Chat Completions, Anthropic, Google, and Ollama receive all of them as ordinary
functions with `deferred=False` and never receive the search tool, because those
protocols reject client-side search. `uses_responses_api` in
`zett/agent/model_factory.py` is the one place that decides which protocol the
adapter speaks. The rewrite runs at priority 90, ahead of zett-agent's search
extension at the default 100, because a filter that ran first would strip the
definitions this protocol still offers.

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
Headless scheduled Agent runs enable direct current-session artifact edits:
updating an artifact owned by the scheduled run's session writes `content_json`
directly and clears any pending draft, while cross-session updates remain
draft-only.
`ScheduledTaskExtension` exposes create, list, get, and update tools for
scheduled tasks, plus `list_providers`, which returns the enabled providers a
task may reference. It deliberately exposes `disable_scheduled_task` instead of a
physical delete tool, so an Agent can stop future runs without removing the
definition or its execution history.
`AgentArtifactEntity.editable_content` is the draft-first view shared by the
conversation UI, previews, search, and the draft-versus-published diff, and
`ArtifactPruner` returns `published_content` and `draft_content` previews
together so a querying model can compare what the user kept with what it
proposes.
The tools never answer with the stored row. `ArtifactReceipt`
(`zett/application/artifacts/artifact_views.py`) is what `create_artifact`,
`update_artifact`, and `set_artifact_tags` return: the id, state, version,
title, pending-draft flag, confirmed tag paths, and the server-assigned
locations — `project_path`/`pdf_name` for a LaTeX project and `asset_path` for
a local image — because `project_path` is the one server-owned key the LaTeX
workflow must preserve. Only `get_artifact` returns the bodies, as
`ArtifactDocument` with `content` and `draft_content` and none of the stored
row's `raw_content`, metadata, timestamps, or owning session. Echoing a body the
model sent in the same turn spent the context of a long article on itself.
Because the draft is that view, every model update patches the draft rather than
the published text: successive `update_artifact` calls accumulate into one
working copy, and `content_json` still changes only on create or a user save.
Tag promotion reads the published side for the same reason, and it is additive:
a save applies the suggestions that content confirms, drops only a suggestion
the editor unchecked, and never deletes an assignment it did not propose, so a
tag attached by `set_artifact_tags`, the Library, or `zett tag add` survives an
unrelated save.

The artifact body syntax lives in a built-in skill rather than in the tool
docstrings: `zett/infra/skills/builtin.py` holds the fixed
`zett-artifact-syntax` content, startup writes it into the user skill root when
the file is missing and never rewrites an edited file, and the artifact
guidelines tell the model to read that skill with `read_skill` before writing or
changing a card, article, image, slide, or LaTeX PDF body.

A `latex_pdf` artifact owns a project directory instead of an inline body, so
the Agent owns that project's git history: it initializes the repository, writes
a `.gitignore` for the regenerated LaTeX build files, and commits each meaningful
change with its own Conventional Commit message through the shell. Zett prepares
and commits nothing there; `zett/infra/artifacts/git_projects.py` only inspects
the tree when the artifact is published. Publishing a PDF artifact (the save
endpoint, or the library editor's `PUT`) therefore answers `409 Conflict` while
the project is not a git repository or still has uncommitted changes, and
publishes without touching history once the tree is clean; the failure names the
pending paths and leaves the draft unpublished. Verification covers only the
project subtree, so other work in an enclosing repository never blocks a save,
and an artifact whose directory is gone has no working tree to verify. The
inspector is platform neutral: it resolves `git` from `PATH`, reads output as
UTF-8, closes stdin so git cannot block on a prompt, and starts the
console-subsystem child windowless on Windows. A git that cannot be run is
logged by artifact id and project key and never blocks a save; only what git
confirms is enforced.

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
| `/api/agent/{id}/artifacts*`, `GET /api/artifacts` | Artifact CRUD, per-session listing, and library-wide search; optional `published_only=true` searches only published content, not draft or raw-source text |
| `POST /api/artifacts` | Create an artifact that belongs to no conversation, owned by the hidden library session; requires a non-blank `metadata.source` naming who creates it |
| `GET /api/artifacts/{artifact_id}` | Read one artifact by id, whichever session owns it |
| `DELETE /api/artifacts/{artifact_id}` | Delete one artifact, and only while the library session owns it: a conversation's artifact answers 403 and stays |
| `/api/agent/{id}/artifacts/{artifact_id}/draft` | Stage edited content as the draft without touching published content |
| `/api/agent/{id}/artifacts/{artifact_id}/save` | Publish the pending draft as the artifact's content (user action) |
| `PUT /api/agent/{id}/artifacts/{artifact_id}` | Direct user edit; optional `expected_version` rejects a stale edit or an unpublished draft with 409 |
| `/api/agent/{id}/artifacts/{artifact}` | Artifact metadata; `content_url` addresses its unified file key |
| `/api/ai/providers*` | Model endpoint configuration |
| `/api/channels*` | Channel management (list/update/delete), plugin listing at `/api/channels/plugins`, and QR login behind the installed channel plugins |
| `/api/settings` | Read or replace runtime limits |
| `/api/library/tags`, `POST/PUT/DELETE /api/library/tags/{tag_id}` | Tag tree listing, creation, single read, rename/move/restyle, and deletion |
| `PUT /api/library/tags/artifacts/{artifact_id}` | Replace the complete tag set of one saved artifact (the editor's save path) |
| `PUT/DELETE /api/library/tags/{tag_id}/artifacts/{artifact_id}` | Attach or detach one tag without rewriting the artifact's other assignments |
| `PUT /api/library/tags/assets/{asset_id}` | Replace the complete tag set of one static asset, which shares the taxonomy artifacts use |
| `PUT/DELETE /api/library/tags/{tag_id}/assets/{asset_id}` | Attach or detach one tag on a static asset without rewriting its other assignments |

IM is split across three packages. `backend/agim` is a stateless SDK with one
interface (`login` / `is_login` / `receive` / `send`) and platform clients; it
stores nothing, so callers persist the login handshake and receive cursor.
`backend/zett-weixin` is a channel plugin built on `agim` that registers into
Zett through the `zett.channels` entry-point group. Zett owns the plugin
mechanism: contracts live in `zett/plugins`, discovery and the KV adapter live
under `zett/infra/plugins`, and `ChannelService` selects a plugin by the open
`channel_type` id, drives its lifecycle, and stores channel records, login records,
dedup markers, and Agent session bindings in the shared key-value store under
the `im:` prefix. `GET /api/channels/plugins` exposes the installed platforms so
the UI can offer a picker instead of assuming one platform, and a login request
may omit `channel_type` only while exactly one plugin is installed. Zett retains
ownership of Agent sessions, providers,
artifacts, and model policy. The current platform client and plugin implement
the personal WeChat iLink/ClawBot bot protocol; the WeChat account must have
Tencent's "微信机器人" feature enabled.

One external conversation (channel plus chat id) maps to one Agent session,
bound as `im:session:<channel_id>:<chat_id>`, and turns for the same pair run
serialized. That binding can outlive its session when the conversation was
deleted, so a turn that finds its bound session missing starts a fresh session
and rebinds instead of leaving the chat mute, logging the stale id.

Inbound attachments arrive on `ChannelInboundMessage.media` as
`ChannelMedia` items holding the bytes the plugin already downloaded and
decrypted; the WeChat plugin gets them from the iLink CDN through agim, so an
image, voice note, file, or video needs no extra round trip here. Zett writes
every attachment below `assets/sessions/<session>/uploads/` and builds ordered
multimodal content for the turn: images within `MAX_INLINE_IMAGE_BYTES` travel
as image content for a vision model, and voice, files, video, and oversized
images travel as a text reference naming the stored `ObjectKey`. Whether the
configured model can use a given attachment is the model's decision, and a
media-only message is a valid turn with no text at all. A plugin owns the
objects it returns and can build them without field validation, so the receive
loop re-applies every limit itself — `MAX_CHANNEL_MEDIA_ITEMS`,
`MAX_CHANNEL_MEDIA_BYTES`, and `MAX_CHANNEL_MEDIA_TOTAL_BYTES` — and drops what
exceeds them, while `MAX_INLINE_IMAGE_TOTAL_BYTES` bounds what one turn hands
the model inline. An attachment over the limit is never silently lost: agim
reports it as a rejection, and the channel answers the sender with
`MEDIA_TOO_LARGE_REPLY` instead of running a turn over bytes nobody received.

Dedup markers are pruned once they are older than the redelivery window, a
login flow releases its plugin whenever it ends without a channel, and chat
locks live in a bounded cache, so the `im:` state cannot grow with the traffic a
long-running process sees.
A turn that fails answers the chat with one fixed English notice instead of
staying silent, and editing a channel's policy (provider, reasoning effort,
coding access) never restarts the running plugin, because those values are read
per turn; only the enabled flag starts or stops it. Disabling a provider is
refused while a conversation preference, scheduled task, or channel still uses
it, exactly like deleting one.

`/messages`, `/events`, and `/steer` consult the same in-process
`ActiveRequestRegistry`: at most one request per session may run, and the
other two return 409 when no request is active.

### Agent plugins

Beyond channel plugins, an installed package can extend what happens inside a
conversation by registering in the `zett.agent` entry-point group. Zett owns
only the plugin class: a plugin subclasses `AgentPlugin`
instead of the runtime's `AgentExtension`, declares its tools in `tools()`, and
may implement any of the runtime's lifecycle hooks — `before_run`, `after_run`,
`on_success`, `on_error`, `before_turn`, `after_turn`, `before_model`,
`after_model`, `before_tool`, and `after_tool` — which receive the runtime's own
objects (`AgentRunContext`, `ModelRequest`, `ModelResponse`, `ToolCall`,
`ToolMessage`, `AssistantMessage`, `Exception`). Zett's single
`AgentPluginExtension` is the only runtime extension involved, so naming and
error reporting live in Zett while plugin authors read one set of types.

Two boundaries are deliberately not exposed yet, because each needs its own
Zett contract rather than a passthrough: replacing the incoming user message or
injecting into the leading system prefix (`on_state`/`on_message`, which would
rebuild the provider's cached prefix every turn), and the two middlewares
(`on_model_request`/`on_tool_call`, which change what the provider receives and
could bypass the shell approval boundary).

Two rules the adapter enforces: every plugin tool is registered as
`<plugin_id>__<tool>`, so a plugin can never shadow a built-in tool, and the
adapter is appended after every built-in extension, so a plugin cannot wrap
persistence, safety, or logging. A plugin that fails is reported as
`PluginError` naming the plugin and the hook — the run fails visibly instead of
continuing with a plugin that silently stopped working.

Discovery follows the channel rules: a broken entry point, a factory that
raises, a contract version mismatch, or an object that is not an `AgentPlugin`
is skipped with a log line while the rest still load. Plugins receive a
`PluginContext` whose KV store is namespaced (`agent:<plugin_id>:`), and their
`config` and `secrets` mappings stay empty until Zett has a settings surface for
them. `AgentPluginService` starts them with the app and stops them on shutdown.

A plugin may also register browser-facing capabilities from its optional
`register(registry)` hook: slash commands and `@` reference kinds, written
against the container's own `SlashCommandInvocation` / `AtCommandSource` /
`AtCommandItem` types. Every capability is pinned to the plugin's id as owner,
so it appears in `GET /api/agent/{id}/slash-commands` and `.../at-commands` next
to the built-in ones without the plugin touching Zett's HTTP layer, and a plugin
can never register under another owner's namespace. A plugin that only needs the
model to learn what the user pointed at passes
`zett.agent.at_command.reference_handler()` as its `@` handler — the same default
the built-in asset and artifact sources use. A failure while registering is
reported as `PluginError` naming the plugin.

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

Every run declares its session id as the provider's prompt cache key, so the
OpenAI-compatible adapters send `prompt_cache_key` and every step of one
conversation routes to the same cached prefix.

## Scheduled tasks

Scheduled tasks are persisted in `zett.db`. The Web process only creates,
updates, enables, disables, deletes, and manually queues tasks. The
`zett scheduler` process polls for due occurrences and writes `pending` run
rows. One or more independent `zett worker` processes claim those rows, change
them to `running`, execute a registered `ActionExecutor`, and write the terminal
result in `scheduled_task_runs`.

The scheduler never loads action executors and never runs model work. A slow or
crashed worker therefore cannot block new scheduling decisions. The task lease
keeps at most one run active per task: the executing worker renews it on a
heartbeat, so an expired lease means the worker stopped renewing (a crash or a
stalled process) instead of a run that is merely slow, and that run is recovered
as `interrupted`.

The Web lifespan writes the server PID, port, scheduler PIDs, and worker PIDs
to `runtime.json` below `storage_root`. `zett status` reports that file — the
server PID and port plus whether each recorded child is still alive — and
`zett stop` reads it to stop the recorded server and child processes before
removing the file. Stale or partial runtime state is cleaned before a new
server starts.

Scheduler and worker processes also run a watchdog against that file. They exit
after repeated failures when the file is missing or incomplete, when the owning
FastAPI PID is gone, or when their own PID is no longer registered. This
prevents orphaned children from continuing after an unclean Web-process crash.

The FastAPI lifespan runs a lightweight process supervisor. Scheduler and
worker processes post heartbeats to `/api/health/processes/heartbeat`; FastAPI
keeps the latest values in an in-memory registry. The supervisor keeps local
`Popen` handles, starts missing CLI processes as independent subprocesses, and
uses `Popen.poll()` as the authoritative local liveness check. It does not
execute scheduler or worker loops inside FastAPI.

Every child lifecycle transition reaches the Web log: `Started supervised
process` when a missing role is spawned, and `Stopped supervised process` (with
`killed=true|false`) for a shutdown, a dead child, or a stale heartbeat. The
reason line — `exited`, `never reported a heartbeat`, or `heartbeat is stale` —
is written immediately before the stop it explains.

A headless turn has no surface that can answer a shell approval, and the
runtime's approval wait has no timeout, so `run_headless_prompt` and the
scheduled executor mark their session `allow_all` before running: an IM
conversation created by a channel with coding enabled, and every scheduled run,
execute their commands without asking. Both headless configs must therefore also
pass `shell_approval_storage`: without it the approval middleware cannot read the
mode and waits for a browser event anyway, which freezes the turn and holds that
chat's lock.

The first executor, `agent_prompt`, always creates a new isolated Agent session
and runs a headless turn. It disables interactive `ask_user` and coding tools so
a background job never waits for browser approval. Scheduled runs never target
a user's existing session.

Both headless paths are traceable from their log alone. An IM turn writes one
line when the message arrives, one short line per streamed delta, one for the
finished turn, and one for the reply the platform accepted; a scheduled run
writes the same shape for its prompt, deltas, tool calls, and answer. Every line
carries the channel/task and event/run ids it belongs to, and text is capped by
`zett.infra.log.log_preview` (`LOG_PREVIEW_CHARS`, about one KiB) so one record
stays one line without naming bytes it never kept.

Uploads log the metadata that identifies them, never the payload: the session
asset upload records the session, asset id, type, media type, byte count, and a
capped name, the static asset upload records the asset id, media type, and byte
count, and the images a turn carries are summarized as file count and bytes.
A rejected upload logs the declared size and the limit that refused it.

Two layers cover what the browser cannot show. `RequestLogMiddleware` writes one
line per HTTP request (`Request; method=GET target=/api/agent/sessions?types,limit
status=200 bytes=812 duration_ms=13 client=127.0.0.1:64077`) without copying the
body, so streamed turns stay streamed, and it logs query parameter names rather
than values because the channel login poll carries a pairing code. Inside a
turn, `TraceLogExtension` writes `Model request`/`Model response` around each
provider step and `Tool call`/`Tool call completed` around each local tool call,
with the session id, request id, duration, and capped previews: the newest
request message (`last=user:'…'`), the answer's first characters, the tool
arguments, and the tool result. Image payloads are summarized as `<image>` or
`<image result>` instead of their bytes.

Requests that repeat on a timer would drown the access log, so
`settings.access_log_sample_rates` maps a path prefix to "log one line per this
many requests" (`ZETT_ACCESS_LOG_SAMPLE_RATES`, default `/api/health=100` for the
heartbeats every supervised process posts). A sampled path logs its first
request and every Nth one after that, and the line says how many requests it
stands for (`sampled=100`); a request that fails is always logged whatever its
rate. Everything unmatched — every user-facing endpoint — logs every request.
uvicorn's own access log is disabled in `zett start` so this sampling is the only
access log, and the counter lives in the process, so the first request after a
restart is always visible.

All process types configure SQLite with WAL, a bounded busy timeout, and short
transactions. The Web process writes `logs/zett.log`, the scheduler writes
`logs/scheduler.log`, and workers write `logs/worker.log`; a detached server
additionally keeps its console output in `logs/background.log`, because nothing
is attached to its stdout. Every record starts
with the host's local wall-clock time and its explicit `±HH:MM` offset
(`2026-09-26 17:51:03+08:00`), so a log read next to local events needs no
conversion and a log copied between machines still names its zone.

## Local data

```
~/.zettelekasten/
├── zett.db         application records: artifacts, assets, tags, providers, settings
├── agent.db        sessions, immutable raw messages, context snapshots
├── assets/         `sessions/<session-id>/` binaries and `static/` uploads
├── artifacts/      one git-tracked directory per session and LaTeX artifact project
├── skills/         user-level skills, including the built-in `zett-artifact-syntax` written at startup
├── provider.key    local key encrypting provider credentials
├── runtime.json    active server and supervised child process state
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
| `ZETT_START_TIMEOUT_SECONDS` | How long `zett start` waits for the detached server to answer, default `30` |
| `ZETT_IM_GATEWAY_DATABASE_PATH` | Imported gateway channel and route database |
| `ZETT_IM_GATEWAY_KEY_PATH` | Local key encrypting channel credentials |

Conversation limits are user settings rather than environment variables:
`max_message_images`, `max_turn_iterations`, `compaction_max_tokens`, and
`compaction_keep_recent_tokens`, read and replaced through `/api/settings`.

`zett start` owns the API and supervises scheduler and worker child processes.
It detaches by default: the command returns once the server answers on its
port, so the terminal stays free and the server survives it. `zett status`
reports what is running and exits non-zero when nothing is.

```bash
uv run --directory backend zett start                 # returns once the port answers
uv run --directory backend zett start --foreground    # block in this terminal
uv run --directory backend zett status

# Separate scheduler/worker debugging processes
uv run --directory backend zett scheduler
uv run --directory backend zett worker
```

Short forms: `-b`/`-f` for the background switch, `-p` for `--port`, and `-r`
for `--reload`. `--host` stays long-only, because `-h` reads as help.

Commands live one module per command under `zett/cli/`, and `zett.cli.main`
imports only the module it is about to run: `zett --help` reads the jump table
in `zett/cli/__init__.py` and nothing else, `zett start` is the only command
that loads uvicorn and FastAPI, and a model provider's SDK is imported by the
turn that calls it rather than by the process that starts. `zett status` and
`zett stop` answer in tens of milliseconds.

`zett install` writes the shell-facing skill into a coding agent that runs
outside Zett, so Claude Code, Codex, or another harness can drive `zett artifact`
and `zett tag` on its own. The text lives in
`zett/infra/skills/coding_agents.py`, next to the built-in skill Zett serves its
own agent, for the same reason: the CLI it documents ships in this package, so
the two cannot drift. The table there maps each agent name to the skill root its
owner documents (`~/.claude/skills`, `~/.codex/skills`), `--dir` serves a harness
this table does not know, and an existing file whose content differs is kept
until `--force` confirms replacing it — an agent owner's edits are not this
command's to discard.

Serving also exports the effective `--host`/`--port` as `ZETT_HOST`/`ZETT_PORT`,
because the reload worker and the supervised scheduler and workers re-read the
configuration from the environment: without it they heartbeat — and the reload
worker records runtime state — for the default port instead of the one this
command was actually given.

The detached child runs `zett start --foreground` in its own session, which is
why the blocking form still exists: it is what a process manager, a debugger,
or `make dev` uses. Anything the detached process prints before logging is
configured lands in `logs/background.log`, and a start that never becomes ready
reports that file with its last lines. `zett stop` stops the API and every
supervised child process. The IM gateway has no separate process to stop
because it is imported directly by Zett.

### Platform support

The process layer keeps every OS difference in
`zett/infra/scheduler/process_platform.py`: children get a POSIX session or a
Windows process group, liveness uses `kill(pid, 0)` or `GetExitCodeProcess`,
termination uses `SIGTERM`/`SIGKILL` or `TerminateProcess`, and port lookup uses
`lsof` or `netstat -ano`. Windows has no catchable termination signal, so
`zett stop` ends a child immediately there, and command-line verification is not
available. CI runs the whole suite on Linux, Windows, and macOS; the Windows
branches are additionally unit tested by forcing the platform flag.

The ZettCode TUI is POSIX-only: raw mode, `SIGWINCH`, and `add_reader` on stdin
have no Windows equivalent in the implementation. Importing ZettCode on Windows
works; starting its TUI reports that it requires a POSIX terminal.

## Development

```bash
uv sync --directory backend
uv run --directory backend zett start --foreground --reload
```

`make check` runs Ruff, the backend, agim, and zett-weixin test suites, frontend
tests, TypeScript typechecking, and the production frontend build. The
`zett-agent` runtime and its Sphinx documentation live in their own repository
and are covered by that repository's checks.

Tests create temporary SQLite databases and asset directories and remove them
afterwards; they never touch the data under `~/.zettelekasten`.

## Frontend

Routes mount the compiled Vue application from `zett/static` at `/`. The UI
reaches the backend only through typed clients in `frontend/src/api`, so a new
or changed route belongs in the same change as its client.

The conversation workspace lays out session assets, the chat, and the artifact
panel as three columns. The assets column can be hidden with the eye button in
its header, which stores the choice in `localStorage` under
`zett.assets-pane-hidden` through `frontend/src/utils/paneVisibility.ts`; the
chat header then offers a button that brings the column back. Panel visibility
is client state and never a backend flag.
