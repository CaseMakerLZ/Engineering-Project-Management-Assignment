import { useEffect, useState } from 'react'
import { LoaderCircle, MessageSquarePlus } from 'lucide-react'
import { createConversation } from '../api/conversations'
import { describeError } from '../lib/errors'
import type { Conversation } from '../types/api'
import { Modal } from './Modal'

interface CreateConversationDialogProps {
  open: boolean
  projectId: string
  onClose: () => void
  onCreated: (conversation: Conversation) => void
}

export function CreateConversationDialog({
  open,
  projectId,
  onClose,
  onCreated,
}: CreateConversationDialogProps) {
  const [title, setTitle] = useState('新对话')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setTitle('新对话')
    setError(null)
    setSubmitting(false)
  }, [open])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (submitting) return
    const trimmed = title.trim()
    if (!trimmed) {
      setError('请输入对话标题')
      return
    }
    if (trimmed.length > 50) {
      setError('对话标题不能超过 50 个字符')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const conversation = await createConversation(projectId, { title: trimmed })
      onCreated(conversation)
      onClose()
    } catch (error) {
      setError(describeError(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建对话"
      description="每段对话拥有独立上下文，适合拆分不同任务。"
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            form="create-conversation-form"
            disabled={submitting}
          >
            {submitting ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <MessageSquarePlus size={16} />
            )}
            {submitting ? '正在创建…' : '开始对话'}
          </button>
        </>
      }
    >
      <form id="create-conversation-form" className="form-stack" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">
            对话标题 <em>必填</em>
          </span>
          <input
            autoFocus
            value={title}
            onChange={(event) => {
              setTitle(event.target.value)
              setError(null)
            }}
            onFocus={(event) => event.currentTarget.select()}
            placeholder="例如：分析项目结构"
            maxLength={50}
            aria-invalid={Boolean(error)}
          />
          <span className="field-help">1–50 个字符，之后可以在对话列表中识别它。</span>
          {error ? <span className="field-error">{error}</span> : null}
        </label>
      </form>
    </Modal>
  )
}
