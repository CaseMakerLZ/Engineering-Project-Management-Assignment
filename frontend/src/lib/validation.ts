import { MAX_PROMPT_LENGTH } from '../config'

export const USERNAME_PATTERN = /^[A-Za-z0-9_]{4,20}$/

export function validateUsername(username: string): string | null {
  if (!username.trim()) return '请输入用户名'
  if (!USERNAME_PATTERN.test(username)) return '用户名需为 4–20 位字母、数字或下划线'
  return null
}

export function validatePassword(password: string): string | null {
  if (!password) return '请输入密码'
  if (password.length < 8 || password.length > 32) return '密码长度需为 8–32 位'
  return null
}

export function validatePrompt(prompt: string): string | null {
  const trimmed = prompt.trim()
  if (!trimmed) return '请输入你想让 Agent 处理的内容'
  if (trimmed.length > MAX_PROMPT_LENGTH) {
    return `输入内容不能超过 ${MAX_PROMPT_LENGTH.toLocaleString('zh-CN')} 个字符`
  }
  return null
}
