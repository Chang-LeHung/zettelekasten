// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import MarkdownIt from 'markdown-it'
import { sanitizeMarkdown } from './sanitizeMarkdown'

const render = (source: string) => sanitizeMarkdown(new MarkdownIt({ html: true }).render(source))

describe('authored HTML', () => {
  it('renders nested layout HTML and leaves fenced HTML as source', () => {
    const html = render('<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px"><h2>Title</h2><img src="/image.png"></div>')
    expect(html).toContain('display:grid')
    expect(html).toContain('<h2>Title</h2>')
    expect(render('```html\n<div>Example</div>\n```')).toContain('&lt;div&gt;Example&lt;/div&gt;')
  })
  it('removes scripts, event handlers, unsafe URLs and global CSS', () => {
    const html = render('<style>body{display:none}</style><script>alert(1)</script><div onclick="alert(1)" style="position:fixed;z-index:999;background-image:url(https://example.com/x)"><a href="javascript:alert(1)">Link</a><iframe src="/x"></iframe></div>')
    expect(html).not.toMatch(/<script|<style|onclick|javascript:|<iframe|position:|z-index:|background-image:/u)
  })
  it('retains generated controls and formula positioning', () => {
    expect(sanitizeMarkdown('<button class="code-copy-button">Copy</button><span style="position:relative;top:-1em">x</span>')).toContain('<button')
    expect(sanitizeMarkdown('<span style="position:relative">x</span>')).toContain('position:relative')
  })
})
