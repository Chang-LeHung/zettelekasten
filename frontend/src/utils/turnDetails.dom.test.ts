// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { TurnDetailsVisibility } from './turnDetails'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

/** Mirror the turn panel binding used by App.vue against a real details element. */
function turnPanel() {
  const running = ref(true)
  const visibility = new TurnDetailsVisibility()
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(
    defineComponent({
      setup: () => () =>
        h(
          'details',
          { open: visibility.isOpen('turn-0', running.value) },
          [
            h(
              'summary',
              {
                onClick: (event: MouseEvent) => {
                  const details = (event.currentTarget as HTMLElement).closest('details')
                  if (details instanceof HTMLDetailsElement) visibility.setOpen('turn-0', !details.open)
                },
              },
              'Processed in 5s',
            ),
          ],
        ),
    }),
  )
  app.mount(host)
  cleanups.push(() => {
    app.unmount()
    host.remove()
  })
  return { host, running, visibility }
}

function panel(host: HTMLElement): HTMLDetailsElement {
  return host.querySelector('details')!
}

describe('turn execution disclosure', () => {
  it('renders open while the turn streams', async () => {
    const { host } = turnPanel()
    await nextTick()

    expect(panel(host).open).toBe(true)
  })

  it('collapses as soon as the final assistant message arrives', async () => {
    const { host, running } = turnPanel()
    await nextTick()
    expect(panel(host).open).toBe(true)

    running.value = false
    await nextTick()

    expect(panel(host).open).toBe(false)
  })

  it('keeps the panel open when the reader expands a finished turn', async () => {
    const { host, running } = turnPanel()
    running.value = false
    await nextTick()
    expect(panel(host).open).toBe(false)

    const summary = host.querySelector('summary')!
    summary.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    panel(host).open = true
    running.value = true
    await nextTick()
    running.value = false
    await nextTick()

    expect(panel(host).open).toBe(true)
  })

  it('keeps the panel closed when the reader collapses a streaming turn', async () => {
    const { host, running } = turnPanel()
    await nextTick()

    const summary = host.querySelector('summary')!
    summary.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    panel(host).open = false
    running.value = false
    await nextTick()

    expect(panel(host).open).toBe(false)
  })
})
