# Channels

A channel connects Zett to a chat app, so you can message the same Zett from
your phone: send a whiteboard photo and ask for a card, forward a voice note,
or ask what you saved about a topic this week.

## Connect a chat app

1. Open **Channels** in the sidebar and choose **Connect**.
2. If more than one chat app is available, pick the platform.
3. Give the bot a name and choose the provider that answers its chats.
4. Choose **Generate QR code**, then scan the code with the account you want to
   connect and confirm on your phone.
5. If the app shows a pairing code, type it into the dialog.
6. The channel appears as **Connected** and starts answering messages.

The dialog tells you where you are: waiting for the scan, scanned and waiting
for you to confirm, waiting for the pairing code, or connecting. A QR code
expires after five minutes; generate a new one if it does.

The platforms you can choose are the chat plugins installed with Zett. Today
that is **WeChat**, through Tencent's personal WeChat bot feature (微信机器人).
A WeCom (企业微信) bot does not work as a substitute.

## Chats and history

Every direct chat and every group chat gets its own conversation, listed under
**Channels** rather than with your other conversations. Messages in one chat
are answered in order. Delete a chat's history to make the next message start
fresh.

## Photos, voice, and files

Send images, voice notes, files, or video, with or without a message. Zett
keeps a copy of each one with that chat's conversation. A model that can see
images reads supported images directly; other files are available for Zett to
open. Whether the model can understand a particular file depends on your
provider.

A message can carry up to 16 attachments and 256 MB in total. When something
is too large, the chat receives an explanation instead of losing the file
silently.

## Channel settings

For each channel you can choose:

- the **provider** and **reasoning effort** that answer its chats, which take
  effect from the next message;
- whether **Allow coding tools in remote conversations** is on.

Chat messages run with no one at a screen, so commands run without an approval
card. Leave **Allow coding tools in remote conversations** off unless you want
a chat message to be able to run commands on this computer.

Use **Disable** to pause a channel and **Enable** to resume it. While a channel
uses a provider, that provider cannot be disabled or deleted.

## When something goes wrong

If Zett cannot answer a message, the chat receives an error notice. Check that
the channel still reads **Connected** and that `zett status` shows Zett
running, then send the message again. If a login fails or the QR code expires,
start again with **Connect**.

Want Zett in another chat app? Channels are plugins; see
[Channel plugins](../plugins/channel-plugins.md).
