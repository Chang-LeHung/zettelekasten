/**
 * Turn a page into the text an agent can use, without carrying the whole DOM.
 *
 * The extraction runs inside the page (see `page-reader.ts`), so these helpers
 * stay pure: they take strings and return strings, and nothing here touches the
 * `chrome` API. That is what makes them testable on their own.
 */

import type { PageSnapshot } from '../api/types'

/** Longest page body sent to the agent, before the prompt becomes the page. */
export const MAX_PAGE_CHARS = 20000

/**
 * Tell the model why it has no browser tools in this turn.
 *
 * A turn carries `get_browser_page` / `update_browser_dom` /
 * `interact_with_browser` only while the panel is connected to the page. Without
 * this note the model learns that by calling one and reading "Unknown tool",
 * which reads like a broken capability instead of a disconnected panel.
 */
export const PAGE_TOOLS_UNAVAILABLE_NOTE = [
  '[Panel note: this turn has no live browser tools. The Chrome panel is not connected to the page,',
  'so get_browser_page, update_browser_dom and interact_with_browser do not exist right now.',
  'Work from the page excerpt below, and tell the user to press "Connect page" in the panel\'s ... menu',
  'before asking for live page reads or edits.]',
].join(' ')

/** Collapse the whitespace a rendered page is full of into single spaces. */
export function collapseWhitespace(value: unknown): string {
  return String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Keep the head of one long body, marking where it was cut. */
export function truncate(value: string, limit: number = MAX_PAGE_CHARS): string {
  if (value.length <= limit) return value
  return `${value.slice(0, limit)}\n\n[…truncated ${value.length - limit} characters]`
}

/**
 * Summarize one page as a single sentence for an artifact's summary field.
 *
 * The description a page publishes is written to be that sentence; the body is
 * only a fallback, and either way the answer is bounded, because a summary that
 * repeats the article is a second copy of it.
 */
export function summarizePage(
  page: Pick<PageSnapshot, 'description' | 'text'> | null,
  limit = 240,
): string {
  const source = collapseWhitespace(page?.description) || collapseWhitespace(page?.text)
  if (!source) return ''
  return source.length <= limit ? source : `${source.slice(0, limit - 1).trimEnd()}…`
}

/** Name the page inside a chat message, keeping its own title and address. */
export function pageContext(
  page: Pick<PageSnapshot, 'title' | 'url' | 'text'>,
  limit: number = MAX_PAGE_CHARS,
): string {
  const heading = [collapseWhitespace(page.title) || 'Untitled page', collapseWhitespace(page.url)]
    .filter(Boolean)
    .join(' — ')
  return `${heading}\n\n${truncate(page.text ?? '', limit)}`
}
