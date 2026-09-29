import type { MessageImagePart, MessagePart } from '../api/types'

export interface PositionedMessageImage extends MessageImagePart {
  id: string
  position: number
}

/** Read one picked or pasted image into the data URL a message part carries. */
export function readMessageImage(file: File, position: number): Promise<PositionedMessageImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error(`Unable to read ${file.name}`))
    reader.onload = () => {
      const contentUrl = typeof reader.result === 'string' ? reader.result : ''
      const separator = contentUrl.indexOf(',')
      if (separator < 0) {
        reject(new Error(`Unable to encode ${file.name}`))
        return
      }
      resolve({
        id: crypto.randomUUID(),
        type: 'image',
        name: file.name || 'Pasted image',
        mime_type: file.type,
        content_url: contentUrl,
        position,
      })
    }
    reader.readAsDataURL(file)
  })
}

/** Interleave pasted images with text using their textarea caret offsets. */
export function buildMessageParts(
  text: string,
  images: readonly PositionedMessageImage[],
): MessagePart[] {
  if (!images.length) return text ? [{ type: 'text', text }] : []
  const ordered = images
    .map((image, index) => ({ image, index }))
    .sort((left, right) => left.image.position - right.image.position || left.index - right.index)
  const parts: MessagePart[] = []
  let cursor = 0
  for (const { image } of ordered) {
    const position = Math.min(text.length, Math.max(cursor, image.position))
    if (position > cursor) parts.push({ type: 'text', text: text.slice(cursor, position) })
    parts.push({
      type: 'image',
      name: image.name,
      mime_type: image.mime_type,
      content_url: image.content_url,
    })
    cursor = position
  }
  if (cursor < text.length) parts.push({ type: 'text', text: text.slice(cursor) })
  return parts
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
