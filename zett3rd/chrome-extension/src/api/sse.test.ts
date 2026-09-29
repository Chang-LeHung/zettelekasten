import { describe, expect, it } from 'vitest'

import { parseSseChunk } from './sse'

describe('parseSseChunk', () => {
  it('parses one complete block', () => {
    const { events, rest } = parseSseChunk('', 'event: text_delta\ndata: {"delta":"hi"}\n\n')

    expect(events).toEqual([{ event: 'text_delta', data: { delta: 'hi' } }])
    expect(rest).toBe('')
  })

  it('keeps an unfinished block for the next chunk', () => {
    const first = parseSseChunk('', 'event: text_delta\ndata: {"delta":"a')
    expect(first.events).toEqual([])
    expect(first.rest).toBe('event: text_delta\ndata: {"delta":"a')

    const second = parseSseChunk(first.rest, '"}\n\n')
    expect(second.events).toEqual([{ event: 'text_delta', data: { delta: 'a' } }])
    expect(second.rest).toBe('')
  })

  it('reads several blocks from one chunk and normalizes CRLF', () => {
    const { events } = parseSseChunk(
      '',
      'event: text_delta\r\ndata: {"delta":"a"}\r\n\r\nevent: text_delta\r\ndata: {"delta":"b"}\r\n\r\n',
    )

    expect(events.map((item) => (item.data as { delta: string }).delta)).toEqual(['a', 'b'])
  })

  it('joins a payload split over several data lines', () => {
    const { events } = parseSseChunk('', 'event: result\ndata: {"a":1,\ndata: "b":2}\n\n')

    expect(events).toEqual([{ event: 'result', data: { a: 1, b: 2 } }])
  })

  it('drops a block that is not a JSON payload instead of killing the stream', () => {
    const { events } = parseSseChunk(
      '',
      'event: text_delta\ndata: not json\n\nevent: text_delta\ndata: {"delta":"ok"}\n\n',
    )

    expect(events).toEqual([{ event: 'text_delta', data: { delta: 'ok' } }])
  })

  it('ignores keep-alive comments and blocks without a data line', () => {
    const { events, rest } = parseSseChunk('', ': ping\n\nevent: text_delta\n\n')

    expect(events).toEqual([])
    expect(rest).toBe('')
  })
})
