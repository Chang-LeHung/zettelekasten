# Settings and local data

Choose **Settings** in the sidebar. The dialog opens over your workspace, with
**Usage**, **Provider**, and **Limit** sections. Close it with **×**, **Esc**,
or a click outside, and you are back exactly where you were.

## Language

Switch between **English** and **中文** with the language menu at the bottom of
the sidebar. The choice is remembered by this browser.

## AI providers

Zett brings no model of its own. A provider is one connection to a model: a
name, the service, the model, and your API key. Add several to keep two models
or two endpoints side by side, then pick one per conversation, task, or
channel.

1. Open **Settings → Provider** and choose **New provider**.
2. Give it a **Connection name** you will recognize, such as “DeepSeek chat”.
3. Under **Provider**, choose the kind of service, then enter the **Model**,
   for example `deepseek-chat`.
4. Paste your **API key**. Fill in **Base URL** only if your service needs a
   custom address.
5. Save. The provider appears in the **Model** menu of every conversation.

| Provider | Use it for |
| --- | --- |
| **OpenAI**, **Anthropic**, **Google Gemini**, **DeepSeek**, **Ollama** | Those services directly. Ollama runs models on your own computer. |
| **OpenAI compatible**, **Responses compatible** | Any other service that offers an OpenAI-style or Responses-style API. |

### Web search

Turn on **Web search** in a provider so the model can look things up on the web
itself and cite what it found. The service runs the search, so it works only
where the service offers one:

- the **Responses API** of OpenAI and compatible services,
- **Anthropic** and Anthropic-compatible services, and
- **Google Gemini**.

DeepSeek is the exception: only its **flash** models search, and only through
an **Anthropic compatible** connection. Zett refuses to save the switch for any
other DeepSeek setup, because those endpoints accept the request and then
answer from memory without searching.

Leave the **search tool name** blank to use the default for the service, or type
the name your service documents, such as `web_search_20250305`. A service can
limit how often it searches, so a search can fail on its side; the model then
says it could not look the answer up.

Your API key is encrypted on this computer and is never shown again. When you
edit a provider, leave the key empty to keep the one you saved.

A provider that a conversation, scheduled task, or channel still uses cannot be
disabled or deleted. Switch those to another provider first.

## Limits

| Setting | What it controls |
| --- | --- |
| **Images per message** | How many images one message can carry. |
| **Model steps per turn** | How many steps Zett may take, such as tool calls, before it has to answer. |
| **Max asset file size** | The largest file you can upload or paste. |
| **Compact context at** | How long a conversation can get before Zett summarizes its older turns. |
| **Keep recent context** | How much of the latest conversation is kept word for word when it does. |

New messages use the changed limits right away. A reply that is already running
finishes with the limits it started with.

## Usage

**Usage** shows how you have used your models over time: requests, input and
output tokens, reasoning, and cache use for each model, with a calendar of
daily activity. It is computed from your own history on this computer. For one
conversation's details, open its **Trace**.

## Where your data lives

Everything Zett keeps — your library, conversations, files, providers, and
settings — lives in one folder on your computer: `~/.zettelekasten`.

- **Back up** that folder to keep your workspace, and restore it to bring
  everything back.
- **Move it** by setting `ZETT_STORAGE_ROOT` to another folder before you run
  `zett start`.
- **Logs** are in its `logs` folder, which helps when something goes wrong.

::: info What leaves your computer
Your folder stays local, but the messages you send to a model go to the
provider you chose, and a connected chat app exchanges messages with its
own service. Do not send anything you would not want them to process.
:::

Deleting a conversation also deletes the files and artifacts it created. A
static asset cannot be deleted while a conversation still uses it.
