// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearOutline, outlinedElement, showOutline } from './outline'

const HOST_ID = 'zettelekasten-outline-host'

beforeEach(() => {
  document.body.innerHTML = '<button id="target">Save</button><button id="far">Far</button>'
})

afterEach(() => {
  clearOutline()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function place(element: Element, rect: Partial<DOMRect>) {
  element.getBoundingClientRect = () => ({
    x: 0, y: 0, left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0,
    toJSON: () => ({}), ...rect,
  }) as DOMRect
}

it('draws an outline over the element it was given', () => {
  const target = document.querySelector('#target')!
  place(target, { left: 20, top: 30, width: 120, height: 40, right: 140, bottom: 70 })
  showOutline(target, 0)
  const host = document.getElementById(HOST_ID)!
  expect(host).not.toBeNull()
  expect(host.style.getPropertyValue('pointer-events')).toBe('none')
  expect(host.style.getPropertyValue('display')).toBe('block')
  const box = host.firstElementChild as HTMLElement
  expect(box.style.left).toBe('20px')
  expect(box.style.top).toBe('30px')
  expect(box.style.width).toBe('120px')
  expect(outlinedElement()).toBe(target)
})

it('hides itself for an element that is off screen or covered by the panel, and stops with clear', () => {
  const target = document.querySelector('#target')!
  place(target, { left: 1200, top: 300, width: 80, height: 20, right: 1280, bottom: 320 })
  // The panel sits over the right edge of this viewport.
  showOutline(target, 0, () => ({ left: 900, top: 0, right: 1440, bottom: 700, width: 540, height: 700 }) as DOMRect)
  const box = document.getElementById(HOST_ID)!.firstElementChild as HTMLElement
  expect(box.style.display).toBe('none')

  // A panel that covers only part of a wide element is not a reason to hide it.
  const wide = document.querySelector('#far')!
  place(wide, { left: 700, top: 300, width: 600, height: 20, right: 1300, bottom: 320 })
  showOutline(wide, 0, () => ({ left: 900, top: 0, right: 1440, bottom: 700, width: 540, height: 700 }) as DOMRect)
  expect((document.getElementById(HOST_ID)!.firstElementChild as HTMLElement).style.display).toBe('block')

  // A zero-size panel is an absent panel, not a cover.
  showOutline(wide, 0, () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }) as DOMRect)
  expect((document.getElementById(HOST_ID)!.firstElementChild as HTMLElement).style.display).toBe('block')

  const onScreen = document.querySelector('#far')!
  place(onScreen, { left: 20, top: 300, width: 80, height: 20, right: 100, bottom: 320 })
  showOutline(onScreen, 0)
  expect((document.getElementById(HOST_ID)!.firstElementChild as HTMLElement).style.display).toBe('block')
  clearOutline()
  expect(document.getElementById(HOST_ID)).toBeNull()
  expect(outlinedElement()).toBeNull()
})

it('removes itself when its time is up', () => {
  vi.useFakeTimers()
  showOutline(document.querySelector('#target')!, 500)
  expect(document.getElementById(HOST_ID)).not.toBeNull()
  vi.advanceTimersByTime(600)
  expect(document.getElementById(HOST_ID)).toBeNull()
})

it('bounds a card outline even when no clear ever arrives', () => {
  vi.useFakeTimers()
  // The consent path's lifetime: a card whose clear is lost still goes away.
  showOutline(document.querySelector('#target')!, 100_000)
  vi.advanceTimersByTime(99_000)
  expect(document.getElementById(HOST_ID)).not.toBeNull()
  vi.advanceTimersByTime(2_000)
  expect(document.getElementById(HOST_ID)).toBeNull()
})

it('stops refreshing once it is cleared', () => {
  vi.useFakeTimers()
  const target = document.querySelector('#target')!
  const rect = vi.spyOn(target, 'getBoundingClientRect')
  showOutline(target, 0)
  const readsWhileOpen = rect.mock.calls.length
  clearOutline()
  vi.advanceTimersByTime(2000)
  expect(rect.mock.calls.length).toBe(readsWhileOpen)
})

it('heals a stale host instead of stacking a second one', () => {
  const stale = document.createElement('div')
  stale.id = HOST_ID
  document.documentElement.appendChild(stale)
  showOutline(document.querySelector('#target')!, 0)
  expect(document.querySelectorAll(`#${HOST_ID}`)).toHaveLength(1)
  expect(document.getElementById(HOST_ID)).not.toBe(stale)
})

it('drops the outline when the page removes the target or our own node', () => {
  const target = document.querySelector('#target')!
  showOutline(target, 0)
  target.remove()
  // Any refresh path notices; a scroll is the cheapest one to trigger.
  window.dispatchEvent(new Event('scroll'))
  expect(document.getElementById(HOST_ID)).toBeNull()

  showOutline(document.querySelector('#far')!, 0)
  document.getElementById(HOST_ID)!.remove()
  window.dispatchEvent(new Event('scroll'))
  expect(document.getElementById(HOST_ID)).toBeNull()
  expect(outlinedElement()).toBeNull()
})

it('replaces the previous outline instead of stacking a second one', () => {
  showOutline(document.querySelector('#target')!, 0)
  showOutline(document.querySelector('#far')!, 0)
  expect(document.querySelectorAll(`#${HOST_ID}`)).toHaveLength(1)
  expect(outlinedElement()).toBe(document.querySelector('#far'))
})
