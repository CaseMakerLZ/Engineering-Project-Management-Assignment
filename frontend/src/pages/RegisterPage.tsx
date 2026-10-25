import { useEffect, useState } from 'react'
import {
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  UserRound,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout } from '../components/AuthLayout'
import { useAuth } from '../auth/AuthProvider'
import { ApiError, describeError } from '../lib/errors'
import { USERNAME_PATTERN, validatePassword, validateUsername } from '../lib/validation'

interface RegisterErrors {
  username?: string
  password?: string
  confirm?: string
  form?: string
}

export function RegisterPage() {
  const navigate = useNavigate()
  const { register } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<RegisterErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    document.title = '注册 · AgentDesk'
  }, [])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (submitting) return
    const usernameError = validateUsername(username)
    const passwordError = validatePassword(password)
    const confirmError = password !== confirm ? '两次输入的密码不一致' : undefined
    if (usernameError || passwordError || confirmError) {
      setErrors({
        username: usernameError ?? undefined,
        password: passwordError ?? undefined,
        confirm: confirmError,
      })
      return
    }

    setSubmitting(true)
    setErrors({})
    try {
      await register({ username: username.trim(), password })
      navigate('/login', {
        replace: true,
        state: { registered: true, username: username.trim() },
      })
    } catch (error) {
      if (error instanceof ApiError && error.code === 20001) {
        setErrors({ username: '用户名已存在，请更换一个。' })
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

  const usernameRulePassed = USERNAME_PATTERN.test(username)
  const passwordRulePassed = password.length >= 8 && password.length <= 32
  const confirmRulePassed = Boolean(confirm) && confirm === password

  return (
    <AuthLayout
      eyebrow="CREATE ACCOUNT"
      title="创建你的账号"
      subtitle="建立独立工作区，保存项目、对话与任务记录。"
      footer={
        <span>
          已经有账号？ <Link to="/login">直接登录</Link>
        </span>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
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
              placeholder="4–20 位字母、数字或下划线"
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
              autoComplete="new-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
                setErrors((current) => ({ ...current, password: undefined, form: undefined }))
              }}
              placeholder="设置 8–32 位密码"
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

        <label className="field">
          <span className="field-label">确认密码</span>
          <span className="input-with-icon">
            <LockKeyhole size={17} />
            <input
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => {
                setConfirm(event.target.value)
                setErrors((current) => ({ ...current, confirm: undefined, form: undefined }))
              }}
              placeholder="再次输入密码"
              aria-invalid={Boolean(errors.confirm)}
            />
          </span>
          {errors.confirm ? <span className="field-error">{errors.confirm}</span> : null}
        </label>

        <div className="password-rules" aria-label="账号格式要求">
          <span className={usernameRulePassed ? 'rule-passed' : undefined}>
            <Check size={13} /> 用户名 4–20 位
          </span>
          <span className={passwordRulePassed ? 'rule-passed' : undefined}>
            <Check size={13} /> 密码 8–32 位
          </span>
          <span className={confirmRulePassed ? 'rule-passed' : undefined}>
            <Check size={13} /> 两次密码一致
          </span>
        </div>

        {errors.form ? (
          <div className="form-alert" role="alert">
            {errors.form}
          </div>
        ) : null}

        <button type="submit" className="btn btn-primary auth-submit" disabled={submitting}>
          {submitting ? <LoaderCircle size={18} className="spin" /> : null}
          {submitting ? '正在创建…' : '创建账号'}
          {!submitting ? <ArrowRight size={17} /> : null}
        </button>
      </form>
    </AuthLayout>
  )
}
