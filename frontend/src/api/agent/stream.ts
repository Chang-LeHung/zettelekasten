import { API_URL, ApiError } from '../http'
import type { AgentArtifact, AgentSteeringMessage, AgentStreamCallbacks, AnalysisMessage, MessagePart, ReasoningEffort, ShellApprovalMode } from '../types'
import { asModelUsage, asServerToolActivity, asToolCalls } from './parsing'
import type { AgentCommandTarget } from './parsing'

export const agentStreamApi = {
  async analyzeStream(
    conversationId: string,
    rawContent: string,
    providerId: string,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
    parts: MessagePart[] = [],
    shellApprovalMode: ShellApprovalMode = 'review',
    command: AgentCommandTarget | null = null,
  ): Promise<AgentArtifact | null> {
    const path = command
      ? `/agent/${conversationId}/${command.slug}/${encodeURIComponent(command.id)}`
      : `/agent/${conversationId}/messages`
    const response = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_content: rawContent,
        provider_id: providerId,
        reasoning_effort: reasoningEffort,
        messages,
        parts,
        shell_approval_mode: shellApprovalMode,
      }),
      signal,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    if (!response.body) throw new Error('The server did not return a response stream')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let result: AgentArtifact | null = null
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replaceAll('\r\n', '\n')
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''
      for (const block of events) {
        const lines = block.split('\n')
        const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
        const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n')
        if (!event || !data) continue
        const payload = JSON.parse(data) as Record<string, unknown> | null
        if (event === 'result') {
          result = payload as AgentArtifact | null
          continue
        }
        if (payload === null) continue
        if (event === 'model_started') {
          callbacks.onModelStarted?.()
          callbacks.onStatus?.('generating')
        }
        if (event === 'model_completed') {
          const usage = asModelUsage(payload.usage)
          if (usage) callbacks.onUsage?.(usage)
        }
        if (event === 'reasoning_delta') callbacks.onReasoning?.(String(payload.delta || ''))
        if (event === 'text_delta') callbacks.onMessage?.(String(payload.delta || ''))
        if (event === 'steering_started') {
          const steering = payload.steering_message as Record<string, unknown> | undefined
          if (steering && typeof steering.text === 'string') {
            callbacks.onSteering?.({
              content: steering.text,
              parts: Array.isArray(steering.parts)
                ? steering.parts as AgentSteeringMessage['parts']
                : [],
            })
          }
        }
        if (event === 'tool_started') {
          for (const call of asToolCalls(payload.tool_calls)) await callbacks.onTool?.({ ...call, state: 'started' })
        }
        if (['tool_completed', 'tool_failed', 'tool_skipped'].includes(event)) {
          const message = payload.message as Record<string, unknown> | undefined
          if (message) await callbacks.onTool?.({
            id: String(message.tool_call_id || ''),
            name: String(message.name || ''),
            state: event === 'tool_completed' ? 'succeeded' : event === 'tool_skipped' ? 'cancelled' : 'failed',
            output: message.output,
            error_message: event === 'tool_failed'
              ? String((payload.error as Record<string, unknown> | undefined)?.message || '')
              : null,
          })
        }
        if ([
          'server_tool_started',
          'server_tool_input_delta',
          'server_tool_completed',
          'server_tool_failed',
        ].includes(event)) {
          const activity = asServerToolActivity(event, payload)
          if (activity) callbacks.onServerTool?.(activity)
        }
        if (event.startsWith('compaction_')) callbacks.onCompaction?.({
          state: event === 'compaction_started' ? 'started' : event === 'compaction_completed' ? 'completed' : 'streaming',
          applied: typeof payload.applied === 'boolean' ? payload.applied : null,
          content: event === 'compaction_text_delta' ? String(payload.delta || '') : '',
          reasoning: event === 'compaction_reasoning_delta' ? String(payload.delta || '') : '',
        })
        if (event === 'custom') callbacks.onCustom?.({
          name: String(payload.name || ''),
          payload: (payload.payload || {}) as Record<string, unknown>,
        })
        if (event === 'run_completed') callbacks.onStatus?.('completed')
        if (event === 'error') throw new Error(String(payload.message || 'AI analysis failed'))
      }
      if (done) break
    }
    return result
  },

  slashCommandStream(
    conversationId: string,
    commandId: string,
    rawContent: string,
    providerId: string,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
    parts: MessagePart[] = [],
    shellApprovalMode: ShellApprovalMode = 'review',
  ): Promise<AgentArtifact | null> {
    return this.analyzeStream(
      conversationId,
      rawContent,
      providerId,
      reasoningEffort,
      messages,
      callbacks,
      signal,
      parts,
      shellApprovalMode,
      { slug: 'slash-commands', id: commandId },
    )
  },

  /**
   * Run one turn that references a conversation resource. The browser submits
   * the `@` item ID it resolved from the composer text, and the backend injects
   * that reference before streaming the Agent events.
   */
  atCommandStream(
    conversationId: string,
    itemId: string,
    rawContent: string,
    providerId: string,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
    parts: MessagePart[] = [],
    shellApprovalMode: ShellApprovalMode = 'review',
  ): Promise<AgentArtifact | null> {
    return this.analyzeStream(
      conversationId,
      rawContent,
      providerId,
      reasoningEffort,
      messages,
      callbacks,
      signal,
      parts,
      shellApprovalMode,
      { slug: 'at-commands', id: itemId },
    )
  },
}
