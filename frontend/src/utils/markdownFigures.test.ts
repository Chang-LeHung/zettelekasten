import MarkdownIt from 'markdown-it'
import { describe, expect, it } from 'vitest'
import { markdownFigures } from './markdownFigures'

const md = new MarkdownIt({ html: false }).use(markdownFigures)

describe('Markdown figures', () => {
  it('numbers standalone images in order and restarts for each document', () => {
    const result = md.render('![Architecture](a.png)\n\n![Results](b.png "Measured results")')
    expect(result).toContain('<figure class="markdown-figure">')
    expect(result).toContain('Figure 1</span>: Architecture')
    expect(result).toContain('Figure 2</span>: Measured results')
    expect(result).not.toContain('<p><figure')
    expect(md.render('![](c.png)')).toContain('Figure 1</span></figcaption>')
  })

  it('preserves inline images, code samples and quoted content', () => {
    expect(md.render('Text ![inline](a.png) text')).not.toContain('<figure')
    expect(md.render('```md\n![example](a.png)\n```')).not.toContain('<figure')
    expect(md.render('> ![Evidence](a.png)')).toContain('<blockquote>\n<figure')
  })

  it('escapes captions and handles formatted alt text and tight lists', () => {
    expect(md.render('![**Diagram**](a.png)')).toContain('Figure 1</span>: Diagram')
    expect(md.render('![<script>alert(1)</script>](a.png)')).not.toContain('<script>')
    expect(md.render('- ![First](a.png)\n- ![Second](b.png)')).toContain('Figure 2</span>: Second')
  })
})
