/**
 * Read the page the user is looking at.
 *
 * Extraction runs inside the page through `chrome.scripting.executeScript`, so
 * `extractPage` must be self-contained: it is serialized into the page and
 * cannot see this module's imports. The constant it needs arrives as an argument.
 */

import { MAX_PAGE_CHARS } from './page-text'
import type { PageSnapshot } from '../api/types'

/** Pages Chrome never lets an extension read, named so the panel can explain. */
const RESTRICTED_PREFIXES = [
  'chrome://',
  'chrome-extension://',
  'edge://',
  'about:',
  'view-source:',
  'https://chrome.google.com/webstore',
  'https://chromewebstore.google.com',
]

/** Run in the page: return its identity, its description, and its readable text. */
function extractPage(maxChars: number): PageSnapshot {
  const collapsed = (value: unknown): string => String(value ?? '').replace(/\s+/g, ' ').trim()
  const meta = (selector: string): string =>
    document.querySelector(selector)?.getAttribute('content') ?? ''
  const body = (document.body?.innerText ?? '').replace(/\n{3,}/g, '\n\n').trim()
  return {
    title: collapsed(document.title),
    url: location.href,
    description: collapsed(meta('meta[name="description"]') || meta('meta[property="og:description"]')),
    selection: collapsed(window.getSelection()?.toString()),
    text: body.length > maxChars ? body.slice(0, maxChars) : body,
    truncated: body.length > maxChars,
  }
}

/**
 * Read the tab that owns this embedded panel.
 *
 * A restricted page has no content script and no text, which reads as "the page
 * is empty" if this is not said out loud, so the caller gets an explanation
 * instead of an empty page. The `tabs` permission is what makes `tab.url`
 * readable for pages `<all_urls>` does not cover (`about:blank`, `chrome://`),
 * which is exactly the case this check has to name.
 */
export async function readActivePage(maxChars: number = MAX_PAGE_CHARS, tabId?: number): Promise<PageSnapshot> {
  const tab = tabId === undefined
    ? (await chrome.tabs.query({ active: true, currentWindow: true }))[0]
    : await chrome.tabs.get(tabId)
  if (!tab?.id) throw new Error('No page to read in this window')
  const url = tab.url ?? tab.pendingUrl ?? ''
  if (!url || RESTRICTED_PREFIXES.some((prefix) => url.startsWith(prefix))) {
    throw new Error('Chrome does not let extensions read this page')
  }
  let result
  try {
    ;[result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPage,
      args: [maxChars],
    })
  } catch (error) {
    // Chrome refuses a page it will not inject into; say that in the panel's own
    // words instead of forwarding a manifest-shaped message.
    throw new Error(`Chrome did not read this page: ${(error as Error).message}`)
  }
  const page = result?.result
  if (!page) throw new Error('The page did not return any text')
  return page
}
