import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  Clock3,
  MessageSquareDashed,
  RefreshCw,
  RotateCcw,
  Sparkles,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import {
  createTurn,
  getConversation,
  listTurns,
} from '../api/conversations'
import { ApiError, describeError, isResourceNotFound } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import type { Conversation, CreateTurnResponse, Turn } from '../types/api'
import { useProjectWorkspace } from '../components/ProjectWorkspaceLayout'
import { Composer } from '../components/Composer'
import { EmptyState } from '../components/EmptyState'
import { isActiveStatus } from '../components/StatusPill'
import { TurnCard } from '../components/TurnCard'
import { useToast } from '../components/ToastProvider'
import { useTurnPolling } from '../hooks/useTurnPolling'

function sortTurns(items: Turn[]): Turn[] {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.created_at).getTime()
    const rightTime = new Date(right.created_at).getTime()
    if (leftTime !== rightTime) return leftTime - rightTime
    return left.task_id.localeCompare(right.task_id)
  })
}

function mergeTurns(current: Turn[], incoming: Turn[]): Turn[] {
  const incomingById = new Map(incoming.map((turn) => [turn.task_id, turn]))
  const merged = current.map((turn) => incomingById.get(turn.task_id) ?? turn)
  const knownIds = new Set(merged.map((turn) => turn.task_id))
  incoming.forEach((turn) => {
    if (!knownIds.has(turn.task_id)) {
      merged.push(turn)
      knownIds.add(turn.task_id)
    }
  })
  return sortTurns(merged)
}

