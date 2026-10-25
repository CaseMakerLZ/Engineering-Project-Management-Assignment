import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type Credentials,
} from '../api/auth'
import { AUTH_EXPIRED_EVENT } from '../api/client'
import { IS_CLOUD_MODE } from '../config'
import { ApiError, describeError } from '../lib/errors'
import { clearToken, getToken, setToken } from '../lib/token'
import type { User } from '../types/api'
import { useToast } from '../components/ToastProvider'

type AuthStatus = 'loading' | 'authenticated' | 'guest' | 'local' | 'error'

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  bootError: string | null
  login: (credentials: Credentials) => Promise<User>
  register: (credentials: Credentials) => Promise<User>
  logout: () => Promise<void>
  retrySession: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(IS_CLOUD_MODE ? 'loading' : 'local')
  const [user, setUser] = useState<User | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const { pushToast } = useToast()

  const hydrate = useCallback(async () => {
    if (!IS_CLOUD_MODE) {
      setStatus('local')
      return
    }
    if (!getToken()) {
      setUser(null)
      setStatus('guest')
      setBootError(null)
      return
    }

    setStatus('loading')
    setBootError(null)
    try {
      const currentUser = await getCurrentUser()
      setUser(currentUser)
      setStatus('authenticated')
    } catch (error) {
      if (error instanceof ApiError && error.code === 10002) {
        setUser(null)
        setStatus('guest')
      } else {
        setBootError(describeError(error))
        setStatus('error')
      }
    }
  }, [])

  useEffect(() => {
    void hydrate()
  }, [hydrate])

  useEffect(() => {
    if (!IS_CLOUD_MODE) return
    const handleExpired = () => {
      clearToken()
      setUser(null)
      setStatus('guest')
      pushToast('登录状态已失效，请重新登录。', 'error')
      const publicPath = location.pathname === '/login' || location.pathname === '/register'
      if (!publicPath) {
        navigate('/login', {
          replace: true,
          state: { from: `${location.pathname}${location.search}` },
        })
      }
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
  }, [location.pathname, location.search, navigate, pushToast])

  const login = useCallback(async (credentials: Credentials) => {
    const session = await loginRequest(credentials)
    setToken(session.token, session.expires_in)
    setUser(session.user)
    setStatus('authenticated')
    return session.user
  }, [])

  const register = useCallback(async (credentials: Credentials) => {
    return registerRequest(credentials)
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } catch {
      // 即使服务端注销失败，也必须清掉本地会话，避免继续使用旧 token。
    } finally {
      clearToken()
      setUser(null)
      setStatus('guest')
      navigate('/login', { replace: true })
    }
  }, [navigate])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      bootError,
      login,
      register,
      logout,
      retrySession: () => void hydrate(),
    }),
    [bootError, hydrate, login, logout, register, status, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}
