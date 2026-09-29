import { expect, it } from 'vitest'
import { PAGE_SESSION_PREFIX, belongsToTab, pageKey } from './page-sessions'

it('assigns separate conversations to distinct pages and Zett servers', () => {
  const one = pageKey('http://127.0.0.1:6280', 7, 'https://example.com/article#intro')
  expect(one).toBe(pageKey('http://127.0.0.1:6280/', 7, 'https://example.com/article#section'))
  expect(one).not.toBe(pageKey('http://127.0.0.1:6280', 7, 'https://example.com/other'))
  expect(one).not.toBe(pageKey('http://127.0.0.1:6280', 8, 'https://example.com/article'))
  expect(one).not.toBe(pageKey('http://127.0.0.1:6281', 7, 'https://example.com/article'))
  expect(pageKey('http://127.0.0.1:6280', 7, 'chrome://extensions')).toBeNull()
})

it('uses an independent storage key per page', () => {
  const key = pageKey('http://localhost:6280', 5, 'https://example.com')!
  expect(key.startsWith(PAGE_SESSION_PREFIX)).toBe(true)
  expect(JSON.parse(key.slice(PAGE_SESSION_PREFIX.length))).toEqual([
    'http://localhost:6280', 5, 'https://example.com/',
  ])
  expect(belongsToTab(key, 5)).toBe(true)
  expect(belongsToTab(key, 6)).toBe(false)
  expect(belongsToTab('pageSession:broken', 5)).toBe(false)
})
