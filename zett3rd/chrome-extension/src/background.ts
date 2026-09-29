/** Toolbar and same-tab navigation keep the embedded panel in the webpage.
 * One storage.session key per tab avoids read/modify/write races when two
 * webpages open concurrently; these flags do not survive a browser restart.
 */
import { belongsToTab } from './chat/page-sessions'

function openKey(tabId: number): string {
  return `embeddedPanelTab:${tabId}`
}

async function showPanel(tabId: number, mode: 'toggle-panel' | 'ensure-panel'): Promise<boolean> {
  try {
    await chrome.scripting.executeScript({
      target: { tabId, frameIds: [0] },
      files: ['content-script.js'],
      world: 'ISOLATED',
    })
    const result = await chrome.tabs.sendMessage(tabId, {
      channel: 'zett-dom', type: mode, tabId,
    }, { frameId: 0 })
    return result?.open === true
  } catch (error) {
    console.error('Zettelekasten: cannot open this webpage', error)
    return false
  }
}

chrome.action.onClicked.addListener(async tab => {
  if (tab.id === undefined || !tab.url || !/^https?:\/\//.test(tab.url)) return
  const open = await showPanel(tab.id, 'toggle-panel')
  if (open) await chrome.storage.session.set({ [openKey(tab.id)]: true })
  else await chrome.storage.session.remove(openKey(tab.id))
})

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete' || !tab.url || !/^https?:\/\//.test(tab.url)) return
  void (async () => {
    if ((await chrome.storage.session.get(openKey(tabId)))[openKey(tabId)] !== true) return
    await showPanel(tabId, 'ensure-panel')
  })()
})

chrome.tabs.onRemoved.addListener(tabId => {
  void (async () => {
    await chrome.storage.session.remove(openKey(tabId))
    // Chrome may reuse numeric tab IDs after a restart. Do not attach a new
    // webpage to a conversation that belonged to a closed tab.
    const records = await chrome.storage.local.get(null)
    const keys = Object.keys(records).filter(key => belongsToTab(key, tabId))
    if (keys.length) await chrome.storage.local.remove(keys)
  })()
})

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== 'embedded-panel-closed' || sender.id !== chrome.runtime.id
    || sender.tab?.id !== message.tabId) return
  void chrome.storage.session.remove(openKey(message.tabId))
})
