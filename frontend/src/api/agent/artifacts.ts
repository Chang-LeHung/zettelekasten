import { request } from '../http'
import type { AgentArtifact, ArtifactContent, CardStatus } from '../types'

export const agentArtifactApi = {
  listAgentArtifacts(conversationId: string): Promise<AgentArtifact[]> {
    return request<AgentArtifact[]>(`/agent/${conversationId}/artifacts`)
  },

  getAgentArtifact(conversationId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}`)
  },

  /**
   * Write editing as a draft. Published content only changes through
   * `saveAgentArtifact`, so an editor save never rewrites the original.
   */
  updateAgentArtifactDraft(
    conversationId: string,
    artifactId: string,
    content: ArtifactContent,
  ): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    })
  },

  deleteAgentArtifact(conversationId: string, artifactId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/agent/${conversationId}/artifacts/${artifactId}`, { method: 'DELETE' })
  },

  /** Move a card to a new status without editing or publishing it. */
  setAgentCardStatus(conversationId: string, artifactId: string, status: CardStatus): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}/card-status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
  },

  saveAgentArtifact(conversationId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}/save`, { method: 'POST' })
  },
}
