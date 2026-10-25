import { Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

export function BrandMark({ size = 'default' }: { size?: 'default' | 'large' }) {
  return (
    <span className={`brand-mark ${size === 'large' ? 'brand-mark-lg' : ''}`} aria-hidden="true">
      <Sparkles />
      <i />
    </span>
  )
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/projects" className="brand" aria-label="AgentDesk 首页">
      <BrandMark />
      {!compact ? (
        <span className="brand-copy">
          <strong>AgentDesk</strong>
          <small>AI 项目工作台</small>
        </span>
      ) : null}
    </Link>
  )
}
