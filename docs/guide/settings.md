# Settings and local data

## Preferences

The language switch (English / 中文) is stored in your browser, not in the
database, so it follows you across conversations on that browser.

## Providers

`AI providers` holds every model connection. A provider record is a name, a
protocol, a model identifier, an optional base URL, an API key, and an
optional API mode. Several records can point at the same vendor, which is how
you keep two models or two endpoints side by side and choose one per
conversation.

| Protocol | Use |
| --- | --- |
| `openai`, `anthropic`, `google`, `deepseek`, `ollama` | Native adapters |
| `openai_compatible`, `responses_compatible` | Any endpoint that speaks the OpenAI or Responses API |

API keys are encrypted with a local key file before they are stored, and never
come back through the API — a provider read reports only whether a key is
configured. Composing a prompt is what decides which protocol adapter is used;
only one place in the codebase makes that choice, so a new protocol does not
have to be taught to the rest of the application.

A provider that a conversation, a scheduled task, or a channel still uses cannot
be disabled or deleted; the request is refused rather than leaving a dangling
reference.

## Limits

| Setting | Meaning |
| --- | --- |
| Images per message | How many images one message may carry |
| Model steps per turn | Maximum model/tool round trips in one turn |
| Max asset file size | Bound for an uploaded or pasted file |
| Compact context at | Token threshold that triggers compaction |
| Keep recent context | Recent tokens kept verbatim by a compaction |

These are user settings rather than environment variables, and they apply to new
requests immediately.

## Usage

`Usage` records model activity from completed calls: requests and tokens per
day over the last twelve months, broken down by model with input, output,
reasoning, cache read and write tokens, and cache hit rate. It is a local log —
nothing is sent anywhere — and it is what the per-turn numbers in the
conversation trace are aggregated from.

## Where your data lives

Everything is under one directory, `~/.zettelekasten` by default:

```text
~/.zettelekasten/
├── zett.db         artifacts, assets, static assets, tags, providers, settings
├── agent.db        sessions, immutable raw messages, context snapshots
├── assets/         sessions/<session-id>/ binaries, message uploads, static/
├── artifacts/      per-session artifact project directories (LaTeX PDFs)
├── skills/         user skills, including the built-in zett-artifact-syntax
├── provider.key    local key encrypting provider credentials
├── runtime.json    active server and supervised child process state
└── logs/           rotating log files
```

Set `ZETT_STORAGE_ROOT` to move it. Every stored path is an object key relative
to that root, so nothing in the database is tied to a machine-specific absolute
path, and tests run against isolated temporary directories rather than your
real data. The full variable list is on the [backend](../backend.md) page.

Deleting a conversation removes its messages, assets, uploads, artifacts, and
artifact project directories. Deleting a static asset is refused while a
session asset still imports it. Nothing here is uploaded to a third party:
the only network calls are the model provider you configured and, if you enable
them, the chat platforms you connected.
