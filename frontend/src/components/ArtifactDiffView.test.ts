// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it } from 'vitest'
import type { CardArtifactContent } from '../api/types'
import { i18nPlugin } from '../i18n'
import { diffArtifactContent } from '../utils/artifactDiff'
import ArtifactDiffView from './ArtifactDiffView.vue'

const cleanups: (() => void)[] = []

afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
})

function card(changes: Partial<CardArtifactContent> = {}): CardArtifactContent {
  return {
    artifact_type: 'card',
    card_type: 'note',
    title: 'Card title',
    summary: 'Card summary',
    content: 'First line\nSecond line',
    suggested_tags: [],
    keywords: [],
    ...changes,
  }
}

function mount(published: CardArtifactContent, draft: CardArtifactContent) {
  const diff = diffArtifactContent(published, draft)
  if (!diff) throw new Error('Expected the card diff to be comparable')
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(ArtifactDiffView, { diff }) })
  app.use(i18nPlugin)
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return host
}

it('marks changed fields and renders removed and added lines', async () => {
  const host = mount(card(), card({ title: 'New title', content: 'First line\nRewritten' }))
  await nextTick()

  const sections = [...host.querySelectorAll<HTMLElement>('.artifact-diff-field')]
  expect(sections.map(section => section.classList.contains('changed'))).toEqual([true, false, false, true])
  expect(sections[0].querySelector('header')?.textContent).toContain('changed')
  expect(sections[1].querySelector('header')?.textContent).toContain('unchanged')

  const body = sections.at(-1)?.textContent ?? ''
  expect(body).toContain('−Second line')
  expect(body).toContain('+Rewritten')
  expect(body).toContain(' First line')
  expect(body).not.toContain('The draft matches the saved artifact.')
})

it('reports a draft that matches the saved artifact', async () => {
  const host = mount(card(), card())
  await nextTick()

  expect(host.textContent).toContain('The draft matches the saved artifact.')
  expect(host.querySelectorAll('.artifact-diff-body')).toHaveLength(0)
})
