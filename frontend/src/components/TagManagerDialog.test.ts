// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import type { Tag } from '../api/types'
import TagManagerDialog from './TagManagerDialog.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

const tags: Tag[] = [{
  id: 'engineering',
  path: 'Engineering',
  normalized_path: 'engineering',
  name: 'Engineering',
  parent_id: null,
  description: null,
  color: null,
  direct_count: 0,
  total_count: 1,
  created_at: '',
  updated_at: '',
  children: [{
    id: 'python',
    path: 'Engineering/Python',
    normalized_path: 'engineering/python',
    name: 'Python',
    parent_id: 'engineering',
    description: null,
    color: null,
    direct_count: 1,
    total_count: 1,
    created_at: '',
    updated_at: '',
    children: [],
  }],
}]

it('submits hierarchical paths and exposes deletion for every visible tag', async () => {
  const create = vi.fn()
  const remove = vi.fn()
  const feedback = ref('')
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () => h(TagManagerDialog, {
      tags,
      busy: false,
      feedback: feedback.value,
      feedbackKind: 'success',
      onCreate: create,
      onDelete: remove,
    }),
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  const input = document.body.querySelector<HTMLInputElement>('#tag-path')!
  input.value = ' Engineering / Python / Asyncio '
  input.dispatchEvent(new Event('input', { bubbles: true }))
  document.body.querySelector<HTMLFormElement>('.tag-create-form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await nextTick()

  expect(create).toHaveBeenCalledWith('Engineering / Python / Asyncio')
  feedback.value = 'Created “Engineering/Python/Asyncio”.'
  await nextTick()
  expect(document.body.querySelector('[role="status"]')?.textContent).toContain('Created “Engineering/Python/Asyncio”.')
  expect(input.value).toBe('')
  expect(document.body.querySelectorAll('.managed-tag')).toHaveLength(2)

  document.body.querySelector<HTMLButtonElement>('[aria-label="Delete Engineering/Python"]')!.click()
  expect(remove).toHaveBeenCalledWith(expect.objectContaining({ id: 'python', path: 'Engineering/Python' }))
})
