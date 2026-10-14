import { nextTick } from 'vue'
import { libraryClient, tagClient } from '../../api/client'
import type { CardStatus, LibraryItem, Tag } from '../../api/types'
import { cardStatusLabel } from '../../utils/cardStatus'
import { boxFromPoints, exceedsThreshold, idsInBox, rangeBetween, settleLimited, toggled } from '../../utils/multiSelect'
import { visibleTagRows } from '../../utils/tagTree'
import { t } from '../i18n'
import { view } from '../nav'
import { errorMessage, requestConfirmation, showNotice } from '../notice'
import { LIBRARY_PAGE_SIZE, MARQUEE_EDGE, NOT_A_MARQUEE_START, activeQuery, bulkDeleting, cardStatusUpdatingIds, deletingLibraryItemId, fullscreenSlidesItem, libraryEditorArtifactId, libraryEditorItem, libraryHasMore, libraryItems, libraryLoading, libraryLoadingMore, libraryMarquee, libraryPdfLaunch, libraryScratch, librarySlidesStage, libraryTotal, query, searchInput, selectedCardStatuses, selectedLibraryIds, selectedLibraryItem, selectedLibraryItems, selectedLibraryType, selectedTag, selectingLibrary, tagManagerBusy } from './state'
import { refreshTags, tagSubtreeContains } from './tags'

