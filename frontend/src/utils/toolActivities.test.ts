import { describe, expect, it } from 'vitest'
import type { AgentToolActivity } from '../api/types'
import { hasRunningTool, upsertToolActivity } from './toolActivities'

describe('parallel tool activities', () => {
  it('keeps same-named calls isolated by tool-call ID and accepts reverse completion', () => {
    let activities: AgentToolActivity[] = []
    activities = upsertToolActivity(activities, { id: 'slow', name: 'read_file', state: 'started' })
    activities = upsertToolActivity(activities, { id: 'fast', name: 'read_file', state: 'started' })
    activities = upsertToolActivity(activities, { id: 'fast', name: 'read_file', state: 'succeeded', output: 'fast' })

    expect(hasRunningTool(activities)).toBe(true)
    expect(activities).toMatchObject([
      { id: 'slow', state: 'started' },
      { id: 'fast', state: 'succeeded', output: 'fast' },
    ])

    activities = upsertToolActivity(activities, {
      id: 'slow', name: 'read_file', state: 'failed', error_message: 'failed',
    })
    expect(hasRunningTool(activities)).toBe(false)
    expect(activities[1]?.state).toBe('succeeded')
  })
})
