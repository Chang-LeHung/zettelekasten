/**
 * Parse the server's `text/event-stream` one block at a time.
 *
 * The stream arrives in arbitrary chunks, so the reader keeps the unfinished
 * tail and hands back whole blocks. Keeping this pure — no `fetch`, no `chrome`
 * — lets the parser be tested with strings alone, which is where the
 * interesting cases live: a block split across two chunks, comments, and the
 * multi-line `data:` form.
 */

export interface SseEvent {
  event: string
  data: unknown
}

export interface SseResult {
  events: SseEvent[]
  rest: string
}

/** Feed one chunk and return the events it completed. */
export function parseSseChunk(buffer: string, chunk: string): SseResult {
  const combined = `${buffer}${chunk}`.replaceAll('\r\n', '\n')
  const blocks = combined.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: SseEvent[] = []
  for (const block of blocks) {
    const lines = block.split('\n')
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
    const data = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('\n')
    if (!event || !data) continue
    try {
      events.push({ event, data: JSON.parse(data) })
    } catch {
      // A payload nobody can parse is dropped rather than killing a live turn.
      continue
    }
  }
  return { events, rest }
}