export async function openSlidesFullscreen(item: LibraryItem): Promise<void> {
  libraryScratch.slidesPreviewTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  fullscreenSlidesItem.value = item
  await nextTick()
  librarySlidesStage.value?.focus()
  try {
    await librarySlidesStage.value?.requestFullscreen()
  } catch {
    // Keep the viewport-sized preview available if native fullscreen is unavailable.
  }
}
export async function closeSlidesFullscreen(): Promise<void> {
  if (document.fullscreenElement === librarySlidesStage.value) await document.exitFullscreen()
  fullscreenSlidesItem.value = null
  libraryScratch.slidesPreviewTrigger?.focus()
}
export function openLibraryPdf(item: LibraryItem, mode: 'expanded' | 'presentation'): void {
  libraryPdfLaunch.value = { item, mode }
}
export function handleSlidesFullscreenChange(): void {
  if (!document.fullscreenElement && fullscreenSlidesItem.value) {
    fullscreenSlidesItem.value = null
    libraryScratch.slidesPreviewTrigger?.focus()
  }
}
export async function deleteTag(tag: Tag): Promise<void> {
  if (tagManagerBusy.value) return
  const childCount = visibleTagRows(tag.children).length
  const itemCount = tag.total_count
  const scope = childCount
    ? `This also deletes ${childCount} nested ${childCount === 1 ? 'tag' : 'tags'}`
    : 'This deletes the tag'
  const assignments = itemCount
    ? ` and removes it from ${itemCount} ${itemCount === 1 ? 'artifact' : 'artifacts'}.`
    : '.'
  const confirmed = await requestConfirmation(
    `Delete “${tag.path}”?`,
    `${scope}${assignments} The artifacts themselves will remain.`,
    childCount ? 'Delete tag tree' : 'Delete tag',
  )
  if (!confirmed) return

  tagManagerBusy.value = true
  try {
    await tagClient.delete(tag.id)
    if (selectedTag.value && tagSubtreeContains(tag, selectedTag.value)) selectedTag.value = null
    await Promise.all([refreshTags(), loadLibrary()])
    showNotice(`Tag “${tag.path}” deleted`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    tagManagerBusy.value = false
  }
}
/** The filters the grid is showing; the count and every page share them. */
function libraryListFilters() {
  return {
    query: view.value === 'search' ? activeQuery.value : '',
    tagId: selectedTag.value,
    artifactTypes: selectedLibraryType.value ? [selectedLibraryType.value] : undefined,
    cardStatuses: selectedCardStatuses.value.length ? selectedCardStatuses.value : undefined,
  }
}
/**
 * Load one page of the library. A plain call replaces the grid and asks how
 * many matches exist; `append` adds the next page when the sentinel below the
 * grid scrolls into view. Each request fetches one card past the page size, so
 * "is there more" costs no second round trip, and a stale page loses to the
 * filter change that replaced it.
 */
export async function loadLibrary({ append = false }: { append?: boolean } = {}): Promise<void> {
  if (append && (libraryLoading.value || libraryLoadingMore.value || !libraryHasMore.value)) return
  const requestId = ++libraryScratch.libraryRequestId
  const offset = append ? libraryItems.value.length : 0
  const filters = libraryListFilters()
  if (append) {
    libraryLoadingMore.value = true
  } else {
    libraryLoading.value = true
    // A reset supersedes any page still in flight, so its settle must not
    // leave the "loading more" state behind.
    libraryLoadingMore.value = false
  }
  try {
    const [page, total] = await Promise.all([
      libraryClient.list({ ...filters, limit: LIBRARY_PAGE_SIZE + 1, offset }),
      append ? Promise.resolve(libraryTotal.value) : libraryClient.count(filters),
    ])
    if (requestId !== libraryScratch.libraryRequestId) return
    libraryHasMore.value = page.length > LIBRARY_PAGE_SIZE
    const visible = libraryHasMore.value ? page.slice(0, LIBRARY_PAGE_SIZE) : page
    libraryItems.value = append ? [...libraryItems.value, ...visible] : visible
    if (total !== null) libraryTotal.value = total
  } catch (error) {
    if (requestId === libraryScratch.libraryRequestId) showNotice(errorMessage(error), 'error')
  } finally {
    if (requestId === libraryScratch.libraryRequestId) {
      libraryLoading.value = false
      libraryLoadingMore.value = false
    }
  }
}
export function openSearch(): void {
  view.value = 'search'
  void nextTick(() => searchInput.value?.focus())
}
function openLibraryItem(item: LibraryItem): void {
  selectedLibraryItem.value = item
}
export async function copyLibraryItemId(item: LibraryItem): Promise<void> {
  try {
    await navigator.clipboard.writeText(item.id)
    showNotice('Resource ID copied')
  } catch {
    showNotice('Could not copy the resource ID', 'error')
  }
}
export function clearLibrarySelection(): void {
  selectedLibraryIds.value = new Set()
  libraryScratch.selectionAnchorId = null
}
export function selectAllLibraryItems(): void {
  selectedLibraryIds.value = new Set(libraryItems.value.map((item) => item.id))
  libraryScratch.selectionAnchorId = libraryItems.value[0]?.id ?? null
}
export function toggleLibrarySelection(item: LibraryItem): void {
  selectedLibraryIds.value = toggled(selectedLibraryIds.value, item.id)
  libraryScratch.selectionAnchorId = item.id
}
/** Shift extends from the last card picked; the earlier picks stay. */
function extendLibrarySelection(item: LibraryItem): void {
  const span = rangeBetween(libraryItems.value.map((candidate) => candidate.id), libraryScratch.selectionAnchorId, item.id)
  selectedLibraryIds.value = new Set([...selectedLibraryIds.value, ...span])
  libraryScratch.selectionAnchorId ??= item.id
}
/** Click opens a card, unless the user is picking cards: then it picks, as in Finder and Photos. */
export function onLibraryCardActivate(item: LibraryItem, event: MouseEvent | KeyboardEvent): void {
  if (event.shiftKey) extendLibrarySelection(item)
  else if (event.metaKey || event.ctrlKey || selectingLibrary.value) toggleLibrarySelection(item)
  else openLibraryItem(item)
}
/**
 * Drag a rectangle over empty space to pick every card it covers. Shift or
 * Cmd/Ctrl adds to the current picks; a plain drag replaces them, and a plain
 * click on empty space clears them. The rectangle is anchored to the page, not
 * the window, so it keeps covering what it started on while the page scrolls.
 */
export function startLibraryMarquee(event: PointerEvent): void {
  if (event.button !== 0 || bulkDeleting.value || !libraryItems.value.length) return
  if (event.target instanceof Element && event.target.closest(NOT_A_MARQUEE_START)) return
  const additive = event.shiftKey || event.metaKey || event.ctrlKey
  const base = additive ? new Set(selectedLibraryIds.value) : new Set<string>()
  const originX = event.clientX + window.scrollX
  const originY = event.clientY + window.scrollY
  let pointerX = event.clientX
  let pointerY = event.clientY
  let dragging = false
  let frame = 0

  const update = (): void => {
    const box = boxFromPoints(originX - window.scrollX, originY - window.scrollY, pointerX, pointerY)
    libraryMarquee.value = box
    const targets = [...document.querySelectorAll<HTMLElement>('[data-library-id]')].map((element) => {
      const rect = element.getBoundingClientRect()
      return { id: element.dataset.libraryId!, box: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom } }
    })
    selectedLibraryIds.value = new Set([...base, ...idsInBox(box, targets)])
  }
  const tick = (): void => {
    if (pointerY < MARQUEE_EDGE) window.scrollBy(0, -Math.ceil((MARQUEE_EDGE - pointerY) / 3))
    else if (pointerY > window.innerHeight - MARQUEE_EDGE) window.scrollBy(0, Math.ceil((pointerY - (window.innerHeight - MARQUEE_EDGE)) / 3))
    update()
    frame = requestAnimationFrame(tick)
  }
  const move = (next: PointerEvent): void => {
    pointerX = next.clientX
    pointerY = next.clientY
    if (!dragging) {
      if (!exceedsThreshold(pointerX - (originX - window.scrollX), pointerY - (originY - window.scrollY))) return
      dragging = true
      document.body.classList.add('marquee-selecting')
      frame = requestAnimationFrame(tick)
    }
  }
  const finish = (): void => {
    cancelAnimationFrame(frame)
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
    document.body.classList.remove('marquee-selecting')
    libraryMarquee.value = null
    // A plain click on empty space is "select nothing".
    if (!dragging && !additive) clearLibrarySelection()
    else libraryScratch.selectionAnchorId = [...selectedLibraryIds.value].at(-1) ?? null
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
}
export async function deleteSelectedLibraryItems(): Promise<void> {
  const items = selectedLibraryItems.value
  if (!items.length || bulkDeleting.value || deletingLibraryItemId.value !== null) return
  const count = items.length
  const names = items.slice(0, 3).map((item) => `“${item.title}”`).join(', ')
  const confirmed = await requestConfirmation(
    count === 1 ? 'Delete this artifact?' : `Delete ${count} artifacts?`,
    `${names}${count > 3 ? ` and ${count - 3} more` : ''} will be permanently removed from artifacts. This action cannot be undone.`,
    count === 1 ? 'Delete artifact' : `Delete ${count} artifacts`,
  )
  if (!confirmed) return
  bulkDeleting.value = true
  try {
    // A few at a time: each is its own request, and a failure must not stop the rest.
    const results = await settleLimited(items, 4, (item) => libraryClient.delete(item.item_type, item.id))
    const removed = new Set(items.filter((_, index) => {
      const result = results[index]
      return result.status === 'fulfilled' && result.value.ok
    }).map((item) => item.id))
    const failed = items.filter((item) => !removed.has(item.id))
    if (removed.size) {
      libraryItems.value = libraryItems.value.filter((candidate) => !removed.has(candidate.id))
      if (libraryTotal.value !== null) libraryTotal.value = Math.max(0, libraryTotal.value - removed.size)
      if (selectedLibraryItem.value && removed.has(selectedLibraryItem.value.id)) selectedLibraryItem.value = null
      if (libraryEditorItem.value && removed.has(libraryEditorItem.value.id)) {
        libraryEditorItem.value = null
        libraryEditorArtifactId.value = null
      }
      await refreshTags()
    }
    // What could not be deleted stays selected, so one more press retries exactly those.
    selectedLibraryIds.value = new Set(failed.map((item) => item.id))
    if (!failed.length) {
      showNotice(removed.size === 1 ? 'Artifact deleted' : `${removed.size} artifacts deleted`)
    } else {
      const firstFailure = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
      showNotice(
        `${removed.size ? `${removed.size} deleted, ` : ''}${failed.length} could not be deleted${firstFailure ? `: ${errorMessage(firstFailure.reason)}` : ''}`,
        'error',
      )
    }
  } finally {
    bulkDeleting.value = false
  }
}
export async function deleteLibraryItem(item: LibraryItem): Promise<void> {
  if (deletingLibraryItemId.value !== null) return
  const confirmed = await requestConfirmation(
    `Delete this ${item.item_type}?`,
    `“${item.title}” will be permanently removed from artifacts. This action cannot be undone.`,
    `Delete ${item.item_type}`,
  )
  if (!confirmed) return
  deletingLibraryItemId.value = item.id
  try {
    await libraryClient.delete(item.item_type, item.id)
    libraryItems.value = libraryItems.value.filter((candidate) => candidate.id !== item.id)
    if (libraryTotal.value !== null) libraryTotal.value = Math.max(0, libraryTotal.value - 1)
    if (selectedLibraryItem.value?.id === item.id) selectedLibraryItem.value = null
    if (libraryEditorItem.value?.id === item.id) {
      libraryEditorItem.value = null
      libraryEditorArtifactId.value = null
    }
    await refreshTags()
    showNotice(`${item.item_type === 'article' ? 'Article' : 'Card'} deleted`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    deletingLibraryItemId.value = null
  }
}
export async function deleteSelectedLibraryItem(): Promise<void> {
  if (selectedLibraryItem.value) await deleteLibraryItem(selectedLibraryItem.value)
}
export async function search(): Promise<void> {
  activeQuery.value = query.value.trim()
  selectedTag.value = null
  view.value = 'search'
  await loadLibrary()
}
export async function filterByTag(tagId: string | null): Promise<void> {
  selectedTag.value = tagId
  activeQuery.value = ''
  query.value = ''
  if (view.value === 'assets') {
    // The collection tree belongs to the library on screen: filter the files
    // instead of leaving the view the user is browsing.
    return
  }
  view.value = 'library'
  await loadLibrary()
}
export async function filterByArtifactType(artifactType: LibraryItem['item_type'] | null): Promise<void> {
  selectedLibraryType.value = artifactType
  // A status belongs to cards, so another type cannot keep a status filter.
  if (artifactType !== null && artifactType !== 'card') selectedCardStatuses.value = []
  await loadLibrary()
}
/** Replace the library's status filter and reload what it shows. */
export async function setCardStatuses(next: CardStatus[]): Promise<void> {
  selectedCardStatuses.value = next
  await loadLibrary()
}
export function markCardStatusUpdating(id: string, updating: boolean): void {
  const next = new Set(cardStatusUpdatingIds.value)
  if (updating) next.add(id)
  else next.delete(id)
  cardStatusUpdatingIds.value = next
}
export function announceCardStatus(title: string, status: CardStatus): void {
  showNotice(t('cardStatus.updated', { title, status: t(cardStatusLabel(status)) }))
}
/** Move a library card to a new status. It takes effect at once: no draft, no save. */
export async function setLibraryCardStatus(item: LibraryItem, status: CardStatus): Promise<void> {
  if (cardStatusUpdatingIds.value.has(item.id)) return
  markCardStatusUpdating(item.id, true)
  try {
    const updated = await libraryClient.setCardStatus(item.id, status)
    if (selectedLibraryItem.value?.id === item.id) selectedLibraryItem.value = updated
    if (selectedCardStatuses.value.length && !selectedCardStatuses.value.includes(status)) {
      // The card no longer matches the filter, so the grid and its count must be reread.
      await loadLibrary()
    } else {
      libraryItems.value = libraryItems.value.map((candidate) => (candidate.id === item.id ? updated : candidate))
    }
    announceCardStatus(item.title, status)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    markCardStatusUpdating(item.id, false)
  }
}
