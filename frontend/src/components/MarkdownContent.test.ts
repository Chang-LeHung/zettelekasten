// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { compileStyle, parse } from '@vue/compiler-sfc'
import { afterEach, expect, it, vi } from 'vitest'
import MarkdownContent from './MarkdownContent.vue'
import SlidesMarkdownContent from './SlidesMarkdownContent.vue'
import source from './MarkdownContent.vue?raw'

vi.mock('../utils/mermaidRenderer', () => ({
  renderMermaid: vi.fn().mockResolvedValue({
    svg: '<svg viewBox="0 0 20 10"><text x="1" y="8">diagram</text></svg>',
  }),
}))

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

async function mount(component: typeof MarkdownContent | typeof SlidesMarkdownContent, props: Record<string, unknown>) {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(component, props) })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()
  await Promise.resolve()
  await nextTick()
  return host
}

it('keeps authored HTML exclusive to slide Markdown', async () => {
  const ordinary = await mount(MarkdownContent, { content: '<div class="layout">ordinary</div>' })
  expect(ordinary.querySelector('.layout')).toBeNull()
  expect(ordinary.textContent).toContain('ordinary</div>')

  const slides = await mount(SlidesMarkdownContent, { content: '<div class="layout">slide</div>' })
  expect(slides.querySelector('.layout')?.textContent).toBe('slide')
  expect(slides.querySelector('.presentation-markdown')).not.toBeNull()
})

it('renders a language header and copy-only action for fenced code', async () => {
  const host = await mount(MarkdownContent, { content: '```python\nprint("hello")\n```' })
  expect(host.querySelector('.code-language')?.textContent).toBe('Python')
  expect(host.querySelector('[data-code-copy]')?.getAttribute('aria-label')).toBe('Copy code')
  expect(host.textContent).not.toContain('Run')
  expect(host.querySelector('code')?.classList.contains('language-python')).toBe(true)
})

it('labels every fence the shared registry resolves, including LaTeX', async () => {
  const latex = await mount(MarkdownContent, { content: '```tex\n\\frac{1}{2}\n```' })
  expect(latex.querySelector('.code-language')?.textContent).toBe('LaTeX')
  expect(latex.querySelector('code')?.classList.contains('language-latex')).toBe(true)

  const graphql = await mount(MarkdownContent, { content: '```graphql\n{ me { id } }\n```' })
  expect(graphql.querySelector('.code-language')?.textContent).toBe('GraphQL')
})

it('renders Mermaid after the Markdown DOM is committed', async () => {
  const host = await mount(MarkdownContent, { content: '```mermaid\ngraph TD\nA-->B\n```' })
  expect(host.querySelector('[data-mermaid-canvas] svg')).not.toBeNull()
  expect(host.querySelector('[data-mermaid-canvas]')?.textContent).toContain('diagram')
})

it('opens Markdown images in a preview dialog', async () => {
  const host = await mount(MarkdownContent, {
    content: '![Architecture diagram](data:image/png;base64,aW1hZ2U=)',
  })
  const image = host.querySelector<HTMLImageElement>('.markdown-body img')
  expect(image).not.toBeNull()

  image?.click()
  await nextTick()

  const dialog = document.body.querySelector('.markdown-image-preview-dialog')
  expect(dialog?.getAttribute('aria-label')).toBe('Preview Architecture diagram')
  expect(dialog?.querySelector<HTMLImageElement>('img')?.src).toBe('data:image/png;base64,aW1hZ2U=')

  dialog?.querySelector<HTMLButtonElement>('[aria-label="Close image preview"]')?.click()
  await nextTick()
  expect(document.body.querySelector('.markdown-image-preview-dialog')).toBeNull()
})

it('isolates Mermaid diagrams from the application icon SVG stroke', () => {
  const { descriptor } = parse(source)
  const { code, errors } = compileStyle({ source: descriptor.styles[0].content, filename: 'MarkdownContent.vue', id: 'data-v-test', scoped: true })
  expect(errors).toEqual([])
  expect(code).toMatch(/\.markdown-body\[data-v-test\]\s+\.mermaid-canvas\s*>\s*svg\s*\{/u)
  expect(code).toMatch(/width:\s*auto\s*!important/u)
  expect(code).toMatch(/max-height:\s*32rem/u)
  expect(code).toContain('stroke: initial')
  expect(code).toContain('stroke-width: initial')
})
