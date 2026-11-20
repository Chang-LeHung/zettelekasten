import { expect, it } from 'vitest'
import { splitPath, toolSummary } from './toolSummary'

it('names the file a file tool acts on and keeps the folder as context', () => {
  expect(toolSummary('read', { file_path: 'frontend/src/utils/toolSummary.ts', offset: 10, limit: 5 })).toEqual({
    label: 'Read', target: 'toolSummary.ts', context: 'src/utils', kind: 'file', meta: 'L10–14',
  })
  expect(toolSummary('edit', { file_path: '/a/b.ts', replace_all: true }).meta).toBe('all matches')
  expect(toolSummary('write_file', { file_path: 'notes.md' })).toMatchObject({ label: 'Write', target: 'notes.md', context: '' })
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
