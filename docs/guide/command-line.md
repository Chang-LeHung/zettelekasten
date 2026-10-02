# The command line

The `zett` command starts and stops Zett, and it can also add things to your
library from a terminal, a script, or another coding agent. Run `zett --help`
for the list of commands, or `zett <command> --help` for one command's options.

## Start, check, and stop

```bash
zett start      # start Zett in the background and return to the shell
zett status     # is it running, and where
zett stop       # stop it
```

`zett start` prints the address to open, usually `http://127.0.0.1:6280`, and
the path of its console log:

```text
Zett is running in the background; pid=48213
http://127.0.0.1:6280
Console log: /Users/you/.zettelekasten/logs/background.log
```

| Option | What it does |
| --- | --- |
| `--host ADDRESS` | Listen on another address. The default keeps Zett on this computer. |
| `-p`, `--port PORT` | Use another port (default `6280`). |
| `-f`, `--foreground` | Keep Zett attached to this terminal, with its logs on screen. Stop it with `Ctrl+C`. |
| `-b`, `--background` | Detach and return to the shell. This is the default. |

`zett status` lists the parts of Zett that keep working while no browser is
open. All three should read `running`:

```text
Zett is running
  url:      http://127.0.0.1:6280
  server:   pid=48213 running
  started:  2026-10-01T09:12:44+08:00
  scheduler: pid=48220 running
  worker:    pid=48221 running
```

If one of them is not running, run `zett stop` and then `zett start`. When Zett
is not running at all, `zett status` says so and exits with a non-zero status,
which makes it usable in a script.

::: tip Leave Zett on this computer
Your library has no login screen. Keep the default address unless you know
who else can reach the port you open.
:::

## Add to the library

`zett artifact` creates cards, articles, and slide decks straight in your
library, without a conversation. Zett has to be running.

```bash
# A card from flags
zett artifact create --type card --title "Local-first beats sync" \
  --body "Your notes should work on a plane." --source cli

# A longer body from a file, or piped in with -
zett artifact create --type article --title "Reading notes" --body-file notes.md --source cli
cat notes.md | zett artifact create --type article --title "Reading notes" --body - --source cli

# A slide deck: separate slides with a line that holds only ---
zett artifact create --type slides --title "Ten minutes on local-first" \
  --body-file talk.md --source cli
```

The command prints the new item's id. Add `--json` to print the whole item
instead.

| Option | What it does |
| --- | --- |
| `--type` | `card`, `article`, or `slides`. Required. |
| `--title` | The title. |
| `--body`, `--body-file` | The Markdown body, from the command line or a file; `-` reads from standard input. |
| `--summary` | A short summary, for cards. |
| `--subtitle` | A subtitle, for articles and slides. |
| `--content`, `--content-file` | Every field at once, as JSON, when a flag cannot name one. |
| `--raw-content` | The original text the item was made from, kept for reference. |
| `--status` | `saved` (the default) puts it in the library; `draft` keeps it unpublished. |
| `--source` | Who created it, for example `cli` or `cron:nightly`. Required. |
| `--metadata KEY=VALUE` | Extra labels; repeat the option for more than one. |

`--source` is required because an item created here has no conversation to
show where it came from. Name the script or tool that made it, so you can tell
later.

To choose a card's kind, pass the fields as JSON. A card is a `note`, `idea`,
`quote`, `todo`, or `reference`:

```bash
zett artifact create --type card --source cli --content '{
  "title": "Local-first beats sync",
  "content": "Your notes should work on a plane.",
  "card_type": "idea"
}'
```

Read, list, and delete what you created:

```bash
zett artifact list                 # newest first: id, type, status, title
zett artifact list -q sync --limit 50
zett artifact get <id>             # the whole item
zett artifact delete <id>
```

`zett artifact list` and `zett artifact delete` cover items created from the
command line and other integrations. An artifact made in a conversation is
deleted from that conversation or from its reader in the library.

Images and LaTeX PDFs cannot be created here yet; ask the Agent for those.

## Organize with tags

`zett tag` works on the same collections you see in the sidebar. A tag is a
path such as `Engineering/Python`; using a path that does not exist yet creates
it, together with any missing parent.

```bash
zett tag list                                  # the collection tree
zett tag create Engineering/Python --description "Python notes"
zett tag update <tag-id> --path Engineering/Python/Async
zett tag delete <tag-id> --recursive --force

zett tag add <artifact-id> Engineering/Python Ideas     # keeps the tags it has
zett tag remove <artifact-id> Ideas
zett tag set <artifact-id> Projects/Zett                # replaces every tag
zett tag set <artifact-id> --clear                      # removes every tag
```

Each line of `zett tag list` reads `path  direct/total  id`. **direct** counts
the items tagged exactly there, and **total** adds everything tagged further
down the tree, so a parent whose only item sits in a child reads `0/1`.

- `update` renames, moves, or restyles a tag. A tag with children cannot be
  renamed or moved.
- `delete` refuses a tag that has children or is still in use; `--recursive`
  also deletes its children, and `--force` removes it from the items that carry
  it.
- `remove` only accepts a path that already exists.
- Only saved items carry tags, so a `--status draft` item cannot be tagged.

Static Assets keep a collection tree of their own. Add `--asset` to `list`,
`create`, `add`, `remove`, or `set` to work on that tree and on asset ids:

```bash
zett tag list --asset
zett tag add --asset <asset-id> Papers/CRDT
```

The same path in the two trees is two different collections.

## Let a coding agent use Zett

`zett install` teaches a coding agent such as Claude Code or Codex to save its
results to your library. It writes one skill file where that agent looks for
skills; after that you can say "save this summary to Zett as an article" and the
agent runs the commands above on its own.

```bash
zett install --list      # the agents it knows
zett install claude      # writes ~/.claude/skills/zett-cli/SKILL.md
zett install codex       # writes ~/.codex/skills/zett-cli/SKILL.md
zett install --dir ~/.my-agent/skills   # any other agent, by its skills folder
```

Installing works whether or not Zett is running; the agent needs a running Zett
when it uses the skill. Running the command again updates the file. If you have
edited the installed file, Zett keeps your version and tells you so; add
`--force` to replace it.

## Save from ChatGPT

The ChatGPT integration in `zett3rd/zettelekasten-chatgpt` lets ChatGPT save a
card or an article to your library, file it under your collections, and later
find, read, or edit it. It runs on your computer next to Zett.

1. Start Zett with `zett start`.
2. In `zett3rd/zettelekasten-chatgpt`, run:

   ```bash
   npm ci
   npm run build
   ZETT_BASE_URL=http://127.0.0.1:6280 npm run dev
   ```

   It listens on port `6281`; set `ZETT_MCP_PORT` to change it.
3. In ChatGPT or Codex developer mode, connect `http://127.0.0.1:6281/mcp`
   through a [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

ChatGPT sees only published cards and articles, never your drafts. Asking it to
save the same thing twice creates two items. An edit is refused when the item
changed since ChatGPT read it or has an unsaved draft, so reopen it and try
again. Nothing from the ChatGPT conversation itself is stored in Zett.

::: warning Keep it private
The integration has no password. Never expose its address, or Zett's, on a
public tunnel or proxy.
:::
