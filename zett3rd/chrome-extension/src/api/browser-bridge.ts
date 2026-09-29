import { BrowserExecutor, validateCommand, type BrowserCommand } from '../page/browser-executor'

export interface BrowserConsent {
  command: BrowserCommand
  approve: () => void
  reject: () => void
}

/** An explicitly connected panel owns its socket, tab, and pending consent.
 * No reconnect/replay: every reconnect requires a new user click and token.
 */
export class BrowserBridgeClient {
  private socket?: WebSocket
  private executor?: BrowserExecutor
  private heartbeat?: ReturnType<typeof setInterval>
  private consent?: (approved: boolean) => void
  private consentTimer?: ReturnType<typeof setTimeout>
  private activeId?: string
  private seen = new Set<string>()
  private generation = 0
  token?: string
  tabId?: number
  /** Set while the panel's session-level "always allow page edits" choice is on. */
  autoApprove = false

  constructor(private onConsent: (consent: BrowserConsent | null) => void, private onClose: (reason: string) => void) {}

  async connect(url: string, tabId: number): Promise<void> {
    await this.disconnect()
    const generation = this.generation
    this.tabId = tabId
    const executor = new BrowserExecutor(tabId)
    this.executor = executor
    try {
      await executor.connect()
      if (generation !== this.generation) { await executor.disconnect(); throw new Error('Connection cancelled') }
      const socket = new WebSocket(url)
      this.socket = socket
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Browser connection timed out')), 8000)
        socket.onmessage = event => {
          if (generation !== this.generation) return
          try {
            if (typeof event.data !== 'string' || event.data.length > 100000) throw new Error('Invalid browser frame')
            const data = JSON.parse(event.data)
            if (!this.token) {
              if (data.type !== 'ready' || typeof data.token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(data.token)) throw new Error('Invalid browser handshake')
              this.token = data.token
              clearTimeout(timer)
              resolve()
            } else if (data.type === 'cancel') {
              if (data.id === this.activeId) {
                this.consent?.(false)
                // Execution already started has uncertain effects: disconnect,
                // so it cannot be followed by a fresh command on this socket.
                if (!this.consent) {
                  this.onClose('Browser command expired. Inspect the page before reconnecting.')
                  void this.disconnect()
                }
              }
            } else if (data.type !== 'pong') {
              void this.handle(validateCommand(data), generation)
            }
          } catch (error) {
            clearTimeout(timer)
            reject(error)
            this.onClose((error as Error).message)
            void this.disconnect()
          }
        }
        socket.onerror = () => { clearTimeout(timer); reject(new Error('Cannot connect browser WebSocket')) }
        socket.onclose = () => {
          clearTimeout(timer)
          reject(new Error('Browser WebSocket closed'))
          if (generation === this.generation) {
            void this.disconnect()
            this.onClose('Browser disconnected. Reconnect the page to use browser tools.')
          }
        }
      })
      this.heartbeat = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ping' }))
      }, 15000)
    } catch (error) {
      await this.disconnect()
      throw error
    }
  }

  private async handle(command: BrowserCommand, generation: number): Promise<void> {
    if (this.seen.has(command.id)) return
    if (this.activeId || this.seen.size >= 1000) {
      this.reply(command.id, { ok: false, error: 'Browser is busy or connection limit reached; reconnect before another run' })
      return
    }
    this.seen.add(command.id)
    this.activeId = command.id
    try {
      if (command.operation !== 'snapshot' && !this.autoApprove) {
        const approved = await new Promise<boolean>(resolve => {
          this.consent = resolve
          this.consentTimer = setTimeout(() => resolve(false), 90000)
          this.onConsent({ command, approve: () => resolve(true), reject: () => resolve(false) })
        })
        clearTimeout(this.consentTimer)
        this.consent = undefined
        this.onConsent(null)
        if (!approved) throw new Error('User declined the DOM change or approval expired')
      }
      if (generation !== this.generation || !this.executor) return
      const result = await this.executor.execute(command)
      if (generation === this.generation) this.reply(command.id, result)
    } catch (error) {
      if (generation === this.generation) this.reply(command.id, { ok: false, error: (error as Error).message.slice(0, 1000) })
    } finally {
      if (generation === this.generation) this.activeId = undefined
    }
  }

  private reply(id: string, result: { ok: boolean; result?: string; error?: string }): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'result', id, ...result }))
  }

  async disconnect(): Promise<void> {
    this.generation++
    clearInterval(this.heartbeat)
    clearTimeout(this.consentTimer)
    this.consent?.(false)
    this.consent = undefined
    this.onConsent(null)
    this.token = undefined
    this.tabId = undefined
    this.activeId = undefined
    this.seen.clear()
    const socket = this.socket
    this.socket = undefined
    if (socket) { socket.onclose = null; socket.onmessage = null; socket.onerror = null; socket.close() }
    const executor = this.executor
    this.executor = undefined
    await executor?.disconnect()
  }
}
