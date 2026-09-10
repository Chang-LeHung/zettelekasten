import type { MessageContentPart, MessageImagePartInput, MessagePartInput } from '../api/types'

export interface PositionedMessageImage extends MessageImagePartInput {
  id: string
  content_url: string
  position: number
}

/** Interleave pasted images with text using their textarea caret offsets. */
export function buildMessageParts(
  text: string,
  images: readonly PositionedMessageImage[],
): MessagePartInput[] {
  if (!images.length) return text ? [{ type: 'text', text }] : []
  const ordered = images
    .map((image, index) => ({ image, index }))
    .sort((left, right) => left.image.position - right.image.position || left.index - right.index)
  const parts: MessagePartInput[] = []
  let cursor = 0
  for (const { image } of ordered) {
    const position = Math.min(text.length, Math.max(cursor, image.position))
    if (position > cursor) parts.push({ type: 'text', text: text.slice(cursor, position) })
    parts.push({
      type: 'image',
      name: image.name,
      mime_type: image.mime_type,
      data_base64: image.data_base64,
    })
    cursor = position
  }
  if (cursor < text.length) parts.push({ type: 'text', text: text.slice(cursor) })
  return parts
}

/** Replace transport-only base64 fields with browser display URLs. */
export function displayMessageParts(
  parts: readonly MessagePartInput[],
  images: readonly PositionedMessageImage[],
): MessageContentPart[] {
  return parts.map((part) => {
    if (part.type === 'text') return part
    const pending = images.find((image) => image.data_base64 === part.data_base64 && image.name === part.name)
    return {
      type: 'image',
      name: part.name,
      mime_type: part.mime_type,
      content_url: pending?.content_url || '',
    }
  })
}

/** Keep image anchors stable when the textarea content changes around them. */
export function rebaseImagePositions(
  images: readonly PositionedMessageImage[],
  previous: string,
  next: string,
): PositionedMessageImage[] {
  let prefix = 0
  while (prefix < previous.length && prefix < next.length && previous[prefix] === next[prefix]) prefix += 1
  let suffix = 0
  while (
    suffix < previous.length - prefix
    && suffix < next.length - prefix
    && previous[previous.length - suffix - 1] === next[next.length - suffix - 1]
  ) suffix += 1
  const previousEnd = previous.length - suffix
  const nextEnd = next.length - suffix
  return images.map((image) => {
    if (image.position < prefix) return image
    if (image.position >= previousEnd) {
      return { ...image, position: Math.max(0, image.position + nextEnd - previousEnd) }
    }
    return { ...image, position: nextEnd }
  })
}
