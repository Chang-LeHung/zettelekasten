export type CardType = 'note' | 'idea' | 'quote' | 'todo' | 'reference'

/**
 * Where a card stands in its own life. Each card type draws from its own slice
 * (`CARD_STATUSES` in utils/cardStatus.ts); a note or a quote has none.
 */
export type CardStatus =
  | 'open' | 'in_progress' | 'on_hold' | 'done' | 'cancelled'
  | 'captured' | 'exploring' | 'adopted' | 'dropped'
  | 'unread' | 'reading' | 'read'

export type ArtifactType = 'card' | 'article' | 'image' | 'slides' | 'latex_pdf'

export type ArtifactStatus = 'draft' | 'saved'

export type SessionAssetType = 'text' | 'image' | 'link' | 'file'

export type ReasoningEffort = 'off' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max' | 'ultra'

export type ShellApprovalMode = 'review' | 'allow_all'
