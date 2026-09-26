# Artifacts and the library

An artifact is a durable output of a conversation: something worth keeping after
the chat scrolls away. Cards, articles, images, slide decks, and LaTeX PDFs are
all artifact variants, not separate features.

| Type | Body | Notes |
| --- | --- | --- |
| Card | Markdown | `note`, `idea`, `quote`, `todo`, or `reference` |
| Article | Markdown | Long-form writing |
| Image | Generated or referenced image | Saved as a file plus metadata |
| Slides | Slide separators over Markdown | Cover page, fullscreen presentation, PDF preview |
| LaTeX PDF | A project directory | Compiled with the local toolchain; you keep the sources |

You create artifacts by talking to the Agent — ask for a card, a summary, a deck,
or a paper, and it calls its artifact tools. `New card` simply opens a fresh
conversation, because the conversation is where artifacts come from.

## Draft first, published on purpose

An artifact has two bodies: the published content and the model's working draft.

- The **first** version is written directly, because there is no user version to
  protect yet.
- Every later model update writes the **draft**. The published content is
  untouched until you save it.
- The UI, previews, search, and the diff all show the draft-first view, so you
  always review what the model proposes.
- The conversation editing surfaces stage edits as a draft too. The `Save`
  action publishes the draft, and after a save the draft and published content
  match again.

Inside a conversation, `Diff` compares the draft with the published artifact
field by field and highlights the changed lines. Nothing is published by
accident: if a conversation ends with an unsaved draft, the artifact list marks
it `unsaved draft` and the artifact keeps its previous published version.

The Agent has no save tool. Only you publish.

## Editing

- **Inline panel** — edit the body next to the conversation, then `Diff` to
  review, then `Save artifact` / `Update artifact` to publish.
- **Full editor** — the split source/preview editor, with linked scrolling for
  Markdown and a slide or PDF preview where the type has one. Opened from the
  conversation or from a library card. Editing from a conversation stages a
  draft; `⌘S` / `Ctrl+S` saves.

Editing a saved artifact from the **Library** writes the published content
directly, because that surface is the library document itself. PDFs are edited
as sources on disk rather than in the browser editor.

## LaTeX PDFs

A PDF artifact owns a project directory instead of an inline body. The Agent
maintains it as a git repository: it runs `git init` in that directory, writes a
`.gitignore` for the regenerated LaTeX build files, and commits each meaningful
change with a Conventional Commit message.

That repository is what makes a PDF artifact saveable. Publishing one is refused
with `409 Conflict` while the project is not a repository or still has
uncommitted changes, and the error names the pending paths. Once the tree is
clean the save succeeds without Zett creating a commit, so a saved PDF always
names a revision instead of a working tree. Only the project directory is
checked, so unrelated work in an enclosing repository never blocks a save.

If you edit the sources yourself, commit them; a dirty tree blocks the next
publish.

## The library

The `Artifacts` view is the library of everything published, searchable by
`⌘K` / `Ctrl+K` and filterable by type — cards, articles, slides, PDFs — and by
tag through the collections tree in the sidebar. Each card opens a reader with
edit, fullscreen preview, presentation, source-conversation, and delete actions.

Cards are draggable: drop one on a tag in the collections tree to tag it.

Search and listings show bounded previews rather than complete documents. The
full body is read only when you open it, and server-owned locations such as a PDF
`project_path` never appear in a preview.

## Tags

Tags are a recursive tree, managed from the `+` next to `Collections`. Tag paths
are normalized, missing ancestors are created as you go, and deleting a tag
cleans up its artifact links.

The Agent can suggest tags while it works, but a suggestion stays a proposal
until you save the artifact — the tag is only applied when the save confirms it.

## Syntax rules live in a skill

Every artifact body follows one Markdown dialect: card sections, figure and
cover blocks, HTML pages, and slide separators. Those rules are not baked into
the tool descriptions. They live in the built-in `zett-artifact-syntax` skill,
which Zett writes to `~/.zettelekasten/skills/zett-artifact-syntax/SKILL.md` at
startup when the file is missing, and the artifact tools tell the model to read
it before writing a body.

Because it is an ordinary skill file, you can edit it — a startup never
overwrites a file that already exists. A new syntax rule belongs there, not in a
tool description.
