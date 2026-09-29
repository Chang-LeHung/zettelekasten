# Conversations

One conversation is one Agent session. The Agent reads your message, calls its
tools, and writes back while it works — assistant text, reasoning, tool calls,
tool arguments, and tool results all stream into the page in timeline order.
Nothing is generated off-screen and revealed at the end.

## Start a conversation

`Start a new session` in the sidebar, or `New card` on an empty library, opens a
fresh conversation. Sessions are stored by `zett-agent` as an immutable raw log
plus versioned context snapshots, so the transcript you see is a replay of that
log rather than a mutable document.

The sidebar lists normal conversations only. Scheduled runs and channel
conversations keep their own entries under
[Scheduled tasks](scheduled-tasks.md) and [Channels](channels.md).

Hover a conversation for its actions: rename it in place, or delete it. Deleting
a conversation removes its messages, session assets, message uploads, artifacts,
and artifact project directories.

## The composer

| Control | What it does |
| --- | --- |
| Model | Provider used for the next message; the choice is remembered per conversation |
| Thinking | Reasoning effort for the next message: Off, Low, Medium, High |
| Shell | `Review` asks you before a shell command runs, `Allow all` runs it directly |
| Enter | Sends the message, or queues it when a turn is already running |
| `/` | Slash commands registered by the container and its plugins |
| `@` | Session assets and artifacts of this conversation |

Attach material by pasting or dropping it on the message box. Pasted images
travel inline with the message and are rendered in the transcript, so the model
can look at them through vision; the same bytes are also written into the
session's upload directory, which is how the model reaches them with a shell
command, `view_image`, or a LaTeX build. Other files are stored the same way and
referenced by path. `Max asset file size` in [Settings](settings.md) bounds what
you can attach.

## While a turn is running

Keep typing. Pressing Enter while the Agent is working adds the message to the
queue instead of interrupting it. From the queue you can reorder items, drop
them, or steer one into the running request, which injects it immediately —
useful for "stop, use this file instead". Slash commands and `@` references
cannot be steered, because they change how a turn starts.

The Agent may stop and ask you a question with a small set of choices; the turn
waits until you answer it, and any questions that arrive behind it are queued.

## Shell approval

In `Review` mode the Agent's shell commands pause on an approval card that shows
the exact command and its timeout. `Execute` runs it once, `Abort` refuses it,
and always allowing applies to that exact command only. The mode is stored per
session and can be changed before each message.

Scheduled runs and channel conversations are headless: no browser is watching,
so they run their shell commands without asking. That is why they should only
use providers and prompts you are comfortable running unattended.

## Trace and usage

The `Workspace` / `Trace` switch in the header changes how the same conversation
is shown:

- `Workspace` is the chat itself, with artifact and asset panels beside it.
- `Trace` renders every request and response of every turn: the model, reasoning
  effort, tool calls with arguments, tool results, durations, and token usage.

A turn separator marks each round trip and can be clicked to jump to the user
message that started it. Per turn you can read input, output, reasoning, cache
read and write tokens, cache hit rate, and speed; the context ring shows how
full the context is and where the next compaction will happen.

When the context approaches the configured threshold the runtime compacts older
turns into a checkpoint while keeping a recent verbatim tail. The raw log and
every earlier snapshot stay on disk, so nothing is lost by compacting.

## What the Agent can reach

### Chrome extension

The Chrome extension embeds a panel on the right edge of the webpage when you
click its toolbar icon; it does not use Chrome's native side panel. Each tab
and page URL owns a separate conversation. Closing and reopening the panel
restores that page's messages and pending artifacts. The embedded panel reuses
the web conversation's execution details and model
controls. Model choices show the connection name so two providers with the same
model are distinguishable. Cache hit rate uses the real model usage counters;
the context ring shows the latest input/output tokens relative to the configured
compaction threshold, not the provider's advertised maximum context window.
Hover or focus the ring to inspect the percentage and context composition.

To let the Agent fill a webpage, click the extension's toolbar icon on that
page. The embedded panel automatically connects the content script to its
session, without debugger permission. Send a request
such as “Fill this form from these details, but do not submit it.” The Agent can
read the connected page and propose a structured DOM edit; review the selector,
action and value, then choose **Allow once** or **Reject**. It can replace plain
text, fill text fields, select a dropdown option, or set a checkbox. Arbitrary
JavaScript and HTML injection are not available. `interact_with_browser` can
request a reviewed click, hover, focus, scroll, bounded key press or drag/drop.
Clicking a submit button can have real side effects and requires explicit user
intent and approval. Synthetic events may be ignored by sites that require
trusted input; the Agent must read the page again to verify the result.

Only the connected top-level document is controlled. Switching tabs keeps each
tab's embedded panel independent. Navigating to a different URL opens that
page's conversation; returning restores the earlier one. Closing the panel
disconnects its live tools without deleting its history. A failed connection
can be retried with **Connect page**; failed edits are not replayed. Field changes
send input/change events and may trigger the website's
own autosave. A timeout cannot roll back edits that already happened.
Ordinary web conversations do not receive these browser tools.

The webpage panel is a movable, resizable floating window rather than a
full-height overlay: drag its top strip to reposition it, or any corner to
resize it. Its pickers and `•••` menu close as soon as the pointer leaves the
trigger or the menu, and hovering `•••` shows it. The composer keeps model and
effort visible; the menu holds browser connection, Save all and token
statistics (cache, tokens, generation speed, and the context share of the
compaction threshold). Hovering the **Context** row there shows the composition
pie and the share each part takes (system, tool prompt, tool output, user,
assistant). Answers render with the web thread's Markdown, including
the same fenced-code toolbar, copy button and language set. When a page
conversation is restored or an answer
streams, the chat follows the newest output. `fill` also supports
`contenteditable="true"` editors (including ProseMirror-style editors with
nested paragraphs), using the browser's text-editing path; it does not submit
the prompt or overwrite HTML.

While the extension is generating, the Send button becomes **Stop**. Enter
queues a follow-up above the composer instead: **Steer** injects it into the
running turn — the thread shows it and marks it until the run answers — and
**×** drops it, while whatever stays queued is sent one by one as the next
turns. Stop cancels the current turn, drops the queue and clears pending
webpage approvals while preserving partial output and your next-message draft;
Stop is cancellation, not suspension of an executing tool. Edits already
applied to a page are not undone, and page control must be explicitly
reconnected after Stop.

When the Agent asks a question (`ask_user`), the turn suspends until the panel
answers it: the card offers the question's options, an **Other** text field and
image attachments, and **Continue** resumes the run with that answer. Further
questions wait behind the current one, and only **Stop** ends the run without
an answer.

### Application tools

Inside a conversation the Agent's tools cover the whole local application:

- artifacts and library search/tagging (`create_artifact`, `update_artifact`, `query_artifacts`)
- session assets (`create_asset`, `get_asset`, `update_asset`, `delete_asset`, `list_assets`)
- tags (`list_tags`, `create_tag`)
- scheduled tasks (`create_scheduled_task` and friends)
- the provider list, so a scheduled task can name one
- files, globbing, and search inside the session workspace
- skills, MCP servers, and any installed [plugin](../plugins/index.md) tool

Tools the model does not have loaded yet can be found through search when the
provider supports it, so a long tool list does not have to live in every
request.
