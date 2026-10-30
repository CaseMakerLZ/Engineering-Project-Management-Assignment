export function formatRelativeTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000)
  const absoluteSeconds = Math.abs(diffSeconds)

  if (absoluteSeconds < 60) return '刚刚'
  if (absoluteSeconds < 3_600) {
    const minutes = Math.round(absoluteSeconds / 60)
    return diffSeconds < 0 ? `${minutes} 分钟前` : `${minutes} 分钟后`
  }
  if (absoluteSeconds < 86_400) {
    const hours = Math.round(absoluteSeconds / 3_600)
    return diffSeconds < 0 ? `${hours} 小时前` : `${hours} 小时后`
  }
  if (absoluteSeconds < 604_800) {
    const days = Math.round(absoluteSeconds / 86_400)
    return diffSeconds < 0 ? `${days} 天前` : `${days} 天后`
  }
  return formatShortDate(value)
}

export function formatShortDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const now = new Date()
  if (date.getFullYear() === now.getFullYear()) {
    return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(date)
  }
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date)
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function getInitials(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return '?'
  const firstSegment = trimmed.split(/\s+/)[0]
  return firstSegment.slice(0, 2).toUpperCase()
}

export function shortId(value: string): string {
  if (value.length <= 12) return value
  return `${value.slice(0, 6)}…${value.slice(-4)}`
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1_024) return `${bytes} B`
  if (bytes < 1_024 * 1_024) return `${(bytes / 1_024).toFixed(1)} KB`
  return `${(bytes / (1_024 * 1_024)).toFixed(1)} MB`
}
