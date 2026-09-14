// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import PdfPreview from './PdfPreview.vue'

vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }))
vi.mock('./PdfPage.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../api/client', () => ({ aiClient: { getArtifactPdfContent: vi.fn().mockResolvedValue(null) } }))

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

async function mountPreview() {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(PdfPreview, { asset: { id: 'pdf', session_id: 'session' }, artifact: true }) })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()
  return { host, root: host.querySelector<HTMLElement>('.pdf-preview')! }
}

it('resizes with the keyboard and retains width across collapse and expansion', async () => {
  const { host, root } = await mountPreview()
  const separator = host.querySelector<HTMLElement>('[role="separator"]')!
  separator.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
  await nextTick()
  expect(root.style.getPropertyValue('--outline-width')).toBe('260px')
  host.querySelector<HTMLButtonElement>('[aria-label="Collapse document outline"]')!.click()
  await nextTick()
  expect(host.querySelector('.pdf-outline')).toBeNull()
  expect(host.querySelector('[role="separator"]')).toBeNull()
  const toggle = host.querySelector<HTMLButtonElement>('[aria-label="Toggle document outline"]')!
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  toggle.click()
  await nextTick()
  expect(host.querySelector('.pdf-outline')).not.toBeNull()
  expect(root.style.getPropertyValue('--outline-width')).toBe('260px')
})

it('bounds pointer resizing and stops when the pointer is cancelled', async () => {
  const { host, root } = await mountPreview()
  const separator = host.querySelector<HTMLElement>('[role="separator"]')!
  separator.setPointerCapture = vi.fn()
  function pointer(type: string, clientX: number) {
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { pointerId: 1, button: 0, clientX })
    separator.dispatchEvent(event)
  }
  pointer('pointerdown', 240)
  pointer('pointermove', 320)
  await nextTick()
  expect(root.style.getPropertyValue('--outline-width')).toBe('320px')
  pointer('pointermove', 900)
  await nextTick()
  expect(root.style.getPropertyValue('--outline-width')).toBe('480px')
  pointer('pointermove', -900)
  await nextTick()
  expect(root.style.getPropertyValue('--outline-width')).toBe('120px')
  pointer('pointercancel', -900)
  pointer('pointermove', 300)
  await nextTick()
  expect(root.style.getPropertyValue('--outline-width')).toBe('120px')
  expect(root.classList.contains('resizing-outline')).toBe(false)
})
