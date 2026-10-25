import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'

type ToastTone = 'success' | 'error' | 'info'

interface ToastItem {
  id: string
  message: string
  tone: ToastTone
}

interface ToastContextValue {
  pushToast: (message: string, tone?: ToastTone) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

function createToastId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef<number[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const pushToast = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = createToastId()
      setToasts((current) => [...current.slice(-3), { id, message, tone }])
      const timer = window.setTimeout(
        () => dismiss(id),
        tone === 'error' ? 6_000 : 4_000,
      )
      timers.current.push(timer)
    },
    [dismiss],
  )

  useEffect(() => {
    const activeTimers = timers.current
    return () => activeTimers.forEach((timer) => window.clearTimeout(timer))
  }, [])

  const value = useMemo(() => ({ pushToast }), [pushToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      {createPortal(
        <div className="toast-viewport" aria-live="polite" aria-atomic="false">
          {toasts.map((toast) => {
            const Icon =
              toast.tone === 'success'
                ? CheckCircle2
                : toast.tone === 'error'
                  ? AlertCircle
                  : Info
            return (
              <div key={toast.id} className={`toast toast-${toast.tone}`} role="status">
                <Icon size={18} aria-hidden="true" />
                <span>{toast.message}</span>
                <button
                  type="button"
                  className="toast-close"
                  onClick={() => dismiss(toast.id)}
                  aria-label="关闭提示"
                >
                  <X size={14} />
                </button>
              </div>
            )
          })}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used inside ToastProvider')
  }
  return context
}
