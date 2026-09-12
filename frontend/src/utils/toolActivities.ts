import type { AgentToolActivity } from '../api/types'

/** Replace one invocation by ID without conflating calls that share a tool name. */
export function upsertToolActivity(
  activities: readonly AgentToolActivity[],
  activity: AgentToolActivity,
): AgentToolActivity[] {
  const index = activities.findIndex((item) => item.id === activity.id)
  if (index < 0) return [...activities, activity]
  return activities.map((item, itemIndex) => itemIndex === index ? { ...item, ...activity } : item)
}

/** Report whether at least one invocation in a parallel batch is unfinished. */
export function hasRunningTool(activities: readonly AgentToolActivity[]): boolean {
  return activities.some((activity) => activity.state === 'started')
}
