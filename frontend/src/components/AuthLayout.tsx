import { Braces, FolderKanban, ShieldCheck, Sparkles } from 'lucide-react'
import { BrandMark } from './Brand'

interface AuthLayoutProps {
  eyebrow: string
  title: string
  subtitle: string
  children: React.ReactNode
  footer: React.ReactNode
}

const FEATURES = [
  { icon: FolderKanban, text: '项目与多段对话集中管理' },
  { icon: Braces, text: 'Markdown、表格与数学公式完整渲染' },
  { icon: ShieldCheck, text: '云端模式的会话令牌自动续带' },
]

export function AuthLayout({ eyebrow, title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <div className="auth-page">
      <aside className="auth-visual">
        <div className="auth-visual-top">
          <BrandMark size="large" />
          <span>AgentDesk</span>
        </div>

        <div className="auth-visual-copy">
          <span className="auth-kicker">
            <Sparkles size={14} />
            AI PROJECT WORKSPACE
          </span>
          <h1>
            让每一个项目，
            <br />
            都有自己的 <em>Agent</em>。
          </h1>
          <p>从一句任务开始，在持续对话中理解项目、生成方案并沉淀结果。</p>
          <ul className="auth-feature-list">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text}>
                <span>
                  <Icon size={15} />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <div className="auth-orbit" aria-hidden="true">
          <span className="orbit-ring orbit-ring-one" />
          <span className="orbit-ring orbit-ring-two" />
          <span className="orbit-core">
            <Sparkles size={30} />
          </span>
          <i className="orbit-dot orbit-dot-one" />
          <i className="orbit-dot orbit-dot-two" />
          <i className="orbit-dot orbit-dot-three" />
        </div>
        <span className="auth-visual-foot">Build with clarity · Think with agents</span>
      </aside>

      <main className="auth-main">
        <div className="auth-mobile-brand">
          <BrandMark />
          <strong>AgentDesk</strong>
        </div>
        <div className="auth-form-shell">
          <div className="auth-heading">
            <span className="eyebrow">{eyebrow}</span>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          {children}
          <div className="auth-footer">{footer}</div>
        </div>
      </main>
    </div>
  )
}
