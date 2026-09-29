/**
 * Render an answer the way the browser app renders one.
 *
 * The panel shows the same Markdown the desktop thread shows, so it uses the
 * same pieces: `markdown-it` for the parse, `highlight.js` for fenced code, and
 * DOMPurify for the result. A model answer is untrusted text that becomes HTML
 * inside an extension page — which holds `chrome.*` APIs — so nothing renders
 * before it is sanitized.
 */

import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

import 'highlight.js/styles/github.css'

import { hljs, languageLabelFor, resolveLanguage } from '../../../../frontend/src/utils/markdownCode'

const renderer = new MarkdownIt({
  breaks: true,
  html: true,
  linkify: true,
  typographer: true,
  highlight(code: string, language: string): string {
    const resolved = resolveLanguage(language)
    if (resolved) return hljs.highlight(code, { language: resolved, ignoreIllegals: true }).value
    return renderer.utils.escapeHtml(code)
  },
})

// Fenced code renders the web thread's block: a toolbar with the language label
// and a copy button, then the highlighted body.
renderer.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index]
  const language = token.info.trim().split(/\s+/u)[0] ?? ''
  const resolved = resolveLanguage(language)
  const highlighted = resolved
    ? hljs.highlight(token.content, { language: resolved, ignoreIllegals: true }).value
    : renderer.utils.escapeHtml(token.content)
  const languageClass = resolved ? ` class="language-${resolved}"` : ''
  const languageLabel = renderer.utils.escapeHtml(languageLabelFor(language, resolved))
  return `<div class="code-block"><div class="code-block-toolbar"><span class="code-language"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 9-3 3 3 3m8-6 3 3-3 3m-2.5-8-3 12" /></svg>${languageLabel}</span><button type="button" class="code-copy-button icon-button" data-code-copy aria-label="Copy code" title="Copy code"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg></button></div><pre><code${languageClass}>${highlighted}</code></pre></div>`
}

export function renderMarkdown(content: string): string {
  return sanitizeMarkdown(renderer.render(content))
}

/** Clean the complete tree, so nested raw HTML and Markdown stay balanced. */
export function sanitizeMarkdown(html: string): string {
  const fragment = DOMPurify.sanitize(html, {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ['style', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'select', 'link', 'meta', 'base'],
  })
  for (const element of fragment.querySelectorAll<HTMLElement>('[style]')) {
    for (const property of Array.from(element.style)) {
      const value = element.style.getPropertyValue(property)
      // Do not allow authored CSS to fetch resources or cover app controls.
      if (
        /url\s*\(|expression\s*\(|@import|\\/iu.test(value) ||
        ['z-index', 'behavior', '-moz-binding'].includes(property) ||
        (property === 'position' && /fixed|sticky/iu.test(value))
      ) {
        element.style.removeProperty(property)
      }
    }
  }
  for (const link of fragment.querySelectorAll('a')) link.setAttribute('rel', 'noopener noreferrer')
  const wrapper = document.createElement('div')
  wrapper.append(fragment)
  return wrapper.innerHTML
}
