<p align="center">
  <img src="https://github.com/Chang-LeHung/zettelekasten/raw/main/frontend/public/logo.png" width="144" height="144" alt="Zett logo">
</p>

<h1 align="center">Zett</h1>

<p align="center">
  A local-first, AI-assisted workspace for turning fleeting thoughts, conversations, links, and assets into reusable knowledge.
</p>

<p align="center">
  <a href="https://github.com/Chang-LeHung/zettelekasten/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-476957.svg"></a>
  <img alt="Python 3.10-3.14" src="https://img.shields.io/badge/Python-3.10%20to%203.14-3776AB.svg?logo=python&logoColor=white">
  <img alt="Local-first" src="https://img.shields.io/badge/storage-local--first-476957.svg">
</p>

---

Zett is a private workspace where you think out loud with an AI assistant and
keep what matters. Catch a fleeting thought in one line before it slips away,
bring in the sources around it, and work it into something durable — a card, an
article, a slide deck, or a paper — organized, searchable, and stored on your own
machine.

No account, no cloud workspace, no telemetry. Zett runs as a single local
application that listens on `127.0.0.1` and keeps every database and file under
one directory. It talks to the model provider you configure, and to a chat
platform only when you connect one.

## What you can do

- **Think in a conversation.** Ask, refine, and iterate; the answer streams with
  its reasoning and the tools it used, so you can see how it got there.
- **Catch a fleeting thought.** Jot down the idea, a rough note, or a question
  the moment it arrives, and develop it into something durable whenever you come
  back to it.
- **Keep the good parts.** Cards, articles, images, slide decks, and LaTeX PDFs
  are built from the conversation and saved only when you say so.
- **Build a library.** Everything published is searchable and tagged with a
  nested tag tree, and every item links back to the conversation it came from.
- **Bring your sources.** Attach notes, links, images, and files to a
  conversation, or keep a global library of material you reuse everywhere.
- **Choose your models.** Configure several providers and pick the model and the
  reasoning effort for each conversation.
- **Work hands-free.** Set a prompt to run on a schedule and read the transcript
  of what it produced while you were away.
- **Talk to it from your phone.** Connect a chat platform and keep a separate
  conversation per chat, images and voice notes included.

## Install

Zett ships as one Python package — the application, the `zett` command, and the
compiled interface — so this is the whole install:

```bash
uv tool install zettelekasten   # or: pipx install zettelekasten
zett start                      # serves 127.0.0.1:6280 in the background
```

The distribution is `zettelekasten`; the command it installs is `zett`. It is
published to PyPI together with the `agim` and `zett-weixin` packages it
depends on, so one install is enough. To work from a checkout instead:

```bash
git clone https://github.com/Chang-LeHung/zettelekasten
cd zettelekasten
make install             # builds the interface and installs the `zett` command
zett start               # serves 127.0.0.1:6280 in the background
```

Either way, open <http://127.0.0.1:6280>, add a model provider in **Settings**,
and start a conversation. `zett start` returns once the server answers and
leaves it running without the terminal, `zett status` reports it, and
`zett stop` shuts it down; `zett start --foreground` stays attached instead.

## First steps

1. **Connect a model.** `Settings` → `Provider` → `New provider`. Give it a
   name, pick the provider, set the model, and paste an API key. Keys are
   encrypted with a local key file before they are stored.
2. **Start a conversation.** Ask a question, drop in a note or a screenshot, and
   keep going. You can queue your next message while it is still answering, or
   steer the running answer with a correction.
3. **Save what is worth keeping.** Ask for a card, an article, a deck, or a
   paper. The Assistant writes a draft; you review the diff and publish it.
4. **Optional.** Connect a channel under `Channels`, or create a recurring
   prompt under `Scheduled tasks`.

## Where your data lives

Everything is under `~/.zettelekasten/` — the databases, attachments, artifact
projects, user skills, and rotating logs. Set `ZETT_STORAGE_ROOT` to move it.
Deleting a conversation removes its messages, files, and artifacts with it.

## Documentation

The project site is published at **<https://chang-lehung.github.io/zettelekasten/>**,
with the full documentation under **<https://chang-lehung.github.io/zettelekasten/docs/>**:

- [Conversations](https://chang-lehung.github.io/zettelekasten/docs/guide/conversations/), [the Chrome extension](https://chang-lehung.github.io/zettelekasten/docs/guide/chrome-extension/), [artifacts and the library](https://chang-lehung.github.io/zettelekasten/docs/guide/artifacts/), [assets](https://chang-lehung.github.io/zettelekasten/docs/guide/assets/), [scheduled tasks](https://chang-lehung.github.io/zettelekasten/docs/guide/scheduled-tasks/), [channels](https://chang-lehung.github.io/zettelekasten/docs/guide/channels/), [settings and local data](https://chang-lehung.github.io/zettelekasten/docs/guide/settings/), [the command line](https://chang-lehung.github.io/zettelekasten/docs/guide/command-line/)
- [Writing a plugin](https://chang-lehung.github.io/zettelekasten/docs/plugins/) — add tools, hooks, or a new chat platform
- [Backend reference](https://github.com/Chang-LeHung/zettelekasten/blob/main/backend/README.md) — layers, storage boundaries, and the HTTP surface, for contributors

## Development

```bash
git clone https://github.com/Chang-LeHung/zettelekasten
cd zettelekasten

make install     # build the frontend and install the `zett` command
make dev         # run from source with reload on 127.0.0.1:6280
make check       # Ruff, backend/agim/channel tests, frontend tests, typecheck, build
```

The repository holds the FastAPI application and the Vue interface that Zett
serves. `backend/README.md` documents how the backend is put together, and
`AGENTS.md` records the rules a change has to follow.

The repository also carries two packages that are released on their own:
[`agim`](https://chang-lehung.github.io/zettelekasten/docs/agim/), the stateless chat
SDK, and [`zett-weixin`](https://chang-lehung.github.io/zettelekasten/docs/weixin/),
the WeChat channel plugin built on it. The agent runtime
Zett runs on lives in its own repository,
[`zett-agent`](https://github.com/Chang-LeHung/zett-agent).

`zett3rd/` keeps integrations that live beside Zett without being part of its
build — nothing there is imported by the backend or the interface, so a broken
one can never fail Zett itself. It currently holds a
[Zettelekasten Chrome extension](https://github.com/Chang-LeHung/zettelekasten/tree/main/zett3rd/chrome-extension) (Vue 3 +
TypeScript, built with Vite) that embeds a separate conversation in each
webpage, reads that page, and saves useful results into your library.

### Plugins

Zett discovers installed packages through entry points, so an extension is a
normal distribution rather than a patch:

- `zett.agent` — tools, lifecycle hooks, slash commands, and `@` references
  inside a conversation.
- `zett.channels` — a chat platform, from QR login to inbound media.

Install one into the same environment as Zett and restart; the
[plugin guide](https://chang-lehung.github.io/zettelekasten/docs/plugins/) walks
through a complete example, including what the host guarantees and which
boundaries stay closed.

## License

This project is available under the [MIT License](https://github.com/Chang-LeHung/zettelekasten/blob/main/LICENSE).
