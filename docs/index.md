# Zett documentation

Zett runs on your machine and keeps one data directory. Jot down a fleeting
thought the moment it arrives, develop it with the Assistant into something
durable, and keep it in a library of your own.

Everything here is written for the running application: what a feature does, how
to use it, and what a plugin author has to implement.

## Quick start

```bash
git clone https://github.com/Chang-LeHung/zettelekasten
cd zettelekasten
make install     # build the interface and install the `zett` command
zett start       # serve the API and the interface on 127.0.0.1:6280
```

Open `http://127.0.0.1:6280`, add a provider in `Settings`, and start a
conversation. The API documentation is at `/docs` while the service runs, and
`make check` runs the whole verification suite.

## User guide

<ul class="docs-cards">
  <li><a class="docs-card" href="guide/conversations.md"><strong>Conversations</strong><span>Stream a turn, queue or steer a message, approve shell commands, and read the trace.</span></a></li>
  <li><a class="docs-card" href="guide/artifacts.md"><strong>Artifacts and the library</strong><span>Cards, articles, images, slides, and LaTeX PDFs — draft first, published when you save.</span></a></li>
  <li><a class="docs-card" href="guide/assets.md"><strong>Assets</strong><span>Session reference material and the global Static Assets library.</span></a></li>
  <li><a class="docs-card" href="guide/scheduled-tasks.md"><strong>Scheduled tasks</strong><span>Run an Agent prompt on a cron schedule, headless, with its own isolated session.</span></a></li>
  <li><a class="docs-card" href="guide/channels.md"><strong>Channels</strong><span>Talk to the same Agent from a chat platform, with per-chat sessions and media support.</span></a></li>
  <li><a class="docs-card" href="guide/settings.md"><strong>Settings and local data</strong><span>Providers, limits, usage, and exactly which file lives where on disk.</span></a></li>
</ul>

## Developer guide

<ul class="docs-cards">
  <li><a class="docs-card" href="plugins/index.md"><strong>Plugins</strong><span>How Zett discovers installed packages, what the host guarantees, and where the boundaries are.</span></a></li>
  <li><a class="docs-card" href="plugins/agent-plugins.md"><strong>Agent plugins</strong><span>Add tools, lifecycle hooks, slash commands, and <code>@</code> references to a conversation.</span></a></li>
  <li><a class="docs-card" href="plugins/channel-plugins.md"><strong>Channel plugins</strong><span>Connect a new chat platform through the login, receive, and send contract.</span></a></li>
</ul>

## Reference

<ul class="docs-cards">
  <li><a class="docs-card" href="backend.md"><strong>Backend</strong><span>Layers, storage boundaries, the HTTP surface, and every setting.</span></a></li>
  <li><a class="docs-card" href="agim.md"><strong>agim SDK</strong><span>The stateless IM login/receive/send interface channel plugins build on.</span></a></li>
  <li><a class="docs-card" href="weixin.md"><strong>WeChat channel plugin</strong><span>The personal WeChat plugin Zett discovers through its entry point.</span></a></li>
</ul>

## Highlights

- Catch a fleeting thought, a rough note, or a question before it is gone, and grow it into an artifact later.
- Stream assistant text, reasoning, tool calls, arguments, and results in timeline order.
- Create cards, articles, images, slide decks, and LaTeX PDFs from one conversation.
- Publish cards and articles into a unified searchable library.
- Organize knowledge with recursively nested tags.
- Attach text, links, images, and files to isolated session workspaces.
- Configure multiple AI providers and pick a model and reasoning effort per conversation.
- Connect instant-messaging channels and schedule recurring agent runs.

## Where the data lives

`~/.zettelekasten/` holds both SQLite databases, session and static assets,
git-tracked artifact projects, user skills, the provider encryption key, and the
rotating log files. Set `ZETT_STORAGE_ROOT` to move it. Every file location is
persisted as an object key relative to that root, and tests use isolated
temporary directories instead of the real one.

The project README is the overview of the product, and the agent runtime lives
in [`zett-agent`](https://github.com/Chang-LeHung/zett-agent).
