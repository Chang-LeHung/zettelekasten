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
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import css from 'highlight.js/lib/languages/css'
import diff from 'highlight.js/lib/languages/diff'
import dockerfile from 'highlight.js/lib/languages/dockerfile'
import go from 'highlight.js/lib/languages/go'
import ini from 'highlight.js/lib/languages/ini'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import kotlin from 'highlight.js/lib/languages/kotlin'
import lua from 'highlight.js/lib/languages/lua'
import makefile from 'highlight.js/lib/languages/makefile'
import markdown from 'highlight.js/lib/languages/markdown'
import php from 'highlight.js/lib/languages/php'
import powershell from 'highlight.js/lib/languages/powershell'
import python from 'highlight.js/lib/languages/python'
import ruby from 'highlight.js/lib/languages/ruby'
import rust from 'highlight.js/lib/languages/rust'
import sql from 'highlight.js/lib/languages/sql'
import swift from 'highlight.js/lib/languages/swift'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import MarkdownIt from 'markdown-it'

import 'highlight.js/styles/github.css'

const LANGUAGES = {
  bash,
  c,
  cpp,
  csharp,
  css,
  diff,
  dockerfile,
  go,
  ini,
  java,
  javascript,
  json,
  kotlin,
  lua,
  makefile,
  markdown,
  php,
  powershell,
  python,
  ruby,
  rust,
  sql,
  swift,
  typescript,
  xml,
  yaml,
}

/** Names a shell or a model uses for a language it already highlighted for us. */
const LANGUAGE_ALIASES: Record<string, string> = {
  sh: 'bash',
  shell: 'bash',
  shellsession: 'bash',
  zsh: 'bash',
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  py: 'python',
  yml: 'yaml',
  md: 'markdown',
  'c++': 'cpp',
  'c#': 'csharp',
}

for (const [name, language] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, language)
}

function resolveLanguage(language: string): string {
  const resolved = LANGUAGE_ALIASES[language.trim().toLowerCase()] ?? language.trim().toLowerCase()
  return /^[a-z0-9_-]+$/u.test(resolved) && hljs.getLanguage(resolved) ? resolved : ''
}

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

// Fenced code keeps the app's block class, so both threads style it the same way.
const defaultFence = renderer.renderer.rules.fence
renderer.renderer.rules.fence = (tokens, index, options, env, self) => {
  const rendered = defaultFence
    ? defaultFence(tokens, index, options, env, self)
    : self.renderToken(tokens, index, options)
  return rendered.replace('<pre>', '<pre class="code-block">')
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
