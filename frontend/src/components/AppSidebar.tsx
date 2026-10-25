import { ChevronRight, FolderKanban, LogOut, Plus, RefreshCw, X } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'
import { IS_CLOUD_MODE } from '../config'
import type { Project, User } from '../types/api'
import { Brand } from './Brand'
import { ProjectGlyph } from './ProjectGlyph'

interface AppSidebarProps {
  open: boolean
  projects: Project[]
  loading: boolean
  error: string | null
  activeProjectId: string | null
  user: User | null
  onClose: () => void
  onCreateProject: () => void
  onRefreshProjects: () => void
  onLogout: () => void
}

export function AppSidebar({
  open,
  projects,
  loading,
  error,
  activeProjectId,
  user,
  onClose,
  onCreateProject,
  onRefreshProjects,
  onLogout,
}: AppSidebarProps) {
  const username = IS_CLOUD_MODE ? (user?.username ?? '未登录') : '本地工作区'
  const avatarLetter = username.slice(0, 1).toUpperCase()

  return (
    <aside id="app-sidebar" className={`app-sidebar ${open ? 'is-open' : ''}`}>
      <div className="sidebar-top">
        <Brand />
        <button type="button" className="sidebar-close icon-btn" onClick={onClose} aria-label="关闭菜单">
          <X size={18} />
        </button>
      </div>

      <button type="button" className="sidebar-create" onClick={onCreateProject}>
        <span>
          <Plus size={17} />
        </span>
        新建项目
      </button>

      <nav className="sidebar-nav" aria-label="主导航">
        <span className="sidebar-section-label">工作区</span>
        <NavLink
          to="/projects"
          end
          className={({ isActive }) => `sidebar-nav-link ${isActive ? 'is-active' : ''}`}
          onClick={onClose}
        >
          <FolderKanban size={17} />
          全部项目
          <span className="nav-count">{projects.length}</span>
        </NavLink>
      </nav>

      <div className="sidebar-projects">
        <div className="sidebar-section-heading">
          <span className="sidebar-section-label">最近项目</span>
          <button
            type="button"
            className="sidebar-refresh"
            onClick={onRefreshProjects}
            aria-label="刷新项目列表"
            title="刷新项目列表"
          >
            <RefreshCw size={13} className={loading ? 'spin' : undefined} />
          </button>
        </div>

        {loading && projects.length === 0 ? (
          <div className="sidebar-skeleton" aria-label="正在加载项目">
            <i />
            <i />
            <i />
          </div>
        ) : null}

        {error ? (
          <div className="sidebar-inline-error">
            <span>{error}</span>
            <button type="button" onClick={onRefreshProjects}>
              重试
            </button>
          </div>
        ) : null}

        {!loading && !error && projects.length === 0 ? (
          <p className="sidebar-empty">还没有项目，创建第一个开始。</p>
        ) : null}

        <div className="sidebar-project-list">
          {projects.map((project) => (
            <Link
              key={project.project_id}
              to={`/projects/${project.project_id}`}
              className={`sidebar-project-item ${
                activeProjectId === project.project_id ? 'is-active' : ''
              }`}
              onClick={onClose}
            >
              <ProjectGlyph
                projectId={project.project_id}
                name={project.name}
                size="small"
              />
              <span className="sidebar-project-copy">
                <strong>{project.name}</strong>
                <small>{project.description || '暂无项目描述'}</small>
              </span>
              <ChevronRight size={14} className="sidebar-project-arrow" />
            </Link>
          ))}
        </div>
      </div>

      <div className="sidebar-user">
        <span className="user-avatar-lg" aria-hidden="true">
          {avatarLetter}
        </span>
        <div className="sidebar-user-copy">
          <strong>{username}</strong>
          <span className={`mode-dot ${IS_CLOUD_MODE ? 'mode-cloud' : 'mode-local'}`}>
            {IS_CLOUD_MODE ? '云端模式' : '本地模式'}
          </span>
        </div>
        {IS_CLOUD_MODE ? (
          <button
            type="button"
            className="icon-btn sidebar-logout"
            onClick={onLogout}
            aria-label="退出登录"
            title="退出登录"
          >
            <LogOut size={17} />
          </button>
        ) : null}
      </div>
    </aside>
  )
}
