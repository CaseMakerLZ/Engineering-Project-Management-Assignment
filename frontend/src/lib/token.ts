const TOKEN_STORAGE_KEY = 'agentdesk.auth.token'
const EXPIRES_AT_STORAGE_KEY = 'agentdesk.auth.expires_at'

let memoryToken: string | null = null
let initialized = false

function readPersistedToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function getToken(): string | null {
  if (!initialized) {
    memoryToken = readPersistedToken()
    initialized = true
  }
  try {
    const rawExpiresAt = window.localStorage.getItem(EXPIRES_AT_STORAGE_KEY)
    if (memoryToken && rawExpiresAt) {
      const expiresAt = Number(rawExpiresAt)
      if (Number.isFinite(expiresAt) && expiresAt <= Date.now()) {
        clearToken()
        return null
      }
    }
  } catch {
    // 本地存储不可用时仍允许使用内存 token。
  }
  return memoryToken
}

export function setToken(token: string, expiresInSeconds?: number): void {
  memoryToken = token
  initialized = true
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
    if (expiresInSeconds && expiresInSeconds > 0) {
      const expiresAt = Date.now() + expiresInSeconds * 1_000
      window.localStorage.setItem(EXPIRES_AT_STORAGE_KEY, String(expiresAt))
    } else {
      window.localStorage.removeItem(EXPIRES_AT_STORAGE_KEY)
    }
  } catch {
    // 内存中的 token 仍可保证当前标签页正常工作。
  }
}

export function clearToken(): void {
  memoryToken = null
  initialized = true
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY)
    window.localStorage.removeItem(EXPIRES_AT_STORAGE_KEY)
  } catch {
    // 忽略存储不可用。
  }
}
