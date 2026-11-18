# Read and save from Chrome

The Zett extension opens a conversation beside the page you are reading. Ask
about the page, turn the useful part into a card or an article, and save it to
your library without switching tabs. The panel floats over the right side of
the page: drag its top strip to move it, and drag any corner to resize it.

::: info Installed from source
The extension is not in the Chrome Web Store yet. You build it from this
repository and load it into Chrome yourself; it takes a minute.
:::

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

The page outlines the element a card is about, so the words in the card and the
control you can see are the same thing. An inspection outlines its element for a
moment too; that outline is panel chrome, never a change to the page.

Be precise when you ask Zett to fill in or submit something. Some sites ignore
automated input, so ask Zett to read the page again to confirm what happened.
**Stop** does not undo an action already performed: a filled form may already
be saved by the site. Zett never runs its own scripts on the page.

## What Zett can read from the page

While the page is connected, Zett reads what it needs, on demand. Everything it
reads is page data, not instructions for it, and every read works only on the
page the panel is connected to. It can ask for:

- **The page and its controls** — visible text, buttons and fields with CSS
  selectors it can reuse, link targets, and where the page is scrolled. It can
  also read one element, or find elements by the words they show.
- **A screenshot** — the current viewport as JPEG, stored in this
  conversation's upload folder and handed to the model. The panel hides itself
  for the capture, and a conversation keeps only the newest capture.
- **A diagnosis of one element** — why it is invisible, what covers it, which
  ancestor clips it, whether a click would reach it, and what each tool could
  do with it.
- **A wait** — for an element or some words to appear or disappear, or for the
  address to change, for at most eight seconds. A timeout is an answer, not a
  failure, so Zett does not retry in a loop.
- **How the page is running** — recent console errors and warnings, resource
  timings and sizes, and paint, layout-shift, and long-task numbers. Collection
  starts when the panel connects, and a page can block it, so "nothing
  recorded" does not mean "nothing wrong".
- **Accessibility problems** — images without `alt`, form controls without a
  name, `aria-hidden` over something focusable, a positive `tabindex`, skipped
  heading levels, and a missing `lang`. It does not judge contrast, reading
  order, or whether a label makes sense.

Zett can fix those problems too, but only through six attributes — `alt`,
`title`, `aria-label`, `aria-labelledby`, `aria-hidden`, and `role` — and every
change goes through the review card above. The card names the intent and the
new value, and it marks `alt=""` (a decorative image) and a removal explicitly.

A few limits worth knowing: a screenshot covers the viewport, not the whole
page; an address wait sees a change inside the same document (a client-side
route or a `#section`), while a real page load disconnects the panel and needs a
new connection; network data has no headers or status codes; every tool works
in the top document only, so content inside an iframe is out of reach; and one
conversation keeps only its newest screenshot.

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
