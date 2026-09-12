import { describe, expect, it } from 'vitest'
import { appendStreamedAssistantMessage, createStreamedAssistantMessage } from './streamedAssistant'

describe('createStreamedAssistantMessage', () => {
  it('retains partial content and execution details when a stream fails', () => {
    const message = createStreamedAssistantMessage(
      {
        content: 'Partial answer',
        reasoning: 'Inspecting the request',
        activities: [{ id: 'call-1', name: 'read_file', state: 'succeeded', output: 'result' }],
        timeline: [
          { id: 'thinking', type: 'reasoning', content: 'Inspecting the request' },
          { id: 'answer', type: 'message', content: 'Partial answer' },
        ],
        duration_ms: 1250,
        generation_duration_ms: 900,
      },
      { error: 'Provider connection failed' },
    )

    expect(message).toMatchObject({
      role: 'assistant',
      content: 'Partial answer',
      error: 'Provider connection failed',
      reasoning: 'Inspecting the request',
      duration_ms: 1250,
    })
    expect(message.timeline).toHaveLength(2)
    expect(message.activities).toHaveLength(1)
  })

  it('shows an error without inventing fallback prose and uses fallback only for success', () => {
    const snapshot = {
      content: '',
      activities: [],
      timeline: [],
      duration_ms: 0,
      generation_duration_ms: 0,
    }

    expect(createStreamedAssistantMessage(snapshot, { error: 'Request failed' })).toMatchObject({
      content: '',
      error: 'Request failed',
    })
    expect(createStreamedAssistantMessage(snapshot, { fallbackContent: 'Finished' }).content).toBe('Finished')
  })

  it('copies mutable stream collections before they are reset for the next turn', () => {
    const activities = [{ id: 'call-1', name: 'read_file', state: 'started' as const }]
    const timeline = [{ id: 'tool-call-1', type: 'tool' as const, activity: activities[0] }]
    const message = createStreamedAssistantMessage({
      content: '', activities, timeline, duration_ms: 0, generation_duration_ms: 0,
    })

    activities.length = 0
    timeline.length = 0

    expect(message.activities).toHaveLength(1)
    expect(message.timeline).toHaveLength(1)
  })

  it('appends a failed response without replacing existing conversation data', () => {
    const history = [
      { role: 'user' as const, content: 'Question' },
      { role: 'assistant' as const, content: 'Previous answer' },
      { role: 'user' as const, content: 'Follow up' },
    ]
    const result = appendStreamedAssistantMessage(
      history,
      { content: 'Partial', activities: [], timeline: [], duration_ms: 5, generation_duration_ms: 3 },
      { error: 'Backend failed' },
    )

    expect(result.slice(0, -1)).toEqual(history)
    expect(result.at(-1)).toMatchObject({ role: 'assistant', content: 'Partial', error: 'Backend failed' })
    expect(history).toHaveLength(3)
  })
})
