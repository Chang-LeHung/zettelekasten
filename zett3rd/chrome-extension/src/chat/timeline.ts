import type { AgentTimelineEntry } from '../../../../frontend/src/api/types'

/** Same invocation ID, same row, even for parallel calls completing in reverse. */
export function updateTimeline(
  timeline: readonly AgentTimelineEntry[],
  incoming: AgentTimelineEntry,
): AgentTimelineEntry[] {
  if (incoming.type === 'tool' || incoming.type === 'server_tool') {
    const index = timeline.findIndex(entry => entry.type === incoming.type && entry.id === incoming.id)
    if (index < 0) return [...timeline, incoming]
    const previous = timeline[index]
    let updated = incoming
    if (previous.type === 'tool' && incoming.type === 'tool') {
      updated = { ...incoming, activity: { ...previous.activity, ...incoming.activity } }
    } else if (previous.type === 'server_tool' && incoming.type === 'server_tool') {
      updated = {
        ...incoming,
        activity: {
          ...previous.activity,
          ...incoming.activity,
          name: incoming.activity.name || previous.activity.name,
          input: incoming.activity.input ?? previous.activity.input,
          input_delta: `${previous.activity.input_delta || ''}${incoming.activity.input_delta || ''}`,
        },
      }
    }
    return timeline.map((entry, i) => i === index ? updated : entry)
  }
  const last = timeline.at(-1)
  if ((incoming.type === 'message' || incoming.type === 'reasoning') && last?.type === incoming.type) {
    return [...timeline.slice(0, -1), { ...last, content: last.content + incoming.content }]
  }
  if (incoming.type === 'compaction' && last?.type === 'compaction' && incoming.activity.state !== 'started') {
    return [...timeline.slice(0, -1), {
      ...last,
      activity: {
        ...last.activity,
        ...incoming.activity,
        content: last.activity.content + incoming.activity.content,
        reasoning: last.activity.reasoning + incoming.activity.reasoning,
      },
    }]
  }
  return [...timeline, incoming]
}

export function turnTask(timeline: readonly AgentTimelineEntry[]): string {
  const active = [...timeline].reverse().find(entry =>
    (entry.type === 'tool' || entry.type === 'server_tool')
    && (entry.activity.state === 'started' || entry.activity.state === 'streaming'),
  )
  if (active?.type === 'tool' || active?.type === 'server_tool') return `Using ${active.activity.name.replaceAll('_', ' ')}`
  return timeline.at(-1)?.type === 'message' ? 'Writing the response' : 'Thinking through your request'
}

/** Keep interrupted tools inspectable, but do not leave their status running. */
export function settleTimeline(timeline: readonly AgentTimelineEntry[]): AgentTimelineEntry[] {
  return timeline.map(entry => {
    if (entry.type === 'tool' && entry.activity.state === 'started') {
      return { ...entry, activity: { ...entry.activity, state: 'cancelled', error_message: 'The stream ended before this tool returned.' } }
    }
    if (entry.type === 'server_tool' && ['started', 'streaming'].includes(entry.activity.state)) {
      return { ...entry, activity: { ...entry.activity, state: 'failed', error_code: 'Stream ended before a result.' } }
    }
    return entry
  })
}
