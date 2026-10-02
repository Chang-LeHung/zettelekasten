import fs from 'node:fs'
import path from 'node:path'
import type MarkdownIt from 'markdown-it'

/** ``--8<-- "backend/agim/README.md"`` pulls a package README into a page. */
const SNIPPET = /^--8<--\s+"([^"]+)"$/

/** A fence may name the file it belongs to: ```bash title="make site". */
const FENCE_TITLE = /^(.*?)\s*title="([^"]+)"$/

/**
 * Expand snippet lines before the block parser sees them, so a developer
 * reference page (agim, weixin) keeps its package README as the one source of
 * truth. The files are read at build time; a README edit needs a rebuild.
 */
export function snippetPlugin(md: MarkdownIt, repoRoot: string): void {
  md.core.ruler.before('block', 'zett-snippets', (state) => {
    if (!state.src.includes('--8<--')) return
    state.src = state.src
      .split('\n')
      .map((line) => {
        const match = SNIPPET.exec(line.trim())
        if (!match) return line
        return fs.readFileSync(path.resolve(repoRoot, match[1]), 'utf8')
      })
      .join('\n')
  })
}

/**
 * Render ```lang title="name" as the ordinary highlighted block with the file
 * name above it. The title is stripped before Shiki reads the info string, so
 * the language is still the only thing it has to understand.
 */
export function fenceTitlePlugin(md: MarkdownIt): void {
  const fence = md.renderer.rules.fence
  if (!fence) return
  md.renderer.rules.fence = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    const match = FENCE_TITLE.exec(token.info.trim())
    if (!match) return fence(tokens, idx, options, env, self)
    token.info = match[1]
    const rendered = fence(tokens, idx, options, env, self)
    return (
      '<div class="zett-code">' +
      `<p class="zett-code__title">${md.utils.escapeHtml(match[2])}</p>` +
      `${rendered}</div>`
    )
  }
}
