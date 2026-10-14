import type { CardStatus, CardType } from './common'

export interface TagRecord {
  id: string
  /** Library this collection belongs to: the artifact or the static asset tree. */
  target_type: 'artifact' | 'asset'
  name: string
  parent_id: string | null
  description: string | null
  color: string | null
  created_at: string
  updated_at: string
  path: string
  normalized_path: string
}

export interface Tag extends TagRecord {
  direct_count: number
  total_count: number
  children: Tag[]
}

export interface TagCreateInput {
  /** Library the collection belongs to; the two keep separate trees. */
  target: 'artifact' | 'asset'
  path: string
  description?: string | null
  color?: string | null
}

export interface Card {
  id: string
  type: string
  title: string
  content: string
  raw_content: string | null
  summary: string | null
  status: string
  created_at: string
  updated_at: string
  tags: string[]
  metadata: Record<string, unknown>
}

export interface CardCreateRequest {
  type: string
  title: string
  content: string
  raw_content?: string | null
  summary?: string | null
  tags: string[]
  metadata?: Record<string, unknown>
}

export interface CardListOptions {
  query?: string
  tagId?: string | null
  artifactTypes?: LibraryItemType[]
  /** Keep only cards in these statuses; an empty list applies no status filter. */
  cardStatuses?: CardStatus[]
  publishedOnly?: boolean
  limit?: number
  offset?: number
}

export type LibraryItemType = 'card' | 'article' | 'slides' | 'latex_pdf'

export interface LibraryItem {
  id: string
  session_id: string
  item_type: LibraryItemType
  title: string
  subtitle: string | null
  summary: string | null
  content: string
  raw_content: string | null
  card_type: CardType | null
  /** Status of a todo, idea, or reference card; null for every other item. */
  card_status?: CardStatus | null
  status: string
  tags: string[]
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface LibraryItemUpdate {
  title: string
  subtitle: string | null
  summary: string | null
  content: string
  tags?: string[] | null
  metadata?: Record<string, unknown> | null
  expectedVersion?: number
}

export interface SuggestedTag {
  path: string
  existing: boolean
  confidence: number
  reason?: string | null
}

export interface TagCreateRequest {
  name: string
  parent_id: number | null
}
