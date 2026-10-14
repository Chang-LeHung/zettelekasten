import type { TurnTarget } from './markdownBlocks'

export type CommandGroup = 'basic' | 'media' | 'advanced' | 'slides'

/**
 * One entry of the `/` menu. Labels and hints live in the message catalog under
 * `editor.cmd.<id>` and `editor.cmd.<id>.hint`, so the menu reads in either
 * language; `keywords` are extra words to match, in both languages.
 */
export interface BlockCommand {
  id: string
  group: CommandGroup
  /** Short glyph drawn in the item's icon tile. */
  glyph: string
  keywords: readonly string[]
  /** Markdown the command inserts. */
  template: string
  /** Where the caret lands inside `template`; the end by default. */
  caret?: number
  /** Re-style the current block instead of inserting a new one, when it already has words. */
  turn?: TurnTarget
  /** Only offered while editing a slide deck. */
  slidesOnly?: boolean
  /** Only offered outside a slide deck. */
  proseOnly?: boolean
}

const after = (template: string, marker: string): number => template.indexOf(marker) + marker.length

const MERMAID = '```mermaid\ngraph TD\n  A[Start] --> B[Next]\n```'
const TABLE = '| Column | Column |\n| --- | --- |\n|  |  |'
const COVER = '<!-- slide:cover -->\n# Title\n\n## Subtitle\n\nAuthor'

export const BLOCK_COMMANDS: readonly BlockCommand[] = [
  { id: 'text', group: 'basic', glyph: 'Aa', keywords: ['paragraph', 'plain', 'text', '正文', '文本', '段落'], template: '', turn: 'paragraph' },
  { id: 'h1', group: 'basic', glyph: 'H1', keywords: ['heading', 'title', 'h1', '#', '标题', '一级'], template: '# ', turn: 'h1' },
  { id: 'h2', group: 'basic', glyph: 'H2', keywords: ['heading', 'subtitle', 'h2', '##', '标题', '二级'], template: '## ', turn: 'h2' },
  { id: 'h3', group: 'basic', glyph: 'H3', keywords: ['heading', 'h3', '###', '标题', '三级'], template: '### ', turn: 'h3' },
  { id: 'bullet', group: 'basic', glyph: '•', keywords: ['list', 'bullet', 'ul', 'unordered', '列表', '无序'], template: '- ', turn: 'bullet' },
  { id: 'numbered', group: 'basic', glyph: '1.', keywords: ['list', 'number', 'ol', 'ordered', '列表', '有序', '编号'], template: '1. ', turn: 'numbered' },
  { id: 'todo', group: 'basic', glyph: '☐', keywords: ['todo', 'task', 'checkbox', 'check', '待办', '任务', '清单'], template: '- [ ] ', turn: 'todo' },
  { id: 'quote', group: 'basic', glyph: '”', keywords: ['quote', 'blockquote', 'cite', '引用', '引述'], template: '> ', turn: 'quote' },
  { id: 'callout', group: 'basic', glyph: '💡', keywords: ['callout', 'note', 'tip', 'info', '提示', '标注', '高亮'], template: '> 💡 ' },
  { id: 'divider', group: 'basic', glyph: '—', keywords: ['divider', 'rule', 'hr', 'line', '分割线', '分隔'], template: '---', proseOnly: true },
  { id: 'image', group: 'media', glyph: '▣', keywords: ['image', 'figure', 'picture', 'photo', 'img', '图片', '插图', '图'], template: '![alt text](https://)', caret: after('![alt text](', '('), },
  { id: 'code', group: 'advanced', glyph: '</>', keywords: ['code', 'snippet', 'fence', 'program', '代码', '代码块'], template: '```\n\n```', caret: 4, turn: 'code' },
  { id: 'diagram', group: 'advanced', glyph: '◇', keywords: ['mermaid', 'diagram', 'chart', 'flow', 'graph', '图表', '流程图', '架构'], template: MERMAID, caret: after(MERMAID, 'graph TD\n  ') },
  { id: 'math', group: 'advanced', glyph: 'Σ', keywords: ['math', 'equation', 'latex', 'katex', 'formula', '公式', '数学'], template: '$$\n\n$$', caret: 3 },
  { id: 'table', group: 'advanced', glyph: '▦', keywords: ['table', 'grid', 'columns', '表格'], template: TABLE, caret: 2 },
  { id: 'slide', group: 'slides', glyph: '▭', keywords: ['slide', 'page', 'next', 'vertical', '幻灯片', '下一页', '新页'], template: '--', slidesOnly: true },
  { id: 'section', group: 'slides', glyph: '▬', keywords: ['section', 'chapter', 'horizontal', '章节', '新章节', '小节'], template: '---', slidesOnly: true },
  { id: 'cover', group: 'slides', glyph: '★', keywords: ['cover', 'title slide', 'opening', '封面'], template: COVER, caret: after(COVER, '# '), slidesOnly: true },
  { id: 'htmlSlide', group: 'slides', glyph: '<>', keywords: ['html', 'custom', 'layout', '自定义', '版式'], template: '<!-- slide:html -->\n<div>\n  <h1>Title</h1>\n</div>', caret: after('<!-- slide:html -->\n<div>\n  <h1>', '<h1>'), slidesOnly: true },
]

/** The commands that apply to this document, in menu order. */
export function commandsFor(slides: boolean): BlockCommand[] {
  return BLOCK_COMMANDS.filter((command) => (slides ? !command.proseOnly : !command.slidesOnly))
}

const GROUP_ORDER: readonly CommandGroup[] = ['slides', 'basic', 'media', 'advanced']

/**
 * Commands matching what was typed after the slash. An empty query lists
 * everything; otherwise a label that starts with the query beats a keyword that
 * starts with it, which beats any word that merely contains it.
 */
export function filterCommands(
  query: string,
  slides: boolean,
  labelOf: (command: BlockCommand) => string,
): BlockCommand[] {
  const available = commandsFor(slides)
  const needle = query.trim().toLowerCase()
  const order = (command: BlockCommand) => GROUP_ORDER.indexOf(command.group)
  if (!needle) return [...available].sort((a, b) => order(a) - order(b))
  const scored: Array<{ command: BlockCommand; score: number; index: number }> = []
  available.forEach((command, index) => {
    const label = labelOf(command).toLowerCase()
    const words = [command.id, ...command.keywords].map((word) => word.toLowerCase())
    let score = 0
    if (label.startsWith(needle) || command.id.startsWith(needle)) score = 4
    else if (words.some((word) => word.startsWith(needle))) score = 3
    else if (label.includes(needle)) score = 2
    else if (words.some((word) => word.includes(needle))) score = 1
    if (score) scored.push({ command, score, index })
  })
  return scored.sort((a, b) => b.score - a.score || a.index - b.index).map((entry) => entry.command)
}
