export interface RuntimeSettings {
  /** Whether the Agent in a web conversation may delete that conversation's artifacts. Off by default. */
  agent_may_delete_artifacts: boolean
  /** Whether the Agent in a web conversation may delete tags from the library. Off by default. */
  agent_may_delete_tags: boolean
  max_message_images: number
  max_turn_iterations: number
  max_asset_size_bytes: number
  compaction_max_tokens: number
  compaction_keep_recent_tokens: number
}
