import { Ban, Check, CircleDashed, LoaderCircle, TriangleAlert } from 'lucide-react'
import type { TaskStatus } from '../types/api'

interface StatusMeta {
  label: string
  tone: 'active' | 'success' | 'danger' | 'muted'
}

const STATUS_META: Record<TaskStatus, StatusMeta> = {
  CREATED: { label: '等待执行', tone: 'active' },
  RUNNING: { label: '执行中', tone: 'active' },
  COMPLETED: { label: '已完成', tone: 'success' },
  FAILED: { label: '执行失败', tone: 'danger' },
  CANCELLED: { label: '已取消', tone: 'muted' },
}

export function isActiveStatus(status: TaskStatus): boolean {
  return status === 'CREATED' || status === 'RUNNING'
}

export function StatusPill({ status }: { status: TaskStatus }) {
  const meta = STATUS_META[status] ?? { label: status, tone: 'muted' as const }
  const Icon =
    status === 'COMPLETED'
      ? Check
      : status === 'FAILED'
        ? TriangleAlert
        : status === 'CANCELLED'
          ? Ban
          : status === 'RUNNING'
            ? LoaderCircle
            : CircleDashed

  return (
    <span className={`status-pill status-${meta.tone}`}>
      <Icon size={12} className={status === 'RUNNING' ? 'spin' : undefined} />
      {meta.label}
    </span>
  )
}
