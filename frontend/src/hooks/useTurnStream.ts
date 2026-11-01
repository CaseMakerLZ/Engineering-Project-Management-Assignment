import { useCallback, useEffect, useRef, useState } from 'react'
import { getTurn } from '../api/conversations'
import { openTurnEventStream } from '../api/turnEvents'
import { ApiError, describeError } from '../lib/errors'
import { readSSEStream, SSEProtocolError } from '../lib/sseParser'
import { reduceTurnEvent } from '../lib/turnEventReducer'
import type { TaskStatus, Turn } from '../types/api'
import type { TurnStreamState } from '../types/turnEvents'

const TERMINAL_STATUSES = new Set<TaskStatus>(['COMPLETED', 'FAILED', 'CANCELLED'])
const NO_RETRY_CODES = new Set(['STREAM_STATE_LOST', 'PERSISTENCE_FAILED'])

class StreamStoppedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'StreamStoppedError'
  }
}

function initialState(status: TaskStatus): TurnStreamState {
  return {
    status,
    messages: [],
    activeTool: null,
    tools: [],
    connectionStatus: 'connecting',
    sequence: 0,
    result: null,
    error: null,
    channelError: null,
    reconnectAttempt: 0,
  }
}

function isTerminal(status: TaskStatus): boolean {
  return TERMINAL_STATUSES.has(status)
}

function shouldRetry(error: unknown): boolean {
  if (error instanceof StreamStoppedError || error instanceof SSEProtocolError) return false
  if (!(error instanceof ApiError)) return true
  if ([400, 401, 403, 404, 429].includes(error.status)) return false
  return error.status === 0 || error.status >= 500
}

interface UseTurnStreamOptions {
  conversationId: string
  taskId: string
  initialStatus: TaskStatus
  reconnectToken: number
  onUpdate: (taskId: string, state: TurnStreamState) => void
  onSettled: (taskId: string) => void
}

export function useTurnStream({
  conversationId,
  taskId,
  initialStatus,
  reconnectToken,
  onUpdate,
  onSettled,
}: UseTurnStreamOptions): {
  streamState: TurnStreamState
  reconnect: () => void
} {
  const [streamState, setStreamState] = useState(() => initialState(initialStatus))
  const [restartToken, setRestartToken] = useState(0)
  const stateRef = useRef(streamState)
  const onUpdateRef = useRef(onUpdate)
  const onSettledRef = useRef(onSettled)
  onUpdateRef.current = onUpdate
  onSettledRef.current = onSettled

  const commit = useCallback((next: TurnStreamState) => {
    stateRef.current = next
    setStreamState(next)
    onUpdateRef.current(taskId, next)
  }, [taskId])

  const reconnect = useCallback(() => {
    setStreamState((current) => ({
      ...current,
      connectionStatus: 'connecting',
      channelError: null,
    }))
    setRestartToken((current) => current + 1)
  }, [])

  useEffect(() => {
    let disposed = false
    let controller: AbortController | null = null
    let retryTimer: number | undefined
    let reconnectAttempt = 0
    let settled = false

    const markSettled = () => {
      if (settled) return
      settled = true
      onSettledRef.current(taskId)
    }

    const compensate = async (message: string) => {
      let compensated: Turn | null = null
      try {
        compensated = await getTurn(conversationId, taskId)
      } catch {
        // The original stream error remains the user-facing explanation.
      }
      if (disposed) return

      const current = stateRef.current
      const next: TurnStreamState = {
        ...current,
        connectionStatus: 'disconnected',
        channelError: message,
        status: compensated?.status ?? current.status,
        result:
          typeof compensated?.result === 'string'
            ? compensated.result
            : current.result,
        error:
          typeof compensated?.error === 'string'
            ? compensated.error
            : current.error,
        activeTool: compensated && isTerminal(compensated.status) ? null : current.activeTool,
      }
      commit(next)
      if (isTerminal(next.status)) markSettled()
    }

    const connect = async (isRetry: boolean) => {
      if (disposed) return
      controller?.abort()
      controller = new AbortController()
      commit({
        ...stateRef.current,
        connectionStatus: isRetry ? 'reconnecting' : 'connecting',
        reconnectAttempt,
        channelError: isRetry ? stateRef.current.channelError : null,
      })

      try {
        const body = await openTurnEventStream(
          conversationId,
          taskId,
          controller.signal,
        )
        if (disposed) return
        commit({
          ...stateRef.current,
          connectionStatus: 'connected',
          channelError: null,
          sequence: 0,
        })

        for await (const frame of readSSEStream(body)) {
          if (disposed) return
          const next = reduceTurnEvent(stateRef.current, frame)
          commit(next)

          if (frame.event === 'stream.error') {
            const data = frame.data as { retryable?: boolean; code?: string }
            if (
              data.retryable === false ||
              (typeof data.code === 'string' && NO_RETRY_CODES.has(data.code))
            ) {
              throw new StreamStoppedError(next.channelError || '实时连接无法继续。')
            }
            throw new TypeError('实时连接暂时中断')
          }

          if (isTerminal(next.status)) {
            commit({ ...next, connectionStatus: 'disconnected', activeTool: null })
            markSettled()
            return
          }
        }
        if (!disposed) throw new TypeError('实时连接意外结束')
      } catch (error) {
        if (disposed || (error instanceof DOMException && error.name === 'AbortError')) {
          return
        }
        if (
          error instanceof ApiError &&
          [400, 401, 403, 404, 429].includes(error.status)
        ) {
          commit({
            ...stateRef.current,
            connectionStatus: 'disconnected',
            channelError: describeError(error),
          })
          return
        }
        const stopped =
          error instanceof StreamStoppedError || !shouldRetry(error)
        if (stopped) {
          const message =
            error instanceof StreamStoppedError
              ? error.message
              : describeError(error)
          await compensate(message)
          return
        }

        if (reconnectAttempt >= 3) {
          await compensate('实时连接中断，后台任务可能仍在运行。可手动重连或刷新。')
          return
        }

        reconnectAttempt += 1
        const delay = 1_000 * 2 ** (reconnectAttempt - 1)
        commit({
          ...stateRef.current,
          connectionStatus: 'reconnecting',
          reconnectAttempt,
          channelError: '实时连接暂时中断，正在重新连接…',
        })
        retryTimer = window.setTimeout(() => void connect(true), delay)
      }
    }

    void connect(false)
    return () => {
      disposed = true
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
      controller?.abort()
    }
  }, [commit, conversationId, reconnectToken, restartToken, taskId])

  return { streamState, reconnect }
}
