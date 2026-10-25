export type AppMode = 'local' | 'cloud'

const configuredMode = (import.meta.env.VITE_APP_MODE ?? 'local').trim().toLowerCase()

export const APP_MODE: AppMode = configuredMode === 'cloud' ? 'cloud' : 'local'
export const IS_CLOUD_MODE = APP_MODE === 'cloud'

const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').trim()
export const API_BASE_URL = configuredBaseUrl.replace(/\/+$/, '')

export const REQUEST_TIMEOUT_MS = 30_000
export const POLL_INITIAL_DELAY_MS = 1_500
export const POLL_MAX_DELAY_MS = 5_000
export const POLL_MAX_WAIT_MS = 180_000
export const MAX_PROMPT_LENGTH = 20_000

export const TERMINAL_TASK_STATUSES = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])
