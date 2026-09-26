# Channels

Channels connect Zett to a chat platform, so you can talk to the same Agent from
your phone. The `Channels` view lists what is installed, starts a login flow, and
shows each channel's state.

## Connect a channel

1. Open `Channels`, then `Connect`.
2. Pick the platform (the list comes from the installed plugins, not from a
   hard-coded assumption), name the bot, and choose the provider whose model
   handles its conversations.
3. Scan the QR code with the account you want to link, and confirm on the
   platform. Some platforms also show a pairing code — enter it in the dialog.
4. The channel appears as `Connected` and starts receiving messages.

Only one platform is installed today: WeChat, through the personal WeChat
robot feature (Tencent's 微信机器人). WeCom smart robots are not a substitute.

## How conversations map

One external conversation — a channel plus a chat id — maps to one Agent
session with session type `channel`. Turns for the same chat run one at a time,
so two messages in one chat never race each other, and different chats run in
parallel. Channel sessions stay out of the conversation sidebar and are listed
under `Channels`.

If you delete the session a chat is bound to, the next message starts a fresh
one instead of leaving the chat mute, and the stale binding is replaced.

## Media

Images, voice notes, files, and video arrive as attachments the plugin already
downloaded and decrypted, so nothing is fetched twice. Zett writes every
attachment under the session's upload directory and decides what the model sees:
images travel as real image content for a vision model, while voice, files,
video, and oversized images travel as a text reference naming the stored key.
Whether the configured model can use a given attachment is the model's decision,
and a message with only an attachment and no text is a valid turn.

Limits are enforced at the boundary rather than trusted from the plugin: at most
16 attachments and 256 MB per message, and a bounded amount of inline image data
per turn. An attachment over the limit is never dropped silently — the chat gets
`That file is too large to process. Please send a smaller one.` instead of a
turn over bytes nobody received.

## Channel policy

Each channel stores its provider, reasoning effort, and whether remote
conversations may use coding tools. These are read per turn, so editing them
never restarts the plugin; only the enabled flag starts or stops it. Disabling a
provider is refused while a channel still uses it.

Channel runs are headless, like scheduled runs: shell commands execute without
an approval card. Leave `Allow coding tools in remote conversations` off unless
you want a chat message to be able to run commands.

If a turn fails, the chat receives one fixed notice — `Sorry, something went
wrong while handling that message. Please try again.` — rather than staying
silent. A login that fails, or a scan that is never confirmed, leaves the
channel disconnected and reusable instead of half-created.

## Writing another channel

Channels are plugins discovered from installed entry points, so a new platform
is a package, not a patch to Zett. See
[Channel plugins](../plugins/channel-plugins.md).
