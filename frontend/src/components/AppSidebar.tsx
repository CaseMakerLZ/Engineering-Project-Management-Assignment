import { useEffect, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Folder,
  FolderKanban,
  FolderOpen,
  LogOut,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  UserRound,
  X,
} from 'lucide-react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { IS_CLOUD_MODE } from '../config'
import { useAppShell } from './AppShell'

interface AppSidebarProps {
  open: boolean
  collapsed: boolean
  onClose: () => void
  onLogout: () => void
}

function routeIds(pathname: string): {
  projectId: string | null
  conversationId: string | null
} {
  const match = pathname.match(/^\/projects\/([^/]+)(?:\/conversations\/([^/]+))?/)
  if (!match) return { projectId: null, conversationId: null }
  let projectId = match[1]
  let conversationId = match[2] ?? null
  try {
    projectId = decodeURIComponent(projectId)
    if (conversationId) conversationId = decodeURIComponent(conversationId)
  } catch {
    // Keep raw route segments if malformed escaping reaches the router.
  }
  return { projectId, conversationId }
}

export function AppSidebar({ open, collapsed, onClose, onLogout }: AppSidebarProps) {
  const {
    projects,
    projectsLoading,
    projectsError,
    conversationsByProject,
    refreshProjects,
    loadConversations,
    openCreateProject,
    openNewConversation,
    toggleSidebar,
  } = useAppShell()
  const { user } = useAuth()
  const location = useLocation()
  const { projectId: activeProjectId, conversationId: activeConversationId } = routeIds(
    location.pathname,
  )
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    () => new Set(activeProjectId ? [activeProjectId] : []),
  )
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 920px)').matches,
  )
  const username = IS_CLOUD_MODE ? (user?.username ?? '未登录') : '本地工作区'

  useEffect(() => {
    const media = window.matchMedia('(max-width: 920px)')
    const update = () => setIsMobile(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (!activeProjectId) return
    setExpandedProjects((current) => {
      if (current.has(activeProjectId)) return current
      const next = new Set(current)
      next.add(activeProjectId)
      return next
    })
    void loadConversations(activeProjectId)
  }, [activeProjectId, loadConversations])

  const toggleProject = (projectId: string) => {
    const opening = !expandedProjects.has(projectId)
    setExpandedProjects((current) => {
      const next = new Set(current)
      if (opening) next.add(projectId)
      else next.delete(projectId)
      return next
    })
    if (opening) void loadConversations(projectId)
  }

  if (collapsed && !isMobile) {
    return (
      <aside className="app-sidebar app-sidebar-rail" aria-label="导航栏">
        <button
          type="button"
          className="sidebar-rail-button"
          onClick={toggleSidebar}
          aria-label="展开导航"
          title="展开导航"
        >
          <PanelLeftOpen size={18} />
        </button>
        <button
          type="button"
          className="sidebar-rail-button"
          onClick={openCreateProject}
          aria-label="新建项目"
          title="新建项目"
        >
          <Plus size={18} />
        </button>
        <Link
          to="/projects"
          className={`sidebar-rail-button ${location.pathname === '/projects' ? 'is-active' : ''}`}
          aria-label="所有项目"
          title="所有项目"
        >
          <FolderKanban size={18} />
        </Link>
        <div className="sidebar-rail-projects" aria-label="项目快捷入口">
          {projects.slice(0, 8).map((project) => (
            <Link
              key={project.project_id}
              to={`/projects/${project.project_id}`}
              className={`sidebar-rail-button ${
                activeProjectId === project.project_id ? 'is-active' : ''
              }`}
              aria-label={project.name}
              title={project.name}
            >
              <Folder size={17} />
            </Link>
          ))}
        </div>
        <div className="sidebar-rail-bottom">
          <span className="sidebar-rail-user" title={username}>
            <UserRound size={17} />
          </span>
          {IS_CLOUD_MODE ? (
            <button
              type="button"
              className="sidebar-rail-button"
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

  return (
    <aside
      id="app-sidebar"
      className={`app-sidebar ${open ? 'is-open' : ''}`}
      aria-label="项目与对话导航"
    >
      <div className="sidebar-top">
        <span className="sidebar-title">项目</span>
        <div className="sidebar-top-actions">
          <button
            type="button"
            className="icon-btn sidebar-collapse"
            onClick={toggleSidebar}
            aria-label="收起导航"
            title="收起导航"
          >
            <PanelLeftClose size={17} />
          </button>
          <button
            type="button"
            className="icon-btn sidebar-close"
            onClick={onClose}
            aria-label="关闭导航"
          >
            <X size={17} />
          </button>
        </div>
      </div>

      <button type="button" className="sidebar-create" onClick={openCreateProject}>
        <Plus size={16} />
        新建项目
      </button>

      <nav className="sidebar-nav" aria-label="项目导航">
        <NavLink
          to="/projects"
          end
          className={({ isActive }) => `sidebar-nav-link ${isActive ? 'is-active' : ''}`}
          onClick={onClose}
        >
          <FolderKanban size={16} />
          所有项目
        </NavLink>
      </nav>

      <div className="sidebar-section-heading">
        <span>项目与对话</span>
        <button
          type="button"
          className="sidebar-refresh"
          onClick={refreshProjects}
          aria-label="刷新项目列表"
          title="刷新项目列表"
        >
          <RefreshCw size={13} className={projectsLoading ? 'spin' : undefined} />
        </button>
      </div>

      <div className="sidebar-projects">
        {projectsLoading && projects.length === 0 ? (
          <div className="sidebar-skeleton" aria-label="正在加载项目">
            <i />
            <i />
            <i />
          </div>
        ) : null}

        {projectsError ? (
          <div className="sidebar-inline-error" role="alert">
            <span>{projectsError}</span>
            <button type="button" onClick={refreshProjects}>
              重试
            </button>
          </div>
        ) : null}

        {!projectsLoading && !projectsError && projects.length === 0 ? (
          <p className="sidebar-empty">还没有项目。使用上方按钮创建第一个项目。</p>
        ) : null}

        <div className="sidebar-project-list">
          {projects.map((project) => {
            const expanded = expandedProjects.has(project.project_id)
            const bucket = conversationsByProject[project.project_id]
            const conversations = bucket?.items ?? []
            return (
              <div className="sidebar-project-branch" key={project.project_id}>
                <div
                  className={`sidebar-project-row ${
                    activeProjectId === project.project_id ? 'is-active' : ''
                  }`}
                >
                  <button
                    type="button"
                    className="sidebar-project-toggle"
                    onClick={() => toggleProject(project.project_id)}
                    aria-label={`${expanded ? '收起' : '展开'} ${project.name}`}
                    aria-expanded={expanded}
                    title={expanded ? '收起对话' : '展开对话'}
                  >
                    {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <Link
                    to={`/projects/${project.project_id}`}
                    className="sidebar-project-link"
                    title={project.name}
                    onClick={onClose}
                  >
                    {activeProjectId === project.project_id ? (
                      <FolderOpen size={16} />
                    ) : (
                      <Folder size={16} />
                    )}
                    <span>{project.name}</span>
                  </Link>
                  <button
                    type="button"
                    className="sidebar-project-add"
                    onClick={() => openNewConversation(project.project_id)}
                    aria-label={`在 ${project.name} 中新建对话`}
                    title="新建对话"
                  >
                    <Plus size={14} />
                  </button>
                </div>

                {expanded ? (
                  <div className="sidebar-conversations">
                    {bucket?.loading ? (
                      <div className="sidebar-conversation-status">
                        <RefreshCw size={12} className="spin" />
                        正在读取对话
                      </div>
                    ) : null}
                    {bucket?.error ? (
                      <div className="sidebar-conversation-error" role="alert">
                        <span>{bucket.error}</span>
                        <button
                          type="button"
                          onClick={() => void loadConversations(project.project_id, true)}
                        >
                          重试
                        </button>
                      </div>
                    ) : null}
                    {!bucket?.loading && !bucket?.error && conversations.length === 0 ? (
                      <p className="sidebar-conversation-empty">暂无对话</p>
                    ) : null}
                    {conversations.map((conversation) => (
                      <Link
                        key={conversation.conversation_id}
                        to={`/projects/${project.project_id}/conversations/${conversation.conversation_id}`}
                        className={`sidebar-conversation-link ${
                          activeConversationId === conversation.conversation_id ? 'is-active' : ''
                        }`}
                        title={conversation.title}
                        onClick={onClose}
                      >
                        <MessageSquare size={14} />
                        <span>{conversation.title}</span>
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </div>

      <div className="sidebar-user">
        <span className="sidebar-user-icon" aria-hidden="true">
          <UserRound size={16} />
        </span>
        <div className="sidebar-user-copy">
          <strong title={username}>{username}</strong>
          <span>{IS_CLOUD_MODE ? '云端账号' : '本地模式'}</span>
        </div>
        {IS_CLOUD_MODE ? (
          <button
            type="button"
            className="icon-btn sidebar-logout"
            onClick={onLogout}
            aria-label="退出登录"
            title="退出登录"
          >
            <LogOut size={16} />
          </button>
        ) : null}
      </div>
    </aside>
  )
}
