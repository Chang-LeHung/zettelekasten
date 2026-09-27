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

## Images

An image artifact is either external or local. An external one carries a
`source_url`; a local one carries the object key of a file this conversation
uploaded, and the pane renders it through `/api/files/<key>`.

The Agent gets that key by uploading a file it wrote. It generates or downloads
the image with the shell — under this conversation's own directory, which the
session-files message names — and then calls its `upload_asset` tool with that
absolute path. The tool stores the file as a session asset and answers with only
what the next step needs: the file name, its media type, the `storage_path` to
hand to the artifact, and the URL this site serves it from. Bytes never travel
through the model's arguments, so a large PNG costs nothing in context. A
relative path is refused instead of guessed: it would mean the shell's working
directory to whoever wrote the file and this conversation's directory here, and
reading the wrong file is a leak rather than a typo.

Zett refuses an image artifact whose local path it does not own or cannot find:
the path has to be a relative object key below `assets/sessions/<session>/`, and
the file has to exist, so a typo can never be published as a permanently broken
image. The artifact editor shows the local path read-only next to the external
URL, because the key belongs to the upload rather than to the edit.

## The library

The `Artifacts` view is the library of everything published, searchable by
`⌘K` / `Ctrl+K` and filterable by type — cards, articles, slides, PDFs — and by
tag through the collections tree in the sidebar. Each card opens a reader with
edit, fullscreen preview, presentation, source-conversation, and delete actions.

Cards are draggable: drop one on a tag in the collections tree to tag it.

The command line edits the same taxonomy:

```bash
zett tag list                                   # the tag tree: path, direct/total counts, id
zett tag create Engineering/Python --description "Python notes"
zett tag update <tag-id> --path Engineering/Python/Async
zett tag delete <tag-id> --recursive --force    # explicit flags for children and assignments

zett tag add <artifact-id> Engineering/Python   # keeps the tags it already carries
zett tag remove <artifact-id> Engineering/Python
zett tag set <artifact-id> Projects/Zett        # replaces the whole set; --clear empties it
```

`zett tag add`/`remove` name tags by path and resolve them against the tree, then
attach or detach exactly that one assignment; `zett tag set` is the editor's
whole-set replace. Only saved artifacts carry tags. Assigning a path the
taxonomy does not have yet creates it — `add` and `set` do that, while `remove`
refuses a path that does not exist instead of inventing a tag to detach.

Every `zett tag list` line is `path  direct/total  id`. `direct` counts the
artifacts tagged exactly there, and `total` adds the ones tagged in its
descendants (an artifact that carries both a tag and its child counts once), so
a parent reads `0/1` when the only assignment sits on its child — the same
numbers the collections tree shows in the library.

Search and listings show bounded previews rather than complete documents. The
full body is read only when you open it, and server-owned locations such as a PDF
`project_path` never appear in a preview.

## Tags

Tags are a recursive tree, managed from the `+` next to `Collections`. Tag paths
are normalized, missing ancestors are created as you go, and deleting a tag
cleans up its artifact links.

The Agent can suggest tags while it works, but a suggestion stays a proposal
until you save the artifact — the tag is only applied when the save confirms it.
Saving never resets the rest of the taxonomy: a tag the Agent set explicitly,
one you attached from the Library, or one added with `zett tag add` stays put.
Unchecking a suggestion in the conversation editor removes that suggestion, and
removing any other tag is its own action (`zett tag remove`, `zett tag set
--clear`, or detaching it in the Library's tag editor).

## Creating artifacts without a conversation

Artifacts are owned by a conversation, and a shell or a script has none, so the
server keeps one hidden library session for them. `POST /api/artifacts` creates
the artifact there, `GET /api/artifacts/{artifact_id}` reads it back, and the
library view lists it like any other published artifact; the conversation
sidebar never shows that session as a chat.

The command line uses those endpoints:

```bash
# A card from flags, or a longer body piped in
zett artifact create --type card --title "Idea" --body "One sentence." --source cli
cat notes.md | zett artifact create --type article --title "Notes" --body-file - --source cron:nightly

# Slides, or a field the flags cannot name, as typed JSON
zett artifact create --type slides --title "Deck" --body "# One\n---\n# Two" --source cli
zett artifact create --type card --content '{"title": "Idea", "content": "Body", "card_type": "structure"}' --source cli

zett artifact list --query notes     # newest first: id, type, status, title
zett artifact get <artifact-id>      # the stored artifact as JSON
zett artifact delete <artifact-id>   # only artifacts that belong to no conversation
```

`--source` is required and recorded as `metadata.source`: it names who creates
the artifact, because an artifact with no conversation has nothing else to
attribute it to. The server refuses a blank one, so a script that forgets to say
who it is fails instead of leaving an unattributable artifact behind.

`zett artifact delete` only deletes artifacts from the library, and it removes
the tag assignments they carried with them. An artifact that belongs to a
conversation is refused (`403`) and left untouched — delete that one in its
conversation — so a shell can never remove a chat's artifact by naming its id.
The same rule holds for the API: `DELETE /api/artifacts/{artifact_id}` decides by
ownership, not by who calls it.

## Teaching another coding agent to use Zett

The commands above are what an agent needs, and `zett install` writes them into
the agent's own skill directory as one `SKILL.md`, so Claude Code, Codex, or
another harness can create artifacts and classify them without being told how
every time:

```bash
zett install --list            # the agents this knows, and the root each reads
zett install claude            # ~/.claude/skills/zett-cli/SKILL.md
zett install codex             # ~/.codex/skills/zett-cli/SKILL.md
zett install --dir ~/.myharness/skills   # anything else, by its skill root
```

The skill text ships inside Zett, so it always describes the flags the installed
CLI actually accepts. Installation only writes files — it never talks to the
server, and Zett does not have to be running for it. A skill file that already
exists with different content is kept until you pass `--force`, because that copy
may be yours.

`zett artifact` talks HTTP to the server recorded in `runtime.json`; it needs a
running `zett start` and refuses to run against nothing. It creates cards,
articles, and slides today: an image artifact has to point at an asset and a
LaTeX artifact needs a server-managed project directory, so both wait for their
own interface instead of asking a shell for a title and a body.

Every value is checked before anything is sent: a blank, oversized,
control-character, or malformed input fails as a usage error, a file or pipe is
read only up to the limit it would be refused for, and typed JSON content names
the keys the stored model accepts instead of letting a typo silently drop a
field. The same holds for `zett tag`: a path with an empty segment, an id with
whitespace, or an oversized description never reaches the server.

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
