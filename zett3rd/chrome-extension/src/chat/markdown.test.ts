// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import { renderMarkdown, sanitizeMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('renders the Markdown an answer is written in', () => {
    const html = renderMarkdown('# Title\n\n- one\n- two\n\n`code`')

    expect(html).toContain('<h1>Title</h1>')
    expect(html).toContain('<li>one</li>')
    expect(html).toContain('<code>code</code>')
  })

  it('keeps fenced code in the app’s block class and highlights it', () => {
    const html = renderMarkdown('```python\nprint("hi")\n```')

    expect(html).toContain('class="code-block"')
    expect(html).toContain('hljs')
    expect(html).toContain('data-code-copy')
    expect(html).toContain('>Python<')
  })

  it('highlights the shared language registry, including LaTeX', () => {
    const latex = renderMarkdown('```tex\n\\frac{1}{2}\n```')

    expect(latex).toContain('class="language-latex"')
    expect(latex).toContain('>LaTeX<')
    expect(renderMarkdown('```scss\n$x: 1;\n```')).toContain('class="language-scss"')
    expect(renderMarkdown('```graphql\n{ me { id } }\n```')).toContain('class="language-graphql"')
  })

  it('turns a link into something safe to click', () => {
    const html = renderMarkdown('[Zett](https://example.com)')

    expect(html).toContain('href="https://example.com"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('drops script tags and inline handlers from an answer', () => {
    const html = sanitizeMarkdown('<p onclick="steal()">hi</p><script>steal()</script>')

    expect(html).toContain('hi')
    expect(html).not.toContain('onclick')
    expect(html).not.toContain('<script')
  })

  it('strips CSS that could fetch or cover the panel', () => {
    const html = sanitizeMarkdown(
      '<div style="position:fixed;z-index:9;background:url(http://example.com/x)">x</div>',
    )

    expect(html).not.toContain('fixed')
    expect(html).not.toContain('z-index')
    expect(html).not.toContain('url(')
  })
})
