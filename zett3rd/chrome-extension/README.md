# Zettelekasten

The Zettelekasten Chrome extension embeds a conversation in the webpage you
are viewing. It reads that page, talks to your local Zett agent about it, and
lets you save artifacts into your library.

It is a Manifest V3 extension written with the same stack as the browser app —
Vue 3, TypeScript, Vite — and it talks to the same HTTP API, so it needs nothing
from Zett except a running server. Chrome loads the built directory, so the
extension is built with `npm run build` before it is loaded.

It wears the app's own product icon: `frontend/public/logo.png` is copied into
`public/` and pre-rendered to `public/icons/icon{16,32,48,128}.png` for the
toolbar button and `chrome://extensions` card, while the panel header and the
welcome screen show the same logo.

## Install

1. Start Zett: `zett start` (the default address is `http://127.0.0.1:6280`).
2. Build the panel:

   ```bash
   npm --prefix zett3rd/chrome-extension install
   npm --prefix zett3rd/chrome-extension run build
   ```

3. Open `chrome://extensions`, turn on **Developer mode**, and choose **Load
   unpacked**.
4. Pick `zett3rd/chrome-extension/dist` — the built directory, not the source
   one.
5. Open an HTTP(S) webpage and click the Zett icon in the toolbar. A panel
   appears inside that page, at the right edge. Click the icon or the panel's
   close button to hide it; click the icon again to restore that page's chat.
   Drag the thin strip at the top to move it; drag any of its four corners to
   enlarge or shrink it. Its default size leaves the webpage visible.

After a change, run `npm run build` again and press the reload button on the
extension's card.

If the server runs elsewhere, open the panel's **Settings** and change the
address.

The extension asks for access to all sites because reading the page you are on
is its whole job: `chrome.scripting` needs that access to hand the panel a
page's text. What it *sends* is what you include — the page text travels only to
the server address you configured, and only when you send a message.

## What the panel does

| Control | What happens |
| --- | --- |
| Page context | Reads the page that owns this panel (bounded to 20 000 characters). Each tab and URL has its own conversation; navigating to a new page switches to that page's conversation, and returning restores its previous chat. |
| Composer picks | Compact connection/model and thinking controls stay under the input. Both choices stick across turns, and their menus close as soon as the pointer leaves the trigger or the menu. |
| More options | The `•••` button holds connection retry/disconnect, Save all and usage metrics (cache, tokens, context percentage), leaving the composer uncluttered. Hovering or clicking it shows the menu, and leaving the trigger or the menu closes it. |
| **Send** | Enter sends and clears the input immediately; Shift + Enter starts a new line. While a turn is running, Enter queues the message above the composer instead of interrupting it. The answer streams in and renders as Markdown. When the browser bridge is connected, the Agent can read the page through `get_browser_page`; otherwise a bounded page excerpt accompanies the message. |
| **Queued follow-ups** | Messages queued during a run list above the composer. **Steer** injects one into the running turn now — the thread shows it and marks it until the run answers — while **×** drops it. Anything left queued is sent one by one as the next turns when the current one ends. |
| **Agent question** | When the Agent calls `ask_user`, the run suspends until the panel answers it. The card shows the question, its options (one or several), an **Other** text field and image attachments; **Continue** posts the matching `ask_user_response`, and further questions wait their turn. Only Stop ends the run without an answer. |
| **Stop** | While running, Send becomes a square Stop button. It aborts the current Agent stream, drops queued follow-ups and disconnects page control, cancelling pending DOM approval. Partial output and any next-message draft stay visible; send a new message to continue. Applied edits are not rolled back. |
| Execution details | Uses the web app's `AgentExecution` and `ToolResult` components. Expand thinking, individual tools, or a context-compaction row (state, summary, compressed and kept ranges) to inspect what happened. Details open while running and collapse on completion unless you choose otherwise. |
| **Artifact card** | When the agent creates or changes an artifact, its card appears in the thread — title, kind, and whether it is still an unsaved draft — with a **Save** button that publishes it. |
| **Save all** | Publishes every artifact of this conversation that still has something to save, and says how many it saved. |
| **New chat** | Starts a fresh conversation for this page only, leaving the conversations of other tabs and pages unchanged. |
| Floating panel | Starts at 440px wide and up to 90% of the viewport height. Drag the top strip to move it; drag any corner to resize it. Invisible corner zones keep the page's own content unobstructed. |
| Page connection | Connects automatically when the page's conversation opens. **Disconnect page** turns off browser tools for this panel; **Connect page** retries a failed or deliberately disconnected connection. |
| **Allow once / Reject** | Reviews each DOM edit's selector, action and value before applying it. No model-authored code executes. |

The server address and each tab/URL-to-session mapping persist in
`chrome.storage.local`; the panel loads messages from the server when reopened.
Restored and streaming turns scroll the conversation to the latest output.
The WebSocket token stays only in memory. Two tabs open to the same URL have
separate conversations, and in-page `#` anchors share one conversation.

Creating and classifying are the conversation's job: ask the agent to file the
page ("save this page as a card under Reading/Web") and it uses its own artifact
and tagging tools. The panel shows the result and lets you publish it; the
artifact and static asset libraries keep separate collection trees, and the
agent knows which one it is writing to.

## Endpoints it calls

