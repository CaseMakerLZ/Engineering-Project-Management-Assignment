import { useState } from 'react'
import {
  AlertTriangle,
  Check,
  CircleCheck,
  CircleX,
  Copy,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Sparkles,
  UserRound,
  Wrench,
} from 'lucide-react'
import { formatRelativeTime } from '../lib/format'
import type { Turn } from '../types/api'
import type { TurnStreamState, TurnToolState } from '../types/turnEvents'
import { MarkdownContent } from './MarkdownContent'
import { isActiveStatus, StatusPill } from './StatusPill'

interface TurnCardProps {
  turn: Turn
  busy: boolean
  onRetry: (prompt: string) => void
  streamState?: TurnStreamState
  onReconnect?: () => void
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  textarea.remove()
}

function toolLabel(tool: Pick<TurnToolState, 'tool_name'>): string {
  const labels: Record<string, string> = {
    read_text_file: '读取文件',
    write_text_file: '写入文件',
  }
  return labels[tool.tool_name] ?? tool.tool_name
}

function connectionLabel(state: TurnStreamState): string {
  if (state.connectionStatus === 'connected') return '实时连接已建立'
  if (state.connectionStatus === 'reconnecting') {
    return `正在重新连接（第 ${state.reconnectAttempt} 次）`
  }
  if (state.connectionStatus === 'connecting') return '正在连接实时输出'
  return '实时连接已断开'
}

export function TurnCard({ turn, busy, onRetry, streamState, onReconnect }: TurnCardProps) {
  const [copied, setCopied] = useState(false)
  const active = isActiveStatus(turn.status)
  const processMessages = streamState?.messages ?? []
  const tools = streamState?.tools ?? []
  const activeTool = streamState?.activeTool

  const handleCopy = async () => {
    if (!turn.result) return
    try {
      await copyText(turn.result)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1_800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <article className="turn" aria-label="一轮对话">
      <section className="message-user">
        <div className="message-avatar user-avatar" aria-hidden="true">
          <UserRound size={16} />
        </div>
        <div className="message-stack">
          <div className="message-meta">
            <strong>你</strong>
            <time dateTime={turn.created_at}>{formatRelativeTime(turn.created_at)}</time>
          </div>
          <div className="user-bubble">{turn.prompt}</div>
        </div>
      </section>

      <section className={`message-agent ${active ? 'message-agent-active' : ''}`}>
        <div className="message-avatar agent-avatar" aria-hidden="true">
          <Sparkles size={16} />
        </div>
        <div className="message-stack">
          <div className="message-meta">
            <strong>Agent</strong>
            <StatusPill status={turn.status} />
            {streamState ? (
              <span
                className={`stream-connection stream-connection-${
                  active ? streamState.connectionStatus : 'complete'
                }`}
              >
                {!active ? (
                  <CircleCheck size={11} />
                ) : streamState.connectionStatus === 'connected' ? (
                  <i />
                ) : streamState.connectionStatus === 'disconnected' ? (
                  <CircleX size={11} />
                ) : (
                  <LoaderCircle size={11} className="spin" />
                )}
                {active ? connectionLabel(streamState) : '实时输出已结束'}
              </span>
            ) : null}
          </div>

          <div className={`agent-surface agent-surface-${turn.status.toLowerCase()}`}>
            {active ? (
              <div className="agent-progress">
                <span className="thinking-orb" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <div>
                  <strong>{turn.status === 'CREATED' ? '任务已受理' : '正在处理你的请求'}</strong>
                  <p>
                    {turn.status === 'CREATED'
                      ? 'Agent 正在准备执行环境，实时输出连接后会自动显示。'
                      : '任务在服务器执行，离开页面后仍可回来查看。'}
                  </p>
                </div>
              </div>
            ) : null}

            {processMessages.length > 0 ? (
              <div className="agent-process-output" role="log" aria-live="polite">
                <div className="agent-toolbar">
                  <span>过程</span>
                </div>
                {processMessages.map((message) => (
                  <MarkdownContent key={message.message_id} content={message.text} />
                ))}
              </div>
            ) : null}

            {tools.length > 0 ? (
              <div className="agent-tool-list" aria-label="工具执行状态">
                {tools.map((tool) => {
                  const running = activeTool?.call_id === tool.call_id
                  return (
                    <div
                      key={tool.call_id}
                      className={`agent-tool-state ${
                        running
                          ? 'is-running'
                          : tool.success === false
                            ? 'is-failed'
                            : tool.success
                              ? 'is-success'
                              : ''
                      }`}
                    >
                      <Wrench size={13} />
                      <span>{toolLabel(tool)}</span>
                      {running ? (
                        <>
                          <LoaderCircle size={12} className="spin" />
                          <small>执行中</small>
                        </>
                      ) : tool.success === false ? (
                        <>
                          <CircleX size={12} />
                          <small>{tool.error || '工具执行失败'}</small>
                        </>
                      ) : tool.success ? (
                        <>
                          <CircleCheck size={12} />
                          <small>完成</small>
                        </>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            ) : null}

            {streamState?.channelError ? (
              <div className="stream-warning" role="status">
                <AlertTriangle size={14} />
                <span>{streamState.channelError}</span>
                {streamState.connectionStatus === 'disconnected' && active && onReconnect ? (
                  <button type="button" onClick={onReconnect}>
                    <RefreshCw size={12} />
                    手动重连
                  </button>
                ) : null}
              </div>
            ) : null}

            {turn.status === 'COMPLETED' ? (
              <>
                <div className="agent-toolbar">
                  <span>回答</span>
                  <button type="button" className="ghost-action" onClick={handleCopy}>
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                    {copied ? '已复制' : '复制'}
                  </button>
                </div>
                {turn.result ? (
                  <MarkdownContent content={turn.result} />
                ) : (
                  <p className="muted-copy">任务已完成，但 Agent 没有返回文本内容。</p>
                )}
              </>
            ) : null}

            {turn.status === 'FAILED' ? (
              <div className="agent-error">
                <div className="agent-error-heading">
                  <AlertTriangle size={17} />
                  <strong>这次任务没有完成</strong>
                </div>
                <p>{turn.error || 'Agent 未返回具体错误信息。'}</p>
                <button
                  type="button"
                  className="btn btn-secondary btn-small"
                  onClick={() => onRetry(turn.prompt)}
                  disabled={busy}
                >
                  <RotateCcw size={14} />
                  重新提问
                </button>
              </div>
            ) : null}

            {turn.status === 'CANCELLED' ? (
              <div className="agent-cancelled">
                <strong>任务已取消</strong>
                <p>你可以修改问题后重新提交。</p>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </article>
  )
}
