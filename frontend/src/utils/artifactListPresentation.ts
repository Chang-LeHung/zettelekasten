import type { AgentArtifact, ArtifactContent } from '../api/types'
import { artifactEditableContent } from './artifactEditor'
import { artifactImageUrl } from './artifactPreview'
import { libraryExcerptText } from './libraryExcerpt'

/** Plain-text preview for the vertical conversation list, never raw HTML. */
export function artifactListExcerpt(content: ArtifactContent | null): string {
  if (!content) return ''
  if (content.artifact_type === 'latex_pdf') return content.pdf_name
  if (content.artifact_type === 'image') {
    return libraryExcerptText(content.summary || content.alt_text || content.prompt)
  }
  return libraryExcerptText([content.summary, content.content].filter(Boolean).join('\n\n'))
}

/** Use the same derived image URL as the full artifact preview. */
export function artifactListImage(artifact: AgentArtifact): string | null {
  return artifactImageUrl(artifactEditableContent(artifact), artifact)
}
