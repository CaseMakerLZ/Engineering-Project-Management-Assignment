import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, UserRound } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, describeError } from '../lib/errors'
import { validatePassword, validateUsername } from '../lib/validation'
import { AuthLayout } from '../components/AuthLayout'
import { useAuth } from '../auth/AuthProvider'
import { useToast } from '../components/ToastProvider'

interface LoginLocationState {
  from?: string
  username?: string
  registered?: boolean
}

export function LoginPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { login } = useAuth()
  const { pushToast } = useToast()
  const state = (location.state ?? null) as LoginLocationState | null
  const [username, setUsername] = useState(state?.username ?? '')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<{ username?: string; password?: string; form?: string }>({})
  const [submitting, setSubmitting] = useState(false)
  const registered = Boolean(state?.registered)
  const registerNoticeShown = useRef(false)

  useEffect(() => {
    document.title = '登录 · AgentDesk'
  }, [])

  useEffect(() => {
    if (registered && !registerNoticeShown.current) {
      registerNoticeShown.current = true
      pushToast('注册成功，请登录。', 'success')
    }
  }, [pushToast, registered])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (submitting) return
    const usernameError = validateUsername(username)
    const passwordError = validatePassword(password)
    if (usernameError || passwordError) {
      setErrors({ username: usernameError ?? undefined, password: passwordError ?? undefined })
      return
    }

    setSubmitting(true)
    setErrors({})
    try {
      await login({ username: username.trim(), password })
      const target =
        state?.from && state.from.startsWith('/') && !state.from.startsWith('//')
          ? state.from
          : '/projects'
      navigate(target, { replace: true })
    } catch (error) {
      if (error instanceof ApiError && error.code === 20002) {
        setErrors({ form: '用户名或密码错误，请检查后重试。' })
      } else if (error instanceof ApiError && error.code === 10001) {
        if (error.message.includes('用户名')) setErrors({ username: error.message })
        else if (error.message.includes('密码')) setErrors({ password: error.message })
        else setErrors({ form: describeError(error) })
      } else {
        setErrors({ form: describeError(error) })
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      eyebrow="WELCOME BACK"
      title="登录你的工作台"
      subtitle="继续项目、对话与正在执行的 Agent 任务。"
      footer={
        <span>
          还没有账号？ <Link to="/register">创建账号</Link>
        </span>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {registered ? <div className="form-success">账号创建成功，请使用新账号登录。</div> : null}

        <label className="field">
          <span className="field-label">用户名</span>
          <span className="input-with-icon">
            <UserRound size={17} />
            <input
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(event) => {
                setUsername(event.target.value)
                setErrors((current) => ({ ...current, username: undefined, form: undefined }))
              }}
              placeholder="输入用户名"
              aria-invalid={Boolean(errors.username)}
            />
          </span>
          {errors.username ? <span className="field-error">{errors.username}</span> : null}
        </label>

        <label className="field">
          <span className="field-label">密码</span>
          <span className="input-with-icon input-with-action">
            <LockKeyhole size={17} />
            <input
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
                setErrors((current) => ({ ...current, password: undefined, form: undefined }))
              }}
              placeholder="输入密码"
              aria-invalid={Boolean(errors.password)}
            />
            <button
              type="button"
              className="input-action"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={showPassword ? '隐藏密码' : '显示密码'}
            >
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </span>
          {errors.password ? <span className="field-error">{errors.password}</span> : null}
        </label>

        {errors.form ? (
          <div className="form-alert" role="alert">
            {errors.form}
          </div>
        ) : null}

        <button type="submit" className="btn btn-primary auth-submit" disabled={submitting}>
          {submitting ? <LoaderCircle size={18} className="spin" /> : null}
          {submitting ? '正在登录…' : '登录'}
          {!submitting ? <ArrowRight size={17} /> : null}
        </button>
      </form>
    </AuthLayout>
  )
}
