/**
 * The element the content script mounts the conversation panel in.
 *
 * It is a real, fixed, full-page-stacking div appended to `documentElement`, so
 * it shadows page content for `elementFromPoint`. The id lives here because both
 * the mount code and the diagnostics must agree on it: a rename that only
 * touched the mount would silently report the panel as the page element that
 * covers a target.
 */
export const PANEL_HOST_ID = 'zettelekasten-panel-host'
