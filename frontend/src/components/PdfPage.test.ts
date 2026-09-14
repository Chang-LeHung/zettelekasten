// @vitest-environment jsdom
import { compileStyle, parse } from '@vue/compiler-sfc'
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import PdfPage from './PdfPage.vue'
import source from './PdfPage.vue?raw'

vi.mock('pdfjs-dist', () => ({
  TextLayer: class {
    render() { return Promise.resolve() }
    update() {}
    cancel() {}
  },
}))

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('applies text selection styles to dynamically inserted, unscoped PDF text nodes', () => {
  const { descriptor } = parse(source)
  const { code, errors } = compileStyle({ source: descriptor.styles[0].content, filename: 'PdfPage.vue', id: 'data-v-test', scoped: true })
  expect(errors).toEqual([])
  expect(code).toContain('.text-layer[data-v-test] :is(span, br)')
  expect(code).toContain('.text-layer[data-v-test] ::selection')
  expect(code).not.toContain('br)[data-v-test]')
})

it('keeps the visible canvas intact until the offscreen render finishes', async () => {
  vi.stubGlobal('IntersectionObserver', class {
    constructor(private callback: (entries: unknown[]) => void) {}
    observe() { this.callback([{ isIntersecting: true }]) }
    disconnect() {}
  })
  const drawImage = vi.fn()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D)
  let finish!: () => void
  const render = vi.fn(() => ({ promise: new Promise<void>(resolve => { finish = resolve }), cancel: vi.fn() }))
  const page = { getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }), render, streamTextContent: vi.fn() }
  const host = document.createElement('div')
  const app = createApp({ render: () => h(PdfPage, { document: { getPage: async () => page } as never, pageNumber: 1, scale: 1, baseWidth: 600, baseHeight: 800 }) })
  app.mount(host)
  try {
    await nextTick()
    await nextTick()
    const visible = host.querySelector('canvas')!
    const buffer = render.mock.calls[0][0].canvas
    expect(buffer).not.toBe(visible)
    expect(visible.width).toBe(300)
    expect(drawImage).not.toHaveBeenCalled()
    finish()
    await Promise.resolve()
    await nextTick()
    expect(visible.width).toBe(buffer.width)
    expect(drawImage).toHaveBeenCalledWith(buffer, 0, 0)
  } finally {
    app.unmount()
  }
})

it('keeps the previous presentation bitmap visible while the next page renders', async () => {
  vi.stubGlobal('IntersectionObserver', class {
    constructor(private callback: (entries: unknown[]) => void) {}
    observe() { this.callback([{ isIntersecting: true }]) }
    disconnect() {}
  })
  const drawImage = vi.fn()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D)
  const finishes = new Map<number, () => void>()
  const pages = new Map([1, 2].map(pageNumber => [pageNumber, {
    getViewport: ({ scale }: { scale: number }) => ({ width: (500 + pageNumber * 10) * scale, height: 700 * scale }),
    render: vi.fn(() => ({ promise: new Promise<void>(resolve => { finishes.set(pageNumber, resolve) }), cancel: vi.fn() })),
    streamTextContent: vi.fn(),
  }]))
  const pageNumber = ref(1)
  const host = document.createElement('div')
  const app = createApp({
    render: () => h(PdfPage, {
      document: { getPage: async (number: number) => pages.get(number) } as never,
      pageNumber: pageNumber.value,
      scale: 1,
      baseWidth: 500,
      baseHeight: 700,
    }),
  })
  app.mount(host)
  try {
    await nextTick()
    await nextTick()
    const visible = host.querySelector('canvas')!
    finishes.get(1)!()
    await Promise.resolve()
    await nextTick()
    const firstWidth = visible.width
    expect(drawImage).toHaveBeenCalledTimes(1)

    pageNumber.value = 2
    await nextTick()
    await nextTick()
    expect(host.querySelector('canvas')).toBe(visible)
    expect(visible.width).toBe(firstWidth)
    expect(drawImage).toHaveBeenCalledTimes(1)

    finishes.get(2)!()
    await Promise.resolve()
    await nextTick()
    expect(host.querySelector('canvas')).toBe(visible)
    expect(visible.width).not.toBe(firstWidth)
    expect(drawImage).toHaveBeenCalledTimes(2)
  } finally {
    app.unmount()
  }
})
