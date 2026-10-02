# Make something worth keeping

Zett is a workspace for thinking with an AI, on your own computer. Start with a
thought, a file, or the page you are reading; shape it into a card, an article,
a slide deck, an image, or a paper; and keep the version you choose in a
library that lives in a folder you own.

## Quick start

You need Python 3.10 to 3.14, on macOS, Linux, or Windows. There is no Zett
account to create.

```bash
git clone https://github.com/Chang-LeHung/zettelekasten
cd zettelekasten
make install     # installs the `zett` command
zett start       # starts Zett in the background
zett status      # checks that it is running
```

1. Open `http://127.0.0.1:6280`.
2. In **Settings → Provider**, add the model you want Zett to use. Zett brings
   no model of its own; see [AI providers](guide/settings.md#ai-providers).
3. Choose **Start a new session** and try “Make a concise card about this
   idea: local-first beats sync for personal notes.”
4. Review the card beside the chat, then choose **Save** to put it in your
   library.

`zett stop` stops Zett when you are done. To watch its logs while you try
things, run `zett start --foreground` instead. Zett is not on PyPI yet, so the
source checkout is how you install it today.

## User guide

<ul class="docs-cards">
  <li><a class="docs-card" href="guide/conversations.md"><strong>Conversations</strong><span>Ask, queue and steer messages, approve commands, and read what each turn did.</span></a></li>
  <li><a class="docs-card" href="guide/chrome-extension.md"><strong>Read from Chrome</strong><span>Open Zett beside a webpage, ask about it, and save the result without leaving the page.</span></a></li>
  <li><a class="docs-card" href="guide/artifacts.md"><strong>Artifacts and the library</strong><span>Cards, articles, images, slides, and LaTeX papers: drafts first, published when you save.</span></a></li>
  <li><a class="docs-card" href="guide/assets.md"><strong>Assets</strong><span>Reference files for one conversation, and a file library for all of them.</span></a></li>
  <li><a class="docs-card" href="guide/scheduled-tasks.md"><strong>Scheduled tasks</strong><span>Have Zett do the same job every morning, week, or month, with no browser open.</span></a></li>
  <li><a class="docs-card" href="guide/channels.md"><strong>Channels</strong><span>Message Zett from WeChat on your phone, with photos, voice notes, and files.</span></a></li>
  <li><a class="docs-card" href="guide/settings.md"><strong>Settings and local data</strong><span>Connect models, set limits, see your usage, and back up your folder.</span></a></li>
  <li><a class="docs-card" href="guide/command-line.md"><strong>The command line</strong><span>Start and stop Zett, add to the library from scripts, and let Claude Code, Codex, or ChatGPT save for you.</span></a></li>
</ul>

## Developer guide

<ul class="docs-cards">
  <li><a class="docs-card" href="plugins/index.md"><strong>Plugins</strong><span>How a plugin is packaged, installed, and loaded.</span></a></li>
  <li><a class="docs-card" href="plugins/agent-plugins.md"><strong>Agent plugins</strong><span>Give Zett new tools, hooks, slash commands, and <code>@</code> references.</span></a></li>
  <li><a class="docs-card" href="plugins/channel-plugins.md"><strong>Channel plugins</strong><span>Connect another chat app through login, receive, and send.</span></a></li>
  <li><a class="docs-card" href="agim.md"><strong>agim SDK</strong><span>The small chat-platform SDK the WeChat plugin is built on.</span></a></li>
  <li><a class="docs-card" href="weixin.md"><strong>WeChat channel plugin</strong><span>A complete channel plugin to read alongside the guide.</span></a></li>
</ul>

## A good first session

1. Paste a paragraph or attach a file in a [conversation](guide/conversations.md).
2. Ask for one concise card. Read it beside the chat, ask for changes, and save
   it when the wording is right.
3. File it in a [collection](guide/artifacts.md#tags) so you can find it later,
   and keep files you reuse in [Static Assets](guide/assets.md#static-assets).
4. Do the same while you read: [open Zett in Chrome](guide/chrome-extension.md).

## Where your data lives

Your library, conversations, files, and settings live in `~/.zettelekasten/`.
Back up that folder to keep your workspace, or set `ZETT_STORAGE_ROOT` before
`zett start` to keep it somewhere else. Messages you send to a model still go
to the provider you chose, so don't send anything you would not want that
provider to process.
