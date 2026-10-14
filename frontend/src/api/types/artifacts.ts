import type { ArtifactStatus, ArtifactType, CardStatus, CardType } from './common'
import type { SuggestedTag } from './library'

export interface ArtifactContentBase {
  title: string
  summary: string
  suggested_tags: SuggestedTag[]
  keywords: string[]
}

export interface CardArtifactContent extends ArtifactContentBase {
  artifact_type: 'card'
  card_type: CardType
  content: string
}

export interface ArticleArtifactContent extends ArtifactContentBase {
  artifact_type: 'article'
  subtitle: string
  content: string
}

export interface ImageArtifactContent extends ArtifactContentBase {
  artifact_type: 'image'
  prompt: string
  alt_text: string
  /** External image URL only, for example `https://example.com/image.png`. */
  source_url: string | null
  /**
   * Relative ObjectKey for a locally stored image.
   * Example: `assets/sessions/<session_id>/<asset_id>.png`.
   */
  asset_path: string | null
}

export interface SlidesArtifactContent extends ArtifactContentBase {
  artifact_type: 'slides'
  subtitle: string
  content: string
}

export interface LatexPdfArtifactContent {
  artifact_type: 'latex_pdf'
  /**
   * Relative project directory ObjectKey.
   * Example: `artifacts/<session_id>/paper`.
   */
  project_path: string
  /** Plain PDF filename inside `project_path`, for example `paper.pdf`. */
  pdf_name: string
}

export type ArtifactContent = CardArtifactContent | ArticleArtifactContent | ImageArtifactContent | SlidesArtifactContent | LatexPdfArtifactContent

export interface LatexPdfArtifactCreate {
  artifact_type: 'latex_pdf'
  /** Compiled PDF basename, including `.pdf`; the server creates the project directory. */
  pdf_name: string
}

/** Content accepted when creating an artifact, before any project directory exists. */
export type ArtifactCreateContent =
  | CardArtifactContent
  | ArticleArtifactContent
  | ImageArtifactContent
  | SlidesArtifactContent
  | LatexPdfArtifactCreate

export interface AgentArtifact {
  id: string
  session_id: string
  artifact_type: ArtifactType
  status: ArtifactStatus
  /** Published content. Null until the user saves the artifact's first draft. */
  content: ArtifactContent | null
  /** Model-proposed content awaiting an explicit user save. */
  draft_content: ArtifactContent | null
  raw_content: string | null
  version: number
  metadata: Record<string, unknown>
  /** Status of a todo, idea, or reference card, independent of its draft; null for every other artifact. */
  card_status?: CardStatus | null
  tags: Array<{ id: string; path: string; name: string }>
  /**
   * Response-only URL for an artifact that owns a file.
   * Example: `/api/files/artifacts/<session_id>/paper/paper.pdf`.
   * Null for inline artifacts such as cards, articles, and slides.
   */
  content_url: string | null
  created_at: string
  updated_at: string
}
