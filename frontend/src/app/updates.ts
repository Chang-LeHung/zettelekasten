import { ref } from 'vue'
import { updateClient } from '../api/client'
import type { UpdateStatus } from '../api/types'
import { waitForRestart } from '../utils/serverRestart'
import { t } from './i18n'
import { errorMessage, showNotice } from './notice'

/** What PyPI offers for this copy, and how it would install it. */
export const updateStatus = ref<UpdateStatus | null>(null)
const updateChecking = ref(false)
export const updateInstalling = ref(false)
export const updateRestarting = ref(false)
/**
 * Ask PyPI, through the backend's cache, whether a newer release exists. The
 * backend reuses an answer for hours, so this is cheap to call on every start.
 */
async function refreshUpdateStatus(refresh = false): Promise<void> {
  if (updateChecking.value || updateInstalling.value) return
  updateChecking.value = true
  try {
    updateStatus.value = await updateClient.get(refresh)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    updateChecking.value = false
  }
}
/**
 * Download the release and let the installer that owns this copy replace it.
 * The running process keeps the old code, so the answer asks for a restart.
 */
export async function installAvailableUpdate(): Promise<void> {
  const version = updateStatus.value?.latest
  if (!version || updateInstalling.value) return
  updateInstalling.value = true
  try {
    const result = await updateClient.install(version)
    if (!result.ok) {
      showNotice(result.detail || t('The installer failed'), 'error')
      return
    }
    showNotice(t('Installed {version} — restart Zett to use it', { version: result.version }))
    // Asked directly: refreshUpdateStatus() refuses while an install is running, and this one
    // still is until the `finally` below, so going through it left the button offering the
    // update that had just been installed. The cached answer is enough: what changed is the disk.
    updateStatus.value = await updateClient.get()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    updateInstalling.value = false
  }
}
/**
 * Restart this server so the release that was just installed is the one running.
 * A helper stops the process that answers, so the page waits until a server that no
 * longer asks for a restart answers, and then reloads to pick up its interface.
 */
export async function restartZett(): Promise<void> {
  if (updateRestarting.value) return
  updateRestarting.value = true
  try {
    const result = await updateClient.restart()
    if (!result.ok) {
      showNotice(result.detail || t('Zett could not restart itself'), 'error')
      return
    }
    const back = await waitForRestart({
      now: () => Date.now(),
      sleep: (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds)),
      stillNeedsRestart: async () => (await updateClient.get()).restart_required,
    })
    if (back) {
      window.location.reload()
      return
    }
    showNotice(t('Zett did not come back; run `zett start` in a terminal'), 'error')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    updateRestarting.value = false
  }
}
