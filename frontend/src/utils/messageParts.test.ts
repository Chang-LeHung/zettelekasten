import { describe, expect, it } from 'vitest'

import type { PositionedMessageImage } from './messageParts'
import { buildMessageParts, displayMessageParts, rebaseImagePositions } from './messageParts'

function image(id: string, position: number): PositionedMessageImage {
  return {
    id,
    type: 'image',
    name: `${id}.png`,
    mime_type: 'image/png',
    data_base64: id,
    content_url: `data:image/png;base64,${id}`,
    position,
  }
}

describe('message parts', () => {
  it('preserves text-image-text order from the paste caret', () => {
    expect(buildMessageParts('beforeafter', [image('middle', 6)])).toEqual([
      { type: 'text', text: 'before' },
      { type: 'image', name: 'middle.png', mime_type: 'image/png', data_base64: 'middle' },
      { type: 'text', text: 'after' },
    ])
  })

  it('keeps insertion order for multiple images at the same caret', () => {
    expect(buildMessageParts('text', [image('first', 0), image('second', 0)]).map((part) => part.type === 'image' ? part.name : part.text)).toEqual([
      'first.png',
      'second.png',
      'text',
    ])
  })

  it('rebases image anchors when text is inserted or removed before them', () => {
    expect(rebaseImagePositions([image('one', 3)], 'abcdef', 'aXXbcdef')[0]?.position).toBe(5)
    expect(rebaseImagePositions([image('one', 3)], 'abcdef', 'adef')[0]?.position).toBe(1)
  })

  it('creates display parts without changing their order', () => {
    const pasted = image('one', 1)
    const request = buildMessageParts('ab', [pasted])
    expect(displayMessageParts(request, [pasted])).toEqual([
      { type: 'text', text: 'a' },
      {
        type: 'image',
        name: 'one.png',
        mime_type: 'image/png',
        content_url: 'data:image/png;base64,one',
      },
      { type: 'text', text: 'b' },
    ])
  })
})
