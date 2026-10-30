import { ApiError } from '../lib/errors'
import { REQUEST_TIMEOUT_MS } from '../config'
import { bearerHeaders, emitAuthExpired, endpoint } from './client'

export async function openTurnEventStream(
  conversationId: string,
  taskId: string,
  signal: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
  let response: Response
  const requestController = new AbortController()
  const forwardAbort = () => requestController.abort()
  signal.addEventListener('abort', forwardAbort, { once: true })
  const handshakeTimer = window.setTimeout(
    () => requestController.abort(),
    REQUEST_TIMEOUT_MS,
  )
  try {
    response = await fetch(
      endpoint(
        `/api/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(taskId)}/events`,
      ),
      {
        method: 'GET',
        headers: {
          ...bearerHeaders('text/event-stream'),
          'Cache-Control': 'no-cache',
        },
        signal: requestController.signal,
      },
    )
  } catch {
    if (signal.aborted) {
      throw new DOMException('Request aborted', 'AbortError')
    }
    if (requestController.signal.aborted) {
      throw new TypeError('实时连接握手超时')
    }
    throw new TypeError('实时连接网络请求失败')
  } finally {
    window.clearTimeout(handshakeTimer)
  }

  if (!response.ok) {
    let message = `实时连接失败（HTTP ${response.status}）`
    let code: number | undefined
    try {
      const payload = (await response.json()) as {
        msg?: string
        code?: number
      }
      message = payload.msg?.trim() || message
      code = typeof payload.code === 'number' ? payload.code : undefined
    } catch {
      // Non-JSON handshake errors still retain their HTTP status.
    }
    if (response.status === 401 || code === 10002) emitAuthExpired()
    throw new ApiError(message, response.status, code)
  }

  const contentType = response.headers.get('Content-Type')?.toLowerCase() ?? ''
  if (!contentType.includes('text/event-stream')) {
    throw new ApiError('服务器没有返回 SSE 事件流。', 0)
  }
  if (!response.body) {
    throw new ApiError('服务器事件流没有可读取内容。', 0)
  }
  return response.body
}
