import { expect, it } from 'vitest'
import { splitPath, toolSummary } from './toolSummary'

it('names the file a file tool acts on and keeps the folder as context', () => {
  expect(toolSummary('read', { path: 'frontend/src/utils/toolSummary.ts', start_line: 10, line_count: 5 })).toEqual({
    label: 'Read', target: 'toolSummary.ts', context: 'src/utils', kind: 'file', meta: 'L10–14',
  })
  expect(toolSummary('read_file', { path: 'a/b.ts', start_line: 3 })).toMatchObject({ label: 'Read', meta: 'from L3' })
  expect(toolSummary('edit', { path: '/a/b.ts', edits: [{ old_text: 'x', new_text: 'y', replace_all: true }] }).meta).toBe('all matches')
  expect(toolSummary('edit', { path: '/a/b.ts', edits: [{}, {}, {}] }).meta).toBe('3 edits')
  expect(toolSummary('write_file', { path: 'notes.md' })).toMatchObject({ label: 'Write', target: 'notes.md', context: '' })
})

it('shows the first line of a command and the query of a search', () => {
  expect(toolSummary('bash', { command: '\ngit status --short\nls' })).toMatchObject({ label: 'Bash', target: 'git status --short', kind: 'command' })
  expect(toolSummary('tool_search', { query: 'scheduled task' })).toMatchObject({ target: 'scheduled task', kind: 'text' })
})

it('falls back to the plain tool name while arguments are still streaming', () => {
  expect(toolSummary('some_new_tool', undefined)).toEqual({ label: 'some new tool', target: '', context: '', kind: 'none', meta: '' })
  expect(toolSummary('read', {})).toMatchObject({ target: '', kind: 'none' })
})

it('splits Windows paths and trailing slashes', () => {
  expect(splitPath('C:\\proj\\src\\a.ts')).toEqual({ name: 'a.ts', context: 'proj/src' })
  expect(splitPath('docs/guide/')).toEqual({ name: 'guide', context: 'docs' })
})
