import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: true })

/** Library summaries contain prose only; never mount images, diagrams or raw HTML. */
export function libraryExcerptText(source: string): string {
  const tokens = markdown.parse(source, {})
  const paragraphs: string[] = []
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]
    if (token.type !== 'inline' || tokens[index - 1]?.type === 'heading_open') continue
    const text = (token.children ?? []).map(child => {
      if (child.type === 'text' || child.type === 'code_inline') return child.content
      if (child.type === 'softbreak' || child.type === 'hardbreak') return ' '
      return ''
    }).join('').trim()
    if (text) paragraphs.push(text)
  }
  const text = paragraphs.join(' ').replace(/\s+/gu, ' ').trim()
  return text.length > 220 ? `${text.slice(0, 220)}…` : text
}
