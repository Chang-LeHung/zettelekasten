import { onBeforeUnmount, onMounted, watch } from 'vue'
import { pruned } from '../utils/multiSelect'
import { setArtifactListHeight } from './artifacts/actions'
import { artifactListHeight, artifactPaneRef, artifactsScratch } from './artifacts/state'
import { activeStreamController, activeTodos, agentTurnStack, conversation, conversationScratch, loading, pendingQuestion, streamingMessage, streamingReasoning, streamingTimeline } from './conversation/state'
import { scrollAgentThread } from './conversation/stream'
import { clearLibrarySelection, handleSlidesFullscreenChange, loadLibrary } from './library/actions'
import { collectionTarget, libraryItems, libraryScratch, librarySentinel, selectedLibraryIds, selectedTag } from './library/state'
import { loadCollectionTags } from './library/tags'
import { view } from './nav'
import { errorMessage, noticeScratch, showNotice } from './notice'
import { clearSessionTitleRefresh } from './sessions'
import { handleShortcut, initializeWorkspace } from './workspace'

/** Watchers and lifecycle hooks that tie the shared state to the DOM. Call once from the root component's setup. */
export function useAppLifecycle(): void {
  watch(artifactPaneRef, (pane) => {
    artifactsScratch.artifactPaneResizeObserver?.disconnect()
    artifactsScratch.artifactPaneResizeObserver = null
    if (!pane) return
    artifactsScratch.artifactPaneResizeObserver = new ResizeObserver(() => {
      if (artifactListHeight.value !== null) setArtifactListHeight(artifactListHeight.value)
    })
    artifactsScratch.artifactPaneResizeObserver.observe(pane)
  })
  watch(
    [streamingMessage, streamingReasoning, () => streamingTimeline.value.length, pendingQuestion, activeTodos],
    () => scrollAgentThread(),
  )
  watch(
    () => conversation.value.length,
    () => scrollAgentThread(),
  )
  watch(loading, (isLoading) => {
    if (isLoading) scrollAgentThread(true)
  })
  watch(agentTurnStack, (current, previous) => {
    if (previous) conversationScratch.agentContentResizeObserver?.unobserve(previous)
    if (current) conversationScratch.agentContentResizeObserver?.observe(current)
  })
  // Each library browses its own tree, so switching libraries drops a selection
  // that belongs to the other one instead of filtering a list it cannot show.
  // A card that was deleted, filtered away, or paged out cannot stay selected, and
  // leaving the library drops the selection so it never resurfaces on return.
  watch(libraryItems, (items) => {
    if (!selectedLibraryIds.value.size) return
    const remaining = pruned(selectedLibraryIds.value, items.map((item) => item.id))
    if (remaining.size !== selectedLibraryIds.value.size) selectedLibraryIds.value = remaining
  })
  watch(view, (next) => {
    if (next !== 'library') clearLibrarySelection()
  })
  watch(collectionTarget, () => {
    selectedTag.value = null
    loadCollectionTags().catch((error: unknown) => showNotice(errorMessage(error), 'error'))
  })
  onMounted(() => {
    document.addEventListener('fullscreenchange', handleSlidesFullscreenChange)
    window.addEventListener('keydown', handleShortcut)
    conversationScratch.agentContentResizeObserver = new ResizeObserver(() => scrollAgentThread())
    if (agentTurnStack.value) conversationScratch.agentContentResizeObserver.observe(agentTurnStack.value)
    void initializeWorkspace()
  })
  /**
   * Infinite scroll for the library grid: the sentinel sits after the last card,
   * so the next page is requested while the reader is still one screen above the
   * fold. A page shorter than the size ends the run by clearing `libraryHasMore`.
   */
  watch(librarySentinel, (element) => {
    libraryScratch.libraryObserver?.disconnect()
    libraryScratch.libraryObserver = null
    if (!element || typeof IntersectionObserver === 'undefined') return
    libraryScratch.libraryObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadLibrary({ append: true })
    }, { rootMargin: '600px 0px' })
    libraryScratch.libraryObserver.observe(element)
  }, { flush: 'post' })
  onBeforeUnmount(() => {
    document.removeEventListener('fullscreenchange', handleSlidesFullscreenChange)
    noticeScratch.resolveConfirmation?.(false)
    activeStreamController.value?.abort()
    if (conversationScratch.agentScrollFrame !== null) window.cancelAnimationFrame(conversationScratch.agentScrollFrame)
    if (conversationScratch.turnClock !== null) window.clearInterval(conversationScratch.turnClock)
    libraryScratch.libraryObserver?.disconnect()
    libraryScratch.libraryObserver = null
    conversationScratch.agentContentResizeObserver?.disconnect()
    conversationScratch.agentContentResizeObserver = null
    artifactsScratch.artifactPaneResizeObserver?.disconnect()
    artifactsScratch.artifactPaneResizeObserver = null
    window.removeEventListener('keydown', handleShortcut)
    clearSessionTitleRefresh()
  })
}
