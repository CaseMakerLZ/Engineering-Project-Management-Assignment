import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  eyebrow?: string
  title: string
  description: string
  action?: React.ReactNode
  compact?: boolean
}

export function EmptyState({
  icon: Icon,
  eyebrow,
  title,
  description,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div className={`empty-state ${compact ? 'empty-state-compact' : ''}`}>
      <span className="empty-icon">
        <Icon size={compact ? 20 : 28} />
      </span>
      {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
      <h2>{title}</h2>
      <p>{description}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  )
}
