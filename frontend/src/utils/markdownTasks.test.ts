import MarkdownIt from 'markdown-it'
import { describe, expect, it } from 'vitest'
import { markdownTasks, toggleTask } from './markdownTasks'

const render = (source: string) => new MarkdownIt({ breaks: true }).use(markdownTasks).render(source)

describe('task lists', () => {
  it('draws open and finished tasks as boxes and removes the bracket text', () => {
    const html = render('- [ ] write\n- [x] ship\n- plain')

    expect(html).toContain('class="task-box" role="checkbox" aria-checked="false"')
    expect(html).toContain('class="task-box checked" role="checkbox" aria-checked="true"')
    expect(html).not.toContain('[ ]')
    expect(html).not.toContain('[x]')
    expect(html).toContain('write')
    expect(html.match(/task-list-item/gu)).toHaveLength(2)
    expect(html).toContain('<li>plain</li>')
  })

  it('numbers the tasks in reading order, nested ones included', () => {
    const html = render('- [ ] a\n  - [x] b\n- [ ] c')
    expect([...html.matchAll(/data-task="(\d+)"/gu)].map((match) => match[1])).toEqual(['0', '1', '2'])
  })

  it('leaves brackets that are not a task alone', () => {
    expect(render('- [link](x)\n- [ ]nospace\n')).not.toContain('task-box')
    expect(render('[ ] not in a list')).not.toContain('task-box')
  })

  it('accepts a capital X', () => {
    expect(render('- [X] done')).toContain('aria-checked="true"')
  })
})

describe('toggling a task in the source', () => {
  it('flips exactly the nth task line', () => {
    const source = '- [ ] a\n- [x] b\n- [ ] c'
    expect(toggleTask(source, 0)).toBe('- [x] a\n- [x] b\n- [ ] c')
    expect(toggleTask(source, 1)).toBe('- [ ] a\n- [ ] b\n- [ ] c')
    expect(toggleTask(source, 2)).toBe('- [ ] a\n- [x] b\n- [x] c')
  })

  it('keeps indentation, the marker, and the rest of the line', () => {
    expect(toggleTask('  * [ ] keep **this**', 0)).toBe('  * [x] keep **this**')
  })

  it('does nothing for a task that is not there', () => {
    expect(toggleTask('- [ ] a', 5)).toBe('- [ ] a')
    expect(toggleTask('plain', 0)).toBe('plain')
  })
})
