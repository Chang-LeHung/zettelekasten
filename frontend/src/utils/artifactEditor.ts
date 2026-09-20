import type { AgentArtifact, ArtifactContent, LibraryItem, LibraryItemUpdate } from '../api/types'

/**
 * Content the artifact shows right now: the model's draft first, published
 * content second. The model never writes published content, so a fresh artifact
 * is visible through its draft until the user saves it.
 */
export function artifactEditableContent(artifact: AgentArtifact): ArtifactContent | null {
  return artifact.draft_content ?? artifact.content ?? null
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

/**
 * Whether the draft still differs from what the user published. Saving copies
 * the published content into the draft, so equal content means nothing is
 * pending even though the draft is always present.
 */
export function hasPendingDraft(artifact: AgentArtifact): boolean {
  if (!artifact.draft_content) return false
  return canonicalJson(artifact.draft_content) !== canonicalJson(artifact.content)
}

/** Project an editable conversation artifact into the full artifact editor model. */
export function libraryItemFromArtifact(artifact: AgentArtifact): LibraryItem | null {
  const content = artifactEditableContent(artifact)
  if (!content) return null
  if (content.artifact_type === 'image' || content.artifact_type === 'latex_pdf') return null
  return {
    id: artifact.id,
    session_id: artifact.session_id,
    item_type: content.artifact_type,
    title: content.title,
    subtitle: content.artifact_type === 'card' ? null : content.subtitle,
    summary: content.summary || null,
    content: content.content,
    raw_content: artifact.raw_content,
    card_type: content.artifact_type === 'card' ? content.card_type : null,
    status: artifact.status,
    tags: artifact.tags.map((tag) => tag.path),
    metadata: artifact.metadata,
    created_at: artifact.created_at,
    updated_at: artifact.updated_at,
  }
}

/** Apply edits from the full artifact editor without dropping type-specific fields. */
export function artifactContentFromLibraryUpdate(
  content: ArtifactContent,
  update: LibraryItemUpdate,
): ArtifactContent {
  if (content.artifact_type === 'article' || content.artifact_type === 'slides') {
    return {
      ...content,
      title: update.title,
      subtitle: update.subtitle || '',
      summary: update.summary || '',
      content: update.content,
    }
  }
  if (content.artifact_type === 'card') {
    return {
      ...content,
      title: update.title,
      summary: update.summary || '',
      content: update.content,
    }
  }
  return content
}
