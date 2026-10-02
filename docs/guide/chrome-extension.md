# Read and save from Chrome

The Zett extension opens a conversation beside the page you are reading. Ask
about the page, turn the useful part into a card or an article, and save it to
your library without switching tabs. The panel floats over the right side of
the page: drag its top strip to move it, and drag any corner to resize it.

!!! note "Installed from source"
    The extension is not in the Chrome Web Store yet. You build it from this
    repository and load it into Chrome yourself; it takes a minute.

## Install the extension

1. [Install and start Zett](../index.md#quick-start), and check that
   `http://127.0.0.1:6280` opens in your browser.
2. Build the extension from your copy of the repository:

   ```bash
   npm --prefix zett3rd/chrome-extension install
   npm --prefix zett3rd/chrome-extension run build
   ```

3. Open `chrome://extensions`, turn on **Developer mode**, and choose
   **Load unpacked**. Select the `zett3rd/chrome-extension/dist` folder, not
   the folder above it.
4. Open any web page and click the Zett icon in the toolbar. If Zett runs at a
   different address, change it in the panel's **Settings**.

To update the extension later, build it again and click **Reload** on its card
in `chrome://extensions`.

The extension needs access to the pages you use it on, so it can read the
current page when you send a message. The page goes to your own Zett, and from
there to the model provider you chose.

## Work with a page

Try “Summarize this page in three points” or “Make a card from the argument in
the second section.” The answer streams into the panel.

- Anything Zett creates appears in the panel with a **Save** button. Choose
  **Save all** from the **•••** menu to save everything pending at once.
- Ask Zett to tag what it makes, and it files the result under your
  collections when you save.
- Add images with the picker, by pasting, or by dropping them on the message
  box.
- **Enter** sends; **Shift + Enter** starts a new line.
- A message sent while Zett is answering waits in a queue. **Steer** hands it to
  the current answer, or remove it, or let it run next.
- **Stop** ends the current answer and clears the queue.

Each tab and page keeps its own conversation. Come back to a page and its
conversation is still there; jumping to a `#section` of the same page does not
start a new one. Use **New chat** to start over on the page, or pick a recent
conversation from the panel header.

## Let Zett use the page

While the page is connected, Zett can read what is on it, and with your
permission click, type, press keys, or drag on it. Every action asks first:

- **Allow once** lets this one action through.
- **Always allow in this session** stops asking for the rest of this
  conversation. You can take it back from the **•••** menu.
- **Reject** refuses it, and Zett carries on without it.

Be precise when you ask Zett to fill in or submit something. Some sites ignore
automated input, so ask Zett to read the page again to confirm what happened.
**Stop** does not undo an action already performed: a filled form may already
be saved by the site. Zett never runs its own scripts on the page.

## If the panel cannot connect

1. Run `zett status` and check that Zett opens at the address set in the
   panel.
2. In the panel's **•••** menu, choose **Connect page** to try again.
3. After rebuilding the extension, click **Reload** on its card and reopen the
   page.

If the page connection stays unavailable, Zett can still answer from an
excerpt of the page, but it cannot read the live page or act on it during that
answer.

Next, see [Conversations](conversations.md) for the composer and the
workspace, or [Artifacts and the library](artifacts.md) for drafts and saving.
