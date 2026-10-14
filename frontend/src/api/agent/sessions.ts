import { request } from '../http'
import type { AgentAtCommand, AgentContextComposition, AgentSession, AgentSlashCommand, AgentStart, MessagePart, SessionModelPreference, SessionType, ShellApprovalMode, ShellApprovalSettings } from '../types'

export const agentSessionApi = {
  startAgent(): Promise<AgentStart> {
    return request<AgentStart>('/agent/start', { method: 'POST' })
  },

  listSlashCommands(conversationId: string): Promise<AgentSlashCommand[]> {
    return request<AgentSlashCommand[]>(`/agent/${conversationId}/slash-commands`)
  },

  listAtCommands(conversationId: string): Promise<AgentAtCommand[]> {
    return request<AgentAtCommand[]>(`/agent/${conversationId}/at-commands`)
  },

  getAgentSession(conversationId: string): Promise<AgentSession> {
    return request<AgentSession>(`/agent/sessions/${conversationId}`)
  },

  getAgentSessionMessages(conversationId: string, limit = 500): Promise<AgentSession['messages']> {
    const params = new URLSearchParams({ limit: String(limit) })
    return request<AgentSession['messages']>(`/agent/sessions/${conversationId}/messages?${params}`)
  },

  getAgentSessionModel(conversationId: string): Promise<SessionModelPreference | null> {
    return request<SessionModelPreference | null>(`/agent/sessions/${conversationId}/model`)
  },

  getAgentSessionContextComposition(conversationId: string): Promise<AgentContextComposition> {
    return request<AgentContextComposition>(`/agent/sessions/${conversationId}/context-composition`)
  },

  getAgentSessionShellApproval(conversationId: string): Promise<ShellApprovalSettings> {
    return request<ShellApprovalSettings>(`/agent/sessions/${conversationId}/shell-approval`)
  },

  updateAgentSessionShellApproval(
    conversationId: string,
    mode: ShellApprovalMode,
  ): Promise<ShellApprovalSettings> {
    return request<ShellApprovalSettings>(`/agent/sessions/${conversationId}/shell-approval`, {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    })
  },

  updateAgentSessionTitle(conversationId: string, title: string): Promise<AgentSession> {
    return request<AgentSession>(`/agent/sessions/${conversationId}/title`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
  },

  listAgentSessions(limit = 20, offset = 0, types: SessionType[] = ['normal']): Promise<AgentSession[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    types.forEach((type) => params.append('types', type))
    return request<AgentSession[]>(`/agent/sessions?${params}`)
  },

  deleteAgentSession(conversationId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/agent/sessions/${conversationId}`, { method: 'DELETE' })
  },

  emitAgentEvent(
    conversationId: string,
    name: string,
    payload: Record<string, unknown>,
  ): Promise<{ accepted: boolean }> {
    return request<{ accepted: boolean }>(`/agent/${conversationId}/events`, {
      method: 'POST',
      body: JSON.stringify({ name, payload }),
    })
  },

  steerAgent(
    conversationId: string,
    rawContent: string,
    parts: MessagePart[] = [],
  ): Promise<{ accepted: boolean }> {
    return request<{ accepted: boolean }>(`/agent/${conversationId}/steer`, {
      method: 'POST',
      body: JSON.stringify({ raw_content: rawContent, parts }),
    })
  },
}
