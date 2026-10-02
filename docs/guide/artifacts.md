# Artifacts and the library

An artifact is something worth coming back to after the conversation has
scrolled away. Ask Zett for a concise card, a longer article, an image, a slide
deck, or a LaTeX paper; then decide which version belongs in your library.

| Type | What it is | Good to know |
| --- | --- | --- |
| **Card** | A short Markdown note | Marked as a note, idea, quote, todo, or reference |
| **Article** | Long-form Markdown writing | Title, optional subtitle, and body |
| **Image** | A picture with a caption | From a web link or a file in the conversation |
| **Slides** | A Markdown slide deck | Cover page, fullscreen presentation, and PDF preview |
| **LaTeX PDF** | A compiled paper | Built with the LaTeX tools on your computer; you keep the sources |

## Make one

Ask for it in a [conversation](conversations.md): “Make a card from this idea”,
“Turn these notes into a ten-slide deck for a team lunch talk”, or “Draft a
LaTeX paper about note sync, with citations.” **New card** in the library opens
a fresh conversation for exactly that.

You can be specific about the shape: the kind of card, the number of slides,
the tags you want, or the section a paper should have. You can also ask for
changes afterwards (“shorter”, “split slide three”, “cite the second source”),
and Zett edits the same artifact instead of starting a new one.

## Draft first, published on purpose

Nothing reaches your library until you say so.

1. A new artifact appears in the conversation as a **draft**.
2. **Save** publishes it to the library.
3. When Zett changes it later, the change waits as a draft beside the published
   version. The library keeps showing the published one.
4. **Diff** compares the two field by field and highlights what changed.
   **Update** publishes the change.

A conversation with unpublished changes is marked **unsaved draft**, and
**Save all** in the workspace publishes every pending artifact at once. If one
of them cannot be saved, the rest still are, and Zett tells you which one
failed and why.

Zett itself cannot publish anything. Only you save.

## Edit

- **In the conversation.** Select an artifact to preview it, then use **Edit**
  on its row. Use **Diff** to check your changes and **Save** or **Update** to
  publish them. Images and PDFs have their own controls.
- **In the full editor.** Open it from the conversation or from a library card
  for a side-by-side source and preview. The two panes scroll together for
  Markdown, and slides and PDFs show their rendered pages. Press **⌘S** to save.
- **From the library.** Editing a card you opened from the library changes the
  published version directly.

## LaTeX papers

A paper is a small LaTeX project rather than a single text field. Zett writes
the sources, compiles them with the LaTeX tools installed on your computer, and
shows the resulting PDF. It keeps the project under version control and records
each change, so every saved PDF matches an exact set of sources.

If you edit the sources yourself, commit your changes before saving. Zett only
saves a paper whose sources are fully committed; otherwise it lists the files
that still have changes so you know what to commit.

## Images

An image comes either from a web link or from a file in this conversation. To
use your own picture, attach it in the conversation and ask Zett to make an
image artifact from it. Zett will not save an image whose file is missing.

Give every image a caption and alt text in its editor, so readers and screen
readers know what it shows.

## The library

**Artifacts** in the sidebar opens your library: everything you have published.

- Press **⌘K** (**Ctrl+K** on Windows and Linux) to search titles and contents.
- Filter by type: **All**, **Cards**, **Articles**, **Slides**, or **PDFs**.
- Choose a collection in the sidebar to show only what is tagged there.
- Open a card for the full reader, with **Edit**, fullscreen preview,
  **Present** for slides, a link back to the conversation it came from, and
  **Delete**.

## Tags

Tags form a tree, such as `Technology/Python`, shown as **Collections** in the
sidebar.

- Add one with **+** next to **Collections**. Typing a path creates any missing
  parent as well.
- Drag a card from the library onto a collection to tag it.
- Ask Zett to tag what it makes. Its suggestions are only applied when you save
  the artifact, and you can uncheck one in the editor before saving.
- Saving never removes tags you added yourself.
- Deleting a tag removes it from every item that carries it.

Static assets have their own collections; see [Assets](assets.md#classify-a-file).

## Add from outside a conversation

Scripts, ChatGPT, and coding agents such as Claude Code or Codex can add cards,
articles, and slides straight to your library. See
[The command line](command-line.md#add-to-the-library).

## Teach Zett your style

Zett follows a writing guide for every artifact: how cards are sectioned, how
figures and cover pages are written, and how slides are separated. The guide is
an ordinary file at
`~/.zettelekasten/skills/zett-artifact-syntax/SKILL.md`, and you can edit it to
change how Zett writes. Zett creates it the first time it starts and never
overwrites your edits; delete the file to get the original back on the next
start.
