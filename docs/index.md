---
layout: home

hero:
  name: Zett
  text: Make something worth keeping.
  tagline: "A workspace for thinking with an AI, on your own computer. Start from a thought, a file, or the page you are reading, and keep the version you choose in a folder you own."
  actions:
    - theme: brand
      text: Quick start
      link: '#quick-start'
    - theme: alt
      text: Read the guide
      link: /guide/conversations
    - theme: alt
      text: GitHub
      link: https://github.com/Chang-LeHung/zettelekasten

features:
  - title: Conversations
    details: "Queue follow-ups while a turn runs, steer it mid-flight, approve shell commands, and pick one of eight reasoning levels."
    link: /guide/conversations
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>'
  - title: Read from Chrome
    details: "Open Zett beside any page. It reads the page, and can fill or click only after you approve each action."
    link: /guide/chrome-extension
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M14 13h4M14 16h4"/></svg>'
  - title: Artifacts and the library
    details: "Cards, articles, images, slide decks, and LaTeX papers: drafts first, published when you save."
    link: /guide/artifacts
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>'
  - title: Assets
    details: "Reference files for one conversation, and a file library you can reuse in all of them."
    link: /guide/assets
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>'
  - title: Scheduled tasks
    details: "Have Zett do the same job every morning, week, or month, with no browser open."
    link: /guide/scheduled-tasks
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
  - title: Channels
    details: "Message Zett from WeChat on your phone, with photos, voice notes, and files."
    link: /guide/channels
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="20" rx="2.5"/><path d="M11 18h2"/></svg>'
  - title: Settings and local data
    details: "Connect any model, set limits, watch usage, and back up one folder."
    link: /guide/settings
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/></svg>'
  - title: The command line
    details: "Start and stop Zett, add to the library from scripts, and let Claude Code or Codex file for you."
    link: /guide/command-line
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m5 8 4 4-4 4M12 17h7"/></svg>'
---
## Quick start

You need Python 3.10 to 3.14, on macOS, Linux, or Windows. There is no Zett
account to create.

```bash
uv tool install zettelekasten   # or: pipx install zettelekasten
zett start       # starts Zett in the background
zett status      # checks that it is running
```

The distribution is `zettelekasten`; the command it installs is `zett`. To run
the same application from a checkout instead:

```bash
git clone https://github.com/Chang-LeHung/zettelekasten
cd zettelekasten
make install     # builds the interface and installs the `zett` command
zett start
```

1. Open `http://127.0.0.1:6280`.
2. In **Settings → Provider**, add the model you want Zett to use. Zett brings
   no model of its own; see [AI providers](guide/settings.md#ai-providers).
3. Choose **Start a new session** and try “Make a concise card about this
   idea: local-first beats sync for personal notes.”
4. Review the card beside the chat, then choose **Save** to put it in your
   library.

`zett stop` stops Zett when you are done. To watch its logs while you try
things, run `zett start --foreground` instead.

## A good first session

1. Paste a paragraph or attach a file in a [conversation](guide/conversations.md).
2. Ask for one concise card. Read it beside the chat, ask for changes, and save
   it when the wording is right.
3. File it in a [collection](guide/artifacts.md#tags) so you can find it later,
   and keep files you reuse in [Static Assets](guide/assets.md#static-assets).
4. Do the same while you read: [open Zett in Chrome](guide/chrome-extension.md).

## Build on Zett

<ul class="home-links">
  <li><a href="plugins/"><strong>Plugins</strong><span>How a plugin is packaged, installed, and loaded.</span></a></li>
  <li><a href="plugins/agent-plugins"><strong>Agent plugins</strong><span>Give Zett new tools, hooks, slash commands, and <code>@</code> references.</span></a></li>
  <li><a href="plugins/channel-plugins"><strong>Channel plugins</strong><span>Connect another chat app through login, receive, and send.</span></a></li>
  <li><a href="agim"><strong>agim SDK</strong><span>The small chat-platform SDK the WeChat plugin is built on.</span></a></li>
  <li><a href="weixin"><strong>WeChat channel plugin</strong><span>A complete channel plugin to read alongside the guide.</span></a></li>
</ul>

## Where your data lives

Your library, conversations, files, and settings live in `~/.zettelekasten/`.
Back up that folder to keep your workspace, or set `ZETT_STORAGE_ROOT` before
`zett start` to keep it somewhere else. Messages you send to a model still go
to the provider you chose, so don't send anything you would not want that
provider to process.
