/**
 * One tab/document URL owns one conversation, independently of the panel UI.
 * Each mapping is stored under its own Chrome storage key: simultaneous iframe
 * startups must not overwrite each other's read/modify/write of one map.
 */
export const PAGE_SESSION_PREFIX = 'pageSession:'

export function belongsToTab(key: string, tabId: number): boolean {
  if (!key.startsWith(PAGE_SESSION_PREFIX)) return false
  try {
    const value = JSON.parse(key.slice(PAGE_SESSION_PREFIX.length))
    return Array.isArray(value) && value.length === 3 && value[1] === tabId
  } catch {
    return false
  }
}

export function pageKey(serverUrl: string, tabId: number, pageUrl: string): string | null {
  try {
    if (!Number.isSafeInteger(tabId) || tabId < 0) return null
    const page = new URL(pageUrl)
    if (page.protocol !== 'http:' && page.protocol !== 'https:') return null
    page.hash = '' // an in-page anchor does not create another conversation
    const server = new URL(serverUrl)
    return PAGE_SESSION_PREFIX + JSON.stringify([server.origin + server.pathname.replace(/\/$/, ''), tabId, page.href])
  } catch {
    return null
  }
}
