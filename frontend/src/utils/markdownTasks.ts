import type MarkdownIt from 'markdown-it'

const TASK_PREFIX = /^\[([ xX])\][ \t]+/u

/**
 * Show `- [ ] item` and `- [x] item` as checkboxes.
 *
 * The box is a `<span>`, not an `<input>`: the sanitizer strips form controls,
 * and a span can carry the state (`aria-checked`) plus the task's position in
 * its block (`data-task`), which is how the editor knows which line to flip when
 * a box is clicked.
 */
export function markdownTasks(md: InstanceType<typeof MarkdownIt>): void {
  md.core.ruler.after('inline', 'zett_tasks', (state) => {
    let task = 0
    for (let index = 0; index < state.tokens.length; index += 1) {
      const item = state.tokens[index]
      if (item?.type !== 'list_item_open') continue
      const inline = state.tokens.slice(index + 1, index + 4).find((token) => token.type === 'inline')
      const first = inline?.children?.[0]
      if (!inline || !first || first.type !== 'text') continue
      const match = TASK_PREFIX.exec(first.content)
      if (!match) continue
      const done = match[1] !== ' '
      first.content = first.content.slice(match[0].length)
      inline.content = inline.content.slice(match[0].length)
      const box = new state.Token('html_inline', '', 0)
      box.content = `<span class="task-box${done ? ' checked' : ''}" role="checkbox" aria-checked="${done}" aria-readonly="true" data-task="${task}"></span>`
      inline.children!.unshift(box)
      item.attrJoin('class', done ? 'task-list-item task-done' : 'task-list-item')
      task += 1
    }
  })
}

const TASK_LINE = /^([ \t]*[-*+][ \t]+\[)([ xX])(\][ \t])/u

/** Flip the nth task line of a block's source, leaving every other character alone. */
export function toggleTask(text: string, which: number): string {
  let seen = 0
  return text
    .split('\n')
    .map((line) => {
      const match = TASK_LINE.exec(line)
      if (!match) return line
      const current = seen
      seen += 1
      if (current !== which) return line
      return `${match[1]}${match[2] === ' ' ? 'x' : ' '}${line.slice(match[0].length - match[3]!.length)}`
    })
    .join('\n')
}
