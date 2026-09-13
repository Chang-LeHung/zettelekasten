import type MarkdownIt from 'markdown-it'

/** Turn standalone Markdown images into numbered figures without invalid nested paragraphs. */
export function markdownFigures(md: InstanceType<typeof MarkdownIt>): void {
  md.core.ruler.after('inline', 'zett_figures', state => {
    let number = 0
    for (let index = 0; index < state.tokens.length - 2; index += 1) {
      const opening = state.tokens[index]
      const inline = state.tokens[index + 1]
      const closing = state.tokens[index + 2]
      if (opening.type !== 'paragraph_open' || inline.type !== 'inline' || closing.type !== 'paragraph_close') continue
      const children = inline.children ?? []
      const meaningful = children.filter(token => token.type !== 'text' || token.content.trim())
      if (meaningful.length !== 1 || meaningful[0].type !== 'image') continue
      const image = meaningful[0]
      const description = String(image.attrGet('title') || md.renderer.renderInlineAsText(image.children ?? [], md.options, state.env))
      number += 1
      opening.tag = 'figure'
      opening.hidden = false
      opening.attrSet('class', 'markdown-figure')
      closing.tag = 'figure'
      closing.hidden = false
      const caption = new state.Token('figure_caption', '', 0)
      caption.content = description
      caption.meta = { number }
      state.tokens.splice(index + 2, 0, caption)
      index += 3
    }
  })
  md.renderer.rules.figure_caption = (tokens, index) => {
    const token = tokens[index]
    const description = token.content ? `: ${md.utils.escapeHtml(token.content)}` : ''
    return `<figcaption><span class="figure-number">Figure ${token.meta?.number}</span>${description}</figcaption>`
  }
}
