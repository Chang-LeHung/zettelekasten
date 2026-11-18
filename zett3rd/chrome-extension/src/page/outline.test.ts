// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearOutline, outlinedElement, showOutline } from './outline'

const HOST_ID = 'zettelekasten-outline-host'

beforeEach(() => {
  document.body.innerHTML = '<button id="target">Save</button><button id="far">Far</button>'
})

afterEach(() => {
  clearOutline()
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
  const box = host.firstElementChild as HTMLElement
  expect(box.style.left).toBe('20px')
  expect(box.style.top).toBe('30px')
  expect(box.style.width).toBe('120px')
  expect(outlinedElement()).toBe(target)
})

it('hides itself for an element that is off screen, and stops with clear', () => {
  const far = document.querySelector('#far')!
  place(far, { left: 0, top: -400, width: 80, height: 20, right: 80, bottom: -380 })
  showOutline(far, 0)
  const box = document.getElementById(HOST_ID)!.firstElementChild as HTMLElement
  expect(box.style.display).toBe('none')
  clearOutline()
  expect(document.getElementById(HOST_ID)).toBeNull()
  expect(outlinedElement()).toBeNull()
})

it('removes itself when its time is up', () => {
  vi.useFakeTimers()
  try {
    showOutline(document.querySelector('#target')!, 500)
    expect(document.getElementById(HOST_ID)).not.toBeNull()
    vi.advanceTimersByTime(600)
    expect(document.getElementById(HOST_ID)).toBeNull()
  } finally {
    vi.useRealTimers()
  }
})

it('replaces the previous outline instead of stacking a second one', () => {
  showOutline(document.querySelector('#target')!, 0)
  showOutline(document.querySelector('#far')!, 0)
  expect(document.querySelectorAll(`#${HOST_ID}`)).toHaveLength(1)
  expect(outlinedElement()).toBe(document.querySelector('#far'))
})
