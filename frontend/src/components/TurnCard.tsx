import { useState } from 'react'
import { AlertTriangle, Check, Copy, RotateCcw, Sparkles, UserRound } from 'lucide-react'
import { formatRelativeTime } from '../lib/format'
import type { Turn } from '../types/api'
import { MarkdownContent } from './MarkdownContent'
import { isActiveStatus, StatusPill } from './StatusPill'

interface TurnCardProps {
  turn: Turn
  busy: boolean
  onRetry: (prompt: string) => void
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

export function TurnCard({ turn, busy, onRetry }: TurnCardProps) {
  const [copied, setCopied] = useState(false)
  const active = isActiveStatus(turn.status)

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
                      ? 'Agent 正在准备执行环境，稍后自动更新结果。'
                      : '正在阅读上下文并生成回答，请保持当前页面打开。'}
                  </p>
                </div>
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
