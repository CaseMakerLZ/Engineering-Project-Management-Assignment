import { API_BASE_URL, REQUEST_TIMEOUT_MS } from '../config'
import { ApiError } from '../lib/errors'
import { clearToken, getToken } from '../lib/token'
import type { ResultEnvelope } from '../types/api'

export const AUTH_EXPIRED_EVENT = 'agentdesk:auth-expired'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean
  timeoutMs?: number
}

function endpoint(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}

function emitAuthExpired(): void {
  clearToken()
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true, timeoutMs = REQUEST_TIMEOUT_MS } = options
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getToken()

  if (auth && token) {
    headers.Authorization = `Bearer ${token}`
  }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json; charset=utf-8'
  }

  let response: Response
  try {
    response = await fetch(endpoint(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请稍后重试。', 0)
    }
    throw new TypeError('网络请求失败')
  } finally {
    window.clearTimeout(timeout)
  }

  const rawBody = await response.text()
  let payload: ResultEnvelope<T> | null = null

  if (rawBody) {
    try {
      payload = JSON.parse(rawBody) as ResultEnvelope<T>
    } catch {
      throw new ApiError('服务器返回了无法解析的响应。', response.status)
    }
  }

  const code = typeof payload?.code === 'number' ? payload.code : undefined
  const successful = response.ok && code === 0

  if (!successful) {
    const shouldExpire =
      auth &&
      (code === 10002 || (response.status === 401 && code !== 20002))

    if (shouldExpire) {
      emitAuthExpired()
    }

    throw new ApiError(
      payload?.msg?.trim() || `请求失败（HTTP ${response.status}）`,
      response.status,
      code,
      payload?.data,
    )
  }

  return payload?.data as T
}