| Call | Purpose |
| --- | --- |
| `GET /api/health` | Is the server there? |
| `GET /api/settings` | Read the configured context compaction threshold |
| `POST /api/agent/start` | Create a conversation for this tab and page |
| `GET /api/agent/sessions/{id}` | Restore its persisted messages when reopening the embedded panel |
| `GET /api/ai/providers` | Find an enabled model |
| `POST /api/agent/{id}/messages` | Run one turn and stream its events |
| `GET /api/agent/{id}/artifacts` | List the conversation's artifacts, to show what still needs saving |
| `POST /api/agent/{id}/artifacts/{artifact_id}/save` | Publish one artifact's pending draft: the card's **Save**, and each of **Save all** |
| `WS /api/agent/{id}/browser` | Ephemeral session-bound browser commands and results |

Answers are rendered with the same pieces the app uses — `markdown-it`,
`highlight.js` for fenced code — and the result is sanitized with DOMPurify
before it touches the DOM: a model answer is untrusted text, and this page holds
`chrome.*` APIs.

The panel imports presentation components and timeline types from `frontend/src`;
they are bundled into the extension, not fetched from the running web app. Both
hosts use the same tool rows and styles. Tool events are correlated by call ID,
including parallel calls that finish out of order, and a failed stream keeps its
partial answer and execution details available for inspection.

The composer grows with the panel but the model/effort controls keep bounded
widths. Their menus are anchored to the buttons, not stretched across the panel,
and they close as soon as the pointer leaves the trigger or the menu. Each menu
sits flush against its trigger, so the pointer never crosses a gap on the way
in. Narrow panels wrap the controls and metrics without hiding connection names.

## Webpage control

Reload the extension after upgrading. Open an HTTP(S) page and click the toolbar
icon. The content script mounts an extension-origin iframe inside a closed
shadow root; the page's scripts cannot access the conversation UI. The frame
automatically connects to this document over WebSocket. Its bundled content
script reads and updates the top document; no debugger permission or arbitrary
JavaScript execution is needed. The Agent gets
`get_browser_page` (bounded text, control descriptions and CSS selectors, optionally
limited to one subtree) and `update_browser_dom`. A tool call to fill a field is:

```json
{
  "change": {
    "action": "fill",
    "selector": "input[name=\"name\"]",
    "value": "Ada",
    "description": "Fill the name field"
  }
}
```

Available actions are `set_text` (replace a plain text element without children),
`fill` (text-like inputs/textareas or `contenteditable="true"` editors such as
ProseMirror), `select` (an existing enabled option),
and `set_checked` (a checkbox with a boolean value). Selectors must match exactly
one visible supported element. Password/file inputs, disabled/read-only controls,
arbitrary HTML and attributes, click, submit, navigation and executable source
are deliberately unsupported in `update_browser_dom`. The separate
`interact_with_browser` tool supports a reviewed click, double-click, hover,
focus, scroll, limited key press, or drag/drop. It accepts one target selector
and only the parameters appropriate for that action. Every potentially
mutating interaction waits for **Allow once**. These are synthetic DOM events:
some sites require trusted pointer or keyboard events and will ignore them.
The receipt means "dispatched", not "the website accepted it"; the Agent must
read the page again before claiming the intended effect occurred. Arbitrary
JavaScript remains unavailable.
For a rich text editor, `fill` selects the editor contents and sends a browser
editing `insertText` command. It does not replace `innerHTML` or execute code,
and it fails if the editor refuses input. Page snapshots expose supported
contenteditable selectors, so the Agent can discover one before editing.

The panel shows the exact edit and purpose and waits for **Allow once**. Rejecting,
expired approval, navigation, or disconnection prevents pending work from being
replayed. Calls bind to the connected tab and document, not whatever tab happens
to be active when the result returns. Only the top frame is supported initially.
The socket and token are never persisted. Navigating to another page opens its
own embedded conversation and connection automatically; if a connection fails,
the panel offers **Connect page** to retry. Stopping a turn disconnects page
control until you reconnect it.

The panel sends only data through `chrome.tabs.sendMessage`, pinned to the
injected content script's `documentId` and a connection nonce. Its listener
validates the sender, payload, expiry and command ID before every operation.
Content-script replies have a ten-second client wait limit and results are
limited to 64 KB. Field edits dispatch input/change events for controlled forms,
which may trigger the website's own autosave. A timeout does not undo edits;
inspect before retrying. Normal Web/CLI/headless turns never register these tools.

This is a local-first API, not a remote authentication system. Keep the backend
on loopback; remote operation needs an authenticated TLS proxy (HTTPS/WSS).

## Two things worth knowing

**Turns run with shell approval allowed.** The panel cannot answer the runtime's
approval prompt, and that prompt waits without a timeout, so asking for review
here would freeze the turn and hold the conversation's lock. Use the desktop UI
when you want to review each command; the panel is for reading, asking, and
filing.

**Reading is best effort.** Chrome refuses extension access to `chrome://`,
`chrome-extension://`, `about:`, and the Web Store pages, and the panel says so
instead of showing an empty page. Pages that render text only after scrolling
give the panel what they had rendered at that moment.

## Tests

The pure parts — the SSE parser and the page-text helpers — run under the same
Vitest the browser app uses, and `vue-tsc` type-checks the panel against the API
shapes it reads:

```bash
npm --prefix zett3rd/chrome-extension run test
npm --prefix zett3rd/chrome-extension run typecheck
```

All three steps, plus the build, run from the repository's `make check`.
