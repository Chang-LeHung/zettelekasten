// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import AskUserPrompt from './AskUserPrompt.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

it('allows an image-only ask_user response and previews the image', async () => {
  const removeImage = vi.fn()
  const previewImage = vi.fn()
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(AskUserPrompt, {
    question: 'Which screenshot should I inspect?',
    options: ['First', 'Second'],
    allowMultiple: false,
    selectedOptions: [],
    answer: '',
    images: [{
      id: 'image-1',
      type: 'image',
      name: 'clipboard.png',
      mime_type: 'image/png',
      content_url: 'data:image/png;base64,aW1hZ2U=',
      position: 0,
    }],
    submitting: false,
    onRemoveImage: removeImage,
    onPreviewImage: previewImage,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  expect(host.querySelector<HTMLImageElement>('.ask-images img')?.alt).toBe('clipboard.png')
  expect(host.querySelector<HTMLButtonElement>('.ask-submit')?.disabled).toBe(false)

  host.querySelector<HTMLButtonElement>('.ask-image-preview')?.click()
  expect(previewImage).toHaveBeenCalledWith({
    name: 'clipboard.png',
    url: 'data:image/png;base64,aW1hZ2U=',
  })

  host.querySelector<HTMLButtonElement>('.ask-image-remove')?.click()
  expect(removeImage).toHaveBeenCalledWith('image-1')
})
