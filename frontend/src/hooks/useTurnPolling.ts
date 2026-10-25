import { useCallback, useEffect, useRef, useState } from 'react'
import { getTurn } from '../api/conversations'
import {
  POLL_INITIAL_DELAY_MS,
  POLL_MAX_DELAY_MS,
  POLL_MAX_WAIT_MS,
} from '../config'
import { ApiError, describeError } from '../lib/errors'
import type { Turn } from '../types/api'

interface UseTurnPollingOptions {
  conversationId: string | null
  activeTaskIds: string[]
  onTurns: (turns: Turn[]) => void
  onSettled?: () => void
}

interface PollingState {
  pollingError: string | null
  timedOut: boolean
  resumePolling: () => void
}

function isActive(status: Turn['status']): boolean {
  return status === 'CREATED' || status === 'RUNNING'
}

function isFatalPollingError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  if (error.code === 10002 || error.code === 10003 || error.code === 10004) return true
  if (error.code === 30003 || error.code === 30004 || error.code === 30006) return true
  return error.status === 401 || error.status === 403 || error.status === 404
}

export function useTurnPolling({
  conversationId,
  activeTaskIds,
  onTurns,
  onSettled,
}: UseTurnPollingOptions): PollingState {
  const [pollingError, setPollingError] = useState<string | null>(null)
  const [timedOut, setTimedOut] = useState(false)
  const [restartToken, setRestartToken] = useState(0)
  const onTurnsRef = useRef(onTurns)
  const onSettledRef = useRef(onSettled)
  const activeKey = [...activeTaskIds].sort().join('|')

  onTurnsRef.current = onTurns
  onSettledRef.current = onSettled

  useEffect(() => {
    setTimedOut(false)
    setPollingError(null)
  }, [activeKey])

  useEffect(() => {
    if (!conversationId || !activeKey) return

    const taskIds = activeKey.split('|').filter(Boolean)
    let cancelled = false
    let timer: number | undefined
    let delay = POLL_INITIAL_DELAY_MS
    const deadline = Date.now() + POLL_MAX_WAIT_MS

    const scheduleNext = () => {
      if (cancelled) return
      delay = Math.min(Math.round(delay * 1.35), POLL_MAX_DELAY_MS)
      timer = window.setTimeout(() => void tick(), delay)
    }

    const tick = async () => {
      if (cancelled) return
      if (Date.now() >= deadline) {
        setTimedOut(true)
        return
      }

      const results = await Promise.allSettled(
        taskIds.map((taskId) => getTurn(conversationId, taskId)),
      )
      if (cancelled) return

      const updatedTurns: Turn[] = []
      const errors: unknown[] = []
      results.forEach((result) => {
        if (result.status === 'fulfilled') updatedTurns.push(result.value)
        else errors.push(result.reason)
      })

      if (updatedTurns.length) {
        onTurnsRef.current(updatedTurns)
      }

      const fatalError = errors.find(isFatalPollingError)
      if (fatalError) {
        setPollingError(describeError(fatalError))
        onSettledRef.current?.()
        return
      }

      if (errors.length) {
        setPollingError('暂时无法获取最新任务状态，正在自动重试…')
      } else {
        setPollingError(null)
      }

      const stillActive = updatedTurns.filter((turn) => isActive(turn.status))
      if (errors.length === 0 && stillActive.length === 0) {
        onSettledRef.current?.()
        return
      }

      scheduleNext()
    }

    timer = window.setTimeout(() => void tick(), POLL_INITIAL_DELAY_MS)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [activeKey, conversationId, restartToken])

  const resumePolling = useCallback(() => {
    setTimedOut(false)
    setPollingError(null)
    setRestartToken((current) => current + 1)
  }, [])

  return { pollingError, timedOut, resumePolling }
}
