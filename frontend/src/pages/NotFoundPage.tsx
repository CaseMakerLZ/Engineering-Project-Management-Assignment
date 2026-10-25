import { Compass, Menu } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAppShell } from '../components/AppShell'

export function NotFoundPage() {
  const { openSidebar } = useAppShell()
  return (
    <div className="not-found-page">
      <button type="button" className="mobile-menu-button" onClick={openSidebar} aria-label="打开导航">
        <Menu size={19} />
      </button>
      <div className="workspace-error-card">
        <span className="workspace-error-icon">
          <Compass size={28} />
        </span>
        <span className="eyebrow">404 · NOT FOUND</span>
        <h1>这里没有可打开的页面</h1>
        <p>链接可能已经失效，或者地址输入有误。</p>
        <Link to="/projects" className="btn btn-primary">
          返回项目列表
        </Link>
      </div>
    </div>
  )
}
