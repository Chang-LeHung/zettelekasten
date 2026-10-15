export const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(apiErrorMessage(status, body))
  }
}

function apiErrorMessage(status: number, body: string): string {
  try {
    const payload = JSON.parse(body) as Record<string, unknown>
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
    const nested = payload.error
    if (nested && typeof nested === 'object') {
      const message = (nested as Record<string, unknown>).message
      if (typeof message === 'string' && message.trim()) return message
    }
  } catch {
    const plainText = body.trim()
    if (plainText && !plainText.startsWith('<')) return plainText
  }
  return `Request failed (${status})`
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return response.json() as Promise<T>
}
