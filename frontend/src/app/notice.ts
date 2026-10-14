import { ref } from 'vue'
import { ApiError } from '../api/client'
import type { ConfirmationState, NoticeKind } from './types'

export const notice = ref('')
export const noticeKind = ref<NoticeKind>('success')
export const confirmation = ref<ConfirmationState>({ open: false, title: '', message: '', confirmLabel: 'Delete' })
export const noticeScratch = {
  resolveConfirmation: null as ((confirmed: boolean) => void) | null,
}
export function showNotice(message: string, kind: NoticeKind = 'success'): void {
  notice.value = message
  noticeKind.value = kind
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3200)
}
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : 'Something went wrong'
}
export function requestConfirmation(title: string, message: string, confirmLabel: string): Promise<boolean> {
  noticeScratch.resolveConfirmation?.(false)
  confirmation.value = { open: true, title, message, confirmLabel }
  return new Promise((resolve) => {
    noticeScratch.resolveConfirmation = resolve
  })
}
export function settleConfirmation(confirmed: boolean): void {
  confirmation.value = { ...confirmation.value, open: false }
  noticeScratch.resolveConfirmation?.(confirmed)
  noticeScratch.resolveConfirmation = null
}
