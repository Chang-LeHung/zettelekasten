# Conversations

A conversation is where things get made. Start with a question, a rough note,
or a file; Zett answers as it works, and the useful part becomes an
[artifact](artifacts.md) you review and keep. Reading in Chrome? You can do the
same [beside the page](chrome-extension.md).

## Start a conversation

1. Choose **Start a new session** in the sidebar, or **New card** in the
   library.
2. Pick a model in the composer. If the list is empty, add a provider in
   [Settings](settings.md#ai-providers) first.
3. Ask for a small, specific result: “Turn these notes into one concise card,
   with a title and a two-sentence summary.”

The answer streams in as Zett writes it. Anything it creates, such as a card,
an article, or a slide deck, appears in the panel beside the chat as a draft for
you to review.

The sidebar lists the conversations you started here. Runs of a
[scheduled task](scheduled-tasks.md) and chats from a [channel](channels.md)
are listed on their own pages.

Hover a conversation to rename it or delete it. Click its title to rename it in
place.

::: warning Deleting a conversation deletes what it made
Deleting a conversation removes its messages, its files, and every artifact
created in it, including the ones already saved to your library.
:::

## The composer

| Control | What it does |
| --- | --- |
| **Model** | The provider and model that answer the next message. Each conversation remembers its choice. |
| **Thinking** | How hard the model reasons before answering: **Off**, **Low**, **Medium**, or **High**. |
| **Shell** | **Review** asks you before a shell command runs; **Allow all** runs commands directly. |
| **Enter** | Sends the message, or queues it while Zett is still answering. **Shift + Enter** starts a new line. |
| `/` | Opens the list of commands for this conversation. |
| `@` | Refers to a file or artifact from this conversation. |

Paste or drop images and files onto the message box. A model that can see
images reads them directly, and Zett can open attached files while it works.
The largest upload size is set in [Settings](settings.md#limits).

Type `@` to point at something you already have here, for example “compare
@reading-list.md with @Local-first beats sync”. The menu lists this
conversation's files and artifacts.

## While Zett is answering

Keep typing. Pressing **Enter** while a turn is running adds the message to a
queue instead of interrupting. In the queue you can:

- drag a message to change the order,
- remove it, or
- choose **Steer** to hand it to the current turn right away, which is useful for
  “use the second file instead.”

A queued message that starts with `/` or uses `@` always waits for its own
turn.

Sometimes Zett needs a decision from you. It shows a question with a few
choices, plus **Other** for your own answer; pick one and choose **Continue**.
The turn waits until you answer.

## Approving shell commands

With **Shell** set to **Review**, a command Zett wants to run pauses on an
approval card that shows the exact command and how long it may run.

- **Execute** runs it once.
- **Abort** refuses it, and Zett continues without it.
- Check **Always allow this exact command** before you choose **Execute** to
  skip the question next time for that same command, in this conversation.

Each conversation keeps its own setting, and you can change it before any
message.

[Scheduled tasks](scheduled-tasks.md) and [channels](channels.md) run with no
one watching, so they run commands without asking. Use them with models and
prompts you are comfortable leaving unattended.

## The workspace

Beside the chat, the workspace collects what this conversation has produced.

- **Artifacts** are listed with a short excerpt or a thumbnail. Select one to
  preview it below the list. Drag the divider between the list and the preview
  to give either more room, or focus the divider and use the **↑** and **↓**
  keys.
- Each artifact has **Save** (or **Update**), **Edit**, and **Delete**.
  **Save all** saves every artifact with pending changes; if one cannot be
  saved, the others still are, and Zett tells you which one failed.
- Images, PDFs, and diagrams open in a larger reader. Press **Esc** to close
  it.
- **Assets** lists the files this conversation keeps for reference. See
  [Assets](assets.md).

## Trace and usage

The icon in the conversation header switches between **Workspace** and
**Trace**. Trace shows every step of every turn: the model and thinking level,
each tool Zett used with its input and result, how long each step took, and the
tokens it spent.

A separator between turns shows what the turn cost: input and output tokens,
reasoning, cache use, and speed. Click it to jump to the message that started
the turn.

The ring next to the composer shows how full the conversation's memory is. When
a long conversation gets close to the limit, Zett summarizes the older turns so
the conversation can continue. You can follow that in Trace too.

## Continue elsewhere

Use [Zett in Chrome](chrome-extension.md) to work beside a webpage, or connect
a [channel](channels.md) to talk to Zett from your phone. Each keeps its own
conversations. Whatever you make, you decide when it is published: see
[Artifacts and the library](artifacts.md).
