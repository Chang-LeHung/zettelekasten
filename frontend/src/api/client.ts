import { agentArtifactApi } from './agent/artifacts'
import { agentSessionApi } from './agent/sessions'
import { sessionAssetApi } from './agent/sessionAssets'
import { agentStreamApi } from './agent/stream'
import { providerApi } from './providers'

export { ApiError } from './http'
export { assetClient } from './assets'
export { channelClient } from './channels'
export { libraryClient } from './library'
export { scheduledTaskClient } from './scheduledTasks'
export { healthClient, settingsClient, updateClient } from './runtime'
export { tagClient } from './tags'

/**
 * The agent conversation API: streaming turns, sessions, session assets, artifacts, and
 * model providers. Each group lives in its own module; this object is what callers use.
 */
export const aiClient = {
  ...agentStreamApi,
  ...agentSessionApi,
  ...sessionAssetApi,
  ...agentArtifactApi,
  ...providerApi,
}