export function ConversationPage() {
  const { conversationId = '' } = useParams()
  const { project, refreshConversations } = useProjectWorkspace()
  const { pushToast } = useToast()
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitInFlight, setSubmitInFlight] = useState(false)
  const [reloadVersion, setReloadVersion] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const initialScrollDoneRef = useRef(false)
  const forceScrollRef = useRef(false)
  const submittingRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setConversation(null)
    setTurns([])
    initialScrollDoneRef.current = false

    const loadConversation = async () => {
      try {
        const [conversationData, turnData] = await Promise.all([
          getConversation(conversationId),
          listTurns(conversationId),
        ])
        if (cancelled) return
        setConversation(conversationData)
        setTurns(sortTurns(Array.isArray(turnData) ? turnData : []))
      } catch (loadError) {
        if (cancelled) return
        setError(
          isResourceNotFound(loadError)
            ? '对话不存在、已被删除，或当前账号无权访问。'
            : describeError(loadError),
        )
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadConversation()
    return () => {
      cancelled = true
    }
  }, [conversationId, reloadVersion])

  useEffect(() => {
    if (!conversation) return
    document.title = `${conversation.title} · ${project.name} · AgentDesk`
  }, [conversation, project.name])

  const activeTaskIds = useMemo(
    () => turns.filter((turn) => isActiveStatus(turn.status)).map((turn) => turn.task_id),
    [turns],
  )

  const busy = activeTaskIds.length > 0 || submitInFlight
  const lastTurnStatus = turns.at(-1)?.status

  const handlePolledTurns = useCallback((incoming: Turn[]) => {
    setTurns((current) => mergeTurns(current, incoming))
  }, [])

  const handleSettled = useCallback(() => {
    void refreshConversations()
  }, [refreshConversations])

  const polling = useTurnPolling({
    conversationId: conversation?.conversation_id ?? null,
    activeTaskIds,
    onTurns: handlePolledTurns,
    onSettled: handleSettled,
  })

  useEffect(() => {
    const element = scrollRef.current
    if (!element || turns.length === 0) return
    if (!initialScrollDoneRef.current) {
      element.scrollTop = element.scrollHeight
      initialScrollDoneRef.current = true
      return
    }
    if (forceScrollRef.current) {
      element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
      forceScrollRef.current = false
      return
    }
    const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight
    if (distanceToBottom < 220) {
      element.scrollTo({
        top: element.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [turns.length, lastTurnStatus, activeTaskIds.length])

  const refreshHistory = useCallback(async () => {
    try {
      const data = await listTurns(conversationId)
      setTurns(sortTurns(Array.isArray(data) ? data : []))
      void refreshConversations()
    } catch (refreshError) {
      pushToast(describeError(refreshError), 'error')
    }
  }, [conversationId, pushToast, refreshConversations])

  const sendPrompt = useCallback(
    async (prompt: string) => {
      if (submittingRef.current) {
        throw new ApiError('同一时间只能提交一个任务。', 409, 30005)
      }

      submittingRef.current = true
      setSubmitInFlight(true)
      try {
        const response: CreateTurnResponse = await createTurn(conversationId, { prompt })
        if (!response.task_id) {
          throw new Error('服务器未返回 task_id，请重试。')
        }
        const pendingTurn: Turn = {
          task_id: response.task_id,
          conversation_id: response.conversation_id || conversationId,
          python_run_id: response.python_run_id,
          prompt,
          status: response.status || 'CREATED',
          result: null,
          error: null,
          created_at: new Date().toISOString(),
        }
        if (mountedRef.current) {
          forceScrollRef.current = true
          setTurns((current) => mergeTurns(current, [pendingTurn]))
          void refreshConversations()
        }
      } finally {
        submittingRef.current = false
        if (mountedRef.current) setSubmitInFlight(false)
      }
    },
    [conversationId, refreshConversations],
  )

  const handleRetry = (prompt: string) => {
    void sendPrompt(prompt).catch((retryError: unknown) => {
      pushToast(describeError(retryError), 'error')
      if (
        retryError &&
        typeof retryError === 'object' &&
        'code' in retryError &&
        retryError.code === 30005
      ) {
        void refreshHistory()
      }
    })
  }

  if (loading) {
    return (
      <div className="conversation-page conversation-loading">
        <div className="conversation-loading-header">
          <i />
          <i />
        </div>
        <div className="conversation-loading-body">
          <span className="loading-orb" />
          <p>正在加载对话记录…</p>
        </div>
      </div>
    )
  }

  if (error || !conversation) {
    return (
      <div className="conversation-page conversation-error-page">
        <div className="conversation-error-card">
          <span className="workspace-error-icon">
            <MessageSquareDashed size={27} />
          </span>
          <span className="eyebrow">CONVERSATION UNAVAILABLE</span>
          <h1>无法打开这段对话</h1>
          <p>{error || '对话不存在或已被删除。'}</p>
          <div className="error-actions">
            <Link to={`/projects/${project.project_id}`} className="btn btn-primary">
              <ArrowLeft size={16} />
              返回项目
            </Link>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setReloadVersion((current) => current + 1)}
            >
              <RotateCcw size={16} />
              重试
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="conversation-page">
      <header className="conversation-header">
        <div className="conversation-title-group">
          <Link
            to={`/projects/${project.project_id}`}
            className="icon-btn conversation-back"
            aria-label="返回项目"
          >
            <ArrowLeft size={18} />
          </Link>
          <div>
            <span className="conversation-project-label">
              <Sparkles size={12} />
              {project.name}
            </span>
            <h1>{conversation.title}</h1>
          </div>
        </div>
        <div className="conversation-header-actions">
          <span className="conversation-updated" title={formatDateTime(conversation.updated_at)}>
            <Clock3 size={13} />
            {formatDateTime(conversation.updated_at)}
          </span>
          <button
            type="button"
            className="icon-btn"
            onClick={() => void refreshHistory()}
            aria-label="刷新对话"
            title="刷新对话"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      <div className="conversation-scroll" ref={scrollRef}>
        <div className="conversation-thread">
          {turns.length === 0 ? (
            <EmptyState
              icon={Sparkles}
              eyebrow="NEW CONVERSATION"
              title="从一个具体的问题开始"
              description="Agent 会持续使用这段对话的上下文。你描述得越具体，它越能给出可执行的回答。"
            />
          ) : (
            turns.map((turn) => (
              <TurnCard key={turn.task_id} turn={turn} busy={busy} onRetry={handleRetry} />
            ))
          )}
        </div>
      </div>

      <footer className="conversation-composer-area">
        {polling.timedOut ? (
          <div className="polling-notice">
            <Clock3 size={15} />
            <span>自动状态查询已停止（已达到最长等待时间），任务仍在服务端执行。</span>
            <button type="button" onClick={polling.resumePolling}>
              继续查询
            </button>
            <button type="button" onClick={() => void refreshHistory()}>
              立即刷新
            </button>
          </div>
        ) : null}
        {polling.pollingError && !polling.timedOut ? (
          <div className="polling-notice polling-notice-warn">
            <RotateCcw size={15} />
            <span>{polling.pollingError}</span>
          </div>
        ) : null}
        <Composer
          busy={busy}
          onSubmit={sendPrompt}
          onConflict={() => void refreshHistory()}
          autoFocus={turns.length === 0}
        />
        <p className="composer-disclaimer">Agent 可能产生不准确的内容，请在执行前核对关键结果。</p>
      </footer>
    </div>
  )
}
