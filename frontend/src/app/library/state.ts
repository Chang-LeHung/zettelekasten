import { computed, ref } from 'vue'
import type { CardStatus, CardType, LibraryItem, StaticAsset, Tag } from '../../api/types'
import type { Box } from '../../utils/multiSelect'
import { visibleTagRows } from '../../utils/tagTree'
import { t } from '../i18n'
import { view } from '../nav'

export const libraryItems = ref<LibraryItem[]>([])
export const selectedLibraryItem = ref<LibraryItem | null>(null)
export const fullscreenSlidesItem = ref<LibraryItem | null>(null)
export const libraryPdfLaunch = ref<{ item: LibraryItem; mode: 'expanded' | 'presentation' } | null>(null)
export const librarySlidesStage = ref<HTMLElement | null>(null)
export const libraryScratch = {
  slidesPreviewTrigger: null as HTMLElement | null,
  libraryRequestId: 0,
  libraryObserver: null as IntersectionObserver | null,
  selectionAnchorId: null as string | null,
}
export const libraryEditorItem = ref<LibraryItem | null>(null)
export const libraryEditorArtifactId = ref<string | null>(null)
export const libraryEditorSaving = ref(false)
/**
 * Cards fetched per request. The sentinel under the grid turns this into the
 * step size of one scroll, not a ceiling on what the library shows.
 */
export const LIBRARY_PAGE_SIZE = 60
export const libraryLoading = ref(false)
export const libraryLoadingMore = ref(false)
export const libraryHasMore = ref(false)
export const libraryTotal = ref<number | null>(null)
export const librarySentinel = ref<HTMLElement | null>(null)
export const deletingLibraryItemId = ref<string | null>(null)
/** Cards picked with the mouse; any selection turns a click on a card into a toggle. */
export const selectedLibraryIds = ref<Set<string>>(new Set())
export const libraryMarquee = ref<Box | null>(null)
export const bulkDeleting = ref(false)
export const selectingLibrary = computed(() => selectedLibraryIds.value.size > 0)
export const selectedLibraryItems = computed(() => libraryItems.value.filter((item) => selectedLibraryIds.value.has(item.id)))
export const draggingLibraryItem = ref<LibraryItem | null>(null)
export const draggingStaticAsset = ref<StaticAsset | null>(null)
export const tagDropTargetId = ref<string | null>(null)
export const tagAssignmentBusy = ref(false)
/**
 * The collection tree of the library being browsed, and the only one this app
 * ever shows: the sidebar, the manager, and every count read from it belong to
 * the library on screen, because the artifact library and the static asset
 * library keep separate trees.
 */
export const collectionTags = ref<Tag[]>([])
export const collapsedTagIds = ref<Set<string>>(new Set())
export const hoveredTagId = ref<string | null>(null)
export const tagManagerOpen = ref(false)
export const tagManagerBusy = ref(false)
export const tagManagerFeedback = ref('')
export const tagManagerFeedbackKind = ref<'success' | 'error'>('success')
export const query = ref('')
export const activeQuery = ref('')
export const selectedTag = ref<string | null>(null)
export const selectedLibraryType = ref<LibraryItem['item_type'] | null>(null)
//: Card statuses the library keeps; empty means every card regardless of status.
export const selectedCardStatuses = ref<CardStatus[]>([])
//: Artifact ids whose status change is in flight, so one click cannot double-send.
export const cardStatusUpdatingIds = ref<ReadonlySet<string>>(new Set())
export const collectionTarget = computed<'artifact' | 'asset'>(() => (view.value === 'assets' ? 'asset' : 'artifact'))
export const searchInput = ref<HTMLInputElement | null>(null)
export const cardTypes: CardType[] = ['note', 'idea', 'quote', 'todo', 'reference']
export const libraryTypeFilters: Array<{ value: LibraryItem['item_type'] | null; label: string }> = [
  { value: null, label: 'All' },
  { value: 'card', label: 'Cards' },
  { value: 'article', label: 'Articles' },
  { value: 'slides', label: 'Slides' },
  { value: 'latex_pdf', label: 'PDFs' },
]
export const flatTags = computed(() => visibleTagRows(collectionTags.value, collapsedTagIds.value))
export const selectedTagName = computed(() => flatTags.value.find((tag) => tag.id === selectedTag.value)?.path)
export const pageTitle = computed(() => {
  if (view.value === 'search') {
    return activeQuery.value
      ? t('Results for “{query}”', { query: activeQuery.value })
      : t('Search library')
  }
  return selectedTagName.value || t('All knowledge')
})
export const pageDescription = computed(() => {
  // The header names the whole library, so a paged grid still counts every match.
  const count = libraryTotal.value ?? libraryItems.value.length
  return view.value === 'search'
    ? t('{count} matching items', { count })
    : t('{count} items in your library', { count })
})
/**
 * Identity of the query on screen. The grid is keyed by it, so a filter that
 * lands on a different set remounts its cards and replays the float-in, while
 * the next page of the same query keeps the loaded nodes instead of animating
 * the whole grid again.
 */
export const libraryGridKey = computed(() => [
  view.value,
  view.value === 'search' ? activeQuery.value : '',
  selectedTag.value ?? '',
  selectedLibraryType.value ?? '',
].join('|'))
export const MARQUEE_EDGE = 64
export const NOT_A_MARQUEE_START = '.card, button, a, input, select, textarea, label, summary, [role="button"], [role="dialog"], .library-bulk-bar'
