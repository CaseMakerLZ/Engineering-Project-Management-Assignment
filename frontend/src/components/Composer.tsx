import { useEffect, useRef, useState } from 'react'
import { ArrowUp, LoaderCircle, RotateCcw, TriangleAlert } from 'lucide-react'
import { MAX_PROMPT_LENGTH } from '../config'
import { ApiError, describeError } from '../lib/errors'
import { validatePrompt } from '../lib/validation'

interface ComposerProps {
  busy: boolean
  busyLabel?: string
  onSubmit: (prompt: string) => Promise<void>
  onConflict?: () => void
  autoFocus?: boolean
}

interface SubmitError {
  message: string
  retryable: boolean
}

export function Composer({
  busy,
  busyLabel = 'Agent 正在处理当前任务，完成后即可继续提问。',
  onSubmit,
  onConflict,
  autoFocus = false,
}: ComposerProps) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<SubmitError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const disabled = busy || submitting

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`
  }, [value])

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus()
  }, [autoFocus])

  const submit = async () => {
    if (disabled) return
    const validationError = validatePrompt(value)
    if (validationError) {
      setError({ message: validationError, retryable: false })
      textareaRef.current?.focus()
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await onSubmit(value.trim())
      setValue('')
    } catch (submitError) {
      const code = submitError instanceof ApiError ? submitError.code : undefined
      if (code === 30005) onConflict?.()
      setError({
        message: describeError(submitError),
        retryable: code === 40001 || code === 40002 || code === 50000 || code === 90001,
      })
      textareaRef.current?.focus()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={`composer ${busy ? 'composer-busy' : ''}`}>
      {busy ? (
        <div className="composer-busy-banner">
          <LoaderCircle size={15} className="spin" />
          <span>{busyLabel}</span>
        </div>
      ) : null}

      <div className="composer-input-wrap">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => {
            setValue(event.target.value)
            if (error) setError(null)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              void submit()
            }
          }}
          placeholder={busy ? '当前任务执行中，请稍候…' : '描述你想让 Agent 完成的任务…'}
          aria-label="输入任务内容"
          maxLength={MAX_PROMPT_LENGTH}
          disabled={disabled}
          rows={1}
        />
        <button
          type="button"
          className="send-button"
          onClick={() => void submit()}
          disabled={disabled || !value.trim()}
          aria-label={submitting ? '正在发送' : '发送'}
        >
          {submitting ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}
        </button>
      </div>

      {error ? (
        <div className="composer-error" role="alert">
          <TriangleAlert size={14} />
          <span>{error.message}</span>
          {error.retryable ? (
            <button type="button" onClick={() => void submit()} disabled={disabled}>
              <RotateCcw size={13} />
              重试
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="composer-footer">
        <span>Enter 发送 · Shift + Enter 换行</span>
        <span className={value.length > MAX_PROMPT_LENGTH * 0.9 ? 'char-warning' : undefined}>
          {value.length.toLocaleString('zh-CN')} / {MAX_PROMPT_LENGTH.toLocaleString('zh-CN')}
        </span>
      </div>
    </div>
  )
}
