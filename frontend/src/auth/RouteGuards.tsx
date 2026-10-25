import { AlertTriangle, RotateCcw, Sparkles } from 'lucide-react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { IS_CLOUD_MODE } from '../config'
import { useAuth } from './AuthProvider'

export function SessionSplash({ label = '正在恢复会话…' }: { label?: string }) {
  return (
    <div className="session-screen">
      <div className="session-brand">
        <span className="brand-mark brand-mark-lg">
          <Sparkles size={24} />
        </span>
        <div>
          <strong>AgentDesk</strong>
          <span>{label}</span>
        </div>
      </div>
      <span className="session-loader" aria-hidden="true" />
    </div>
  )
}

export function RequireAuth() {
  const { status, bootError, retrySession } = useAuth()
  const location = useLocation()

  if (!IS_CLOUD_MODE) return <Outlet />
  if (status === 'loading') return <SessionSplash />
  if (status === 'error') {
    return (
      <div className="session-screen">
        <div className="session-error-card">
          <span className="session-error-icon">
            <AlertTriangle size={22} />
          </span>
          <h1>暂时无法恢复会话</h1>
          <p>{bootError}</p>
          <button type="button" className="btn btn-primary" onClick={retrySession}>
            <RotateCcw size={16} />
            重新连接
          </button>
        </div>
      </div>
    )
  }
  if (status === 'guest') {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }
  return <Outlet />
}

export function GuestOnly({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()

  if (!IS_CLOUD_MODE) return <Navigate to="/projects" replace />
  if (status === 'loading') return <SessionSplash label="正在检查登录状态…" />
  if (status === 'authenticated') return <Navigate to="/projects" replace />
  return <>{children}</>
}
