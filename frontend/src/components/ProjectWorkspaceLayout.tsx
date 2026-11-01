import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  ArrowLeft,
  ChevronRight,
  FolderSearch,
  FolderTree,
  Menu,
  MessagesSquare,
  Plus,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { listConversations } from '../api/conversations'
import { getProject } from '../api/projects'
import { IS_CLOUD_MODE } from '../config'
import { describeError, isResourceNotFound } from '../lib/errors'
import { formatRelativeTime } from '../lib/format'
import type { Conversation, Project } from '../types/api'
import { useAppShell } from './AppShell'
import { CreateConversationDialog } from './CreateConversationDialog'
import { ProjectGlyph } from './ProjectGlyph'
import { ProjectFilesPanel } from './ProjectFilesPanel'
import { useToast } from './ToastProvider'

interface ProjectWorkspaceContextValue {
  project: Project
  conversations: Conversation[]
  conversationsLoading: boolean
  conversationsError: string | null
  refreshConversations: () => void
  openNewConversation: () => void
  filesPanelOpen: boolean
  toggleFilesPanel: () => void
  taskMutating: boolean
  notifyTaskStarted: (taskId: string) => void
  notifyTaskSettled: (taskId: string) => void
}

const ProjectWorkspaceContext = createContext<ProjectWorkspaceContextValue | null>(null)

function sortConversations(items: Conversation[]): Conversation[] {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at).getTime()
    const rightTime = new Date(right.updated_at || right.created_at).getTime()
    return rightTime - leftTime
  })
}

export function ProjectWorkspaceLayout() {
  const { projectId = '' } = useParams()
  const [project, setProject] = useState<Project | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [conversationsLoading, setConversationsLoading] = useState(true)
  const [conversationsError, setConversationsError] = useState<string | null>(null)
  const [paneOpen, setPaneOpen] = useState(false)
  const [filesPanelOpen, setFilesPanelOpen] = useState(() =>
    typeof window === 'undefined'
      ? true
      : !window.matchMedia('(max-width: 1280px)').matches,
  )
  const [filesRefreshVersion, setFilesRefreshVersion] = useState(0)
  const [taskMutating, setTaskMutating] = useState(false)
  const activeTaskIdsRef = useRef(new Set<string>())
  const [createConversationOpen, setCreateConversationOpen] = useState(false)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const { openSidebar } = useAppShell()
  const { pushToast } = useToast()

  useEffect(() => {
    activeTaskIdsRef.current.clear()
    setTaskMutating(false)
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setProject(null)
    setConversations([])
    setConversationsLoading(true)
    setConversationsError(null)
    setQuery('')

    const loadProjectData = async () => {
      try {
        const projectData = await getProject(projectId)
        if (cancelled) return
        setProject(projectData)
        setLoading(false)
      } catch (loadError) {
        if (!cancelled) {
          setError(
            isResourceNotFound(loadError)
              ? '项目不存在、已被删除，或当前账号无权访问。'
              : describeError(loadError),
          )
          setLoading(false)
        }
        return
      }

      try {
        const conversationData = await listConversations(projectId)
        if (!cancelled) {
          setConversations(sortConversations(Array.isArray(conversationData) ? conversationData : []))
        }
      } catch (loadError) {
        if (!cancelled) setConversationsError(describeError(loadError))
      } finally {
        if (!cancelled) setConversationsLoading(false)
      }
    }

    void loadProjectData()
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    setPaneOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (paneOpen) {
      document.body.classList.add('pane-locked')
    } else {
      document.body.classList.remove('pane-locked')
    }
    return () => document.body.classList.remove('pane-locked')
  }, [paneOpen])

  useEffect(() => {
    if (!project) return
    document.title = `${project.name} · AgentDesk`
  }, [project])

  const refreshConversations = useCallback(async () => {
    setConversationsLoading(true)
    setConversationsError(null)
    try {
      const data = await listConversations(projectId)
      setConversations(sortConversations(Array.isArray(data) ? data : []))
    } catch (loadError) {
      setConversationsError(describeError(loadError))
    } finally {
      setConversationsLoading(false)
    }
  }, [projectId])

  const handleConversationCreated = (conversation: Conversation) => {
    setConversations((current) =>
      sortConversations([
        conversation,
        ...current.filter((item) => item.conversation_id !== conversation.conversation_id),
      ]),
    )
    pushToast('对话已创建，可以开始提问了。', 'success')
    navigate(`/projects/${projectId}/conversations/${conversation.conversation_id}`)
  }

  const notifyTaskStarted = useCallback((taskId: string) => {
    activeTaskIdsRef.current.add(taskId)
    setTaskMutating(true)
  }, [])

  const notifyTaskSettled = useCallback((taskId: string) => {
    activeTaskIdsRef.current.delete(taskId)
    setTaskMutating(activeTaskIdsRef.current.size > 0)
    setFilesRefreshVersion((current) => current + 1)
  }, [])

  const toggleFilesPanel = useCallback(() => {
    setFilesPanelOpen((current) => !current)
  }, [])

  const filteredConversations = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return conversations
    return conversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(normalized),
    )
  }, [conversations, query])

  const activeConversationId = useMemo(() => {
    const match = location.pathname.match(/\/conversations\/([^/]+)/)
    if (!match) return null
    try {
      return decodeURIComponent(match[1])
    } catch {
      return match[1]
    }
  }, [location.pathname])

  const contextValue = useMemo<ProjectWorkspaceContextValue | null>(() => {
    if (!project) return null
    return {
      project,
      conversations,
      conversationsLoading,
      conversationsError,
      refreshConversations: () => void refreshConversations(),
      openNewConversation: () => setCreateConversationOpen(true),
      filesPanelOpen,
      toggleFilesPanel,
      taskMutating,
      notifyTaskStarted,
      notifyTaskSettled,
    }
  }, [
    conversations,
    conversationsError,
    conversationsLoading,
    filesPanelOpen,
    notifyTaskSettled,
    notifyTaskStarted,
    project,
    refreshConversations,
    taskMutating,
    toggleFilesPanel,
  ])

  if (loading) {
    return (
      <div className="workspace-loading">
        <div className="workspace-loading-pane">
          <i />
          <i />
          <i />
        </div>
        <div className="workspace-loading-stage">
          <span className="loading-orb" />
          <p>正在打开项目…</p>
        </div>
      </div>
    )
  }

  if (error || !project || !contextValue) {
    return (
      <div className="workspace-error-page">
        <button type="button" className="mobile-menu-button" onClick={openSidebar} aria-label="打开导航">
          <Menu size={19} />
        </button>
        <div className="workspace-error-card">
          <span className="workspace-error-icon">
            <FolderSearch size={28} />
          </span>
          <span className="eyebrow">PROJECT UNAVAILABLE</span>
          <h1>无法打开这个项目</h1>
          <p>{error || '项目不存在或已被删除。'}</p>
          <div className="error-actions">
            <Link to="/projects" className="btn btn-primary">
              <ArrowLeft size={16} />
              返回项目列表
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ProjectWorkspaceContext.Provider value={contextValue}>
      <div
        className={`workspace ${paneOpen ? 'pane-open' : ''} ${
          IS_CLOUD_MODE && filesPanelOpen ? 'files-panel-open' : ''
        }`}
      >
        <button
          type="button"
          className="pane-scrim"
          onClick={() => setPaneOpen(false)}
          aria-label="关闭对话列表"
          tabIndex={paneOpen ? 0 : -1}
        />

        <aside className={`conversation-pane ${paneOpen ? 'is-open' : ''}`}>
          <div className="conversation-pane-top">
            <button
              type="button"
              className="icon-btn pane-menu-button"
              onClick={openSidebar}
              aria-label="打开项目导航"
            >
              <Menu size={18} />
            </button>
            <ProjectGlyph projectId={project.project_id} name={project.name} size="small" />
            <div className="conversation-pane-project-copy">
              <span>当前项目</span>
              <strong>{project.name}</strong>
            </div>
            <button
              type="button"
              className="icon-btn pane-close"
              onClick={() => setPaneOpen(false)}
              aria-label="关闭对话列表"
            >
              <X size={18} />
            </button>
          </div>

          <button
            type="button"
            className="new-conversation-button"
            onClick={() => setCreateConversationOpen(true)}
          >
            <span>
              <Plus size={17} />
            </span>
            新建对话
          </button>

          <div className="conversation-list-heading">
            <span>对话</span>
            <small>{conversations.length}</small>
            <button
              type="button"
              className="icon-btn icon-btn-xs"
              onClick={() => void refreshConversations()}
              aria-label="刷新对话列表"
              title="刷新对话列表"
            >
              <RefreshCw size={13} className={conversationsLoading ? 'spin' : undefined} />
            </button>
          </div>

          <label className="conversation-search">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索对话"
              aria-label="搜索对话"
            />
            {query ? (
              <button type="button" onClick={() => setQuery('')} aria-label="清空搜索">
                <X size={13} />
              </button>
            ) : null}
          </label>

          <div className="conversation-list">
            {conversationsLoading ? (
              <div className="conversation-skeleton" aria-label="正在加载对话">
                <i />
                <i />
                <i />
              </div>
            ) : null}

            {conversationsError ? (
              <div className="conversation-inline-error">
                <span>{conversationsError}</span>
                <button type="button" onClick={() => void refreshConversations()}>
                  重新加载
                </button>
              </div>
            ) : null}

            {!conversationsLoading && !conversationsError && filteredConversations.length === 0 ? (
              <div className="conversation-empty">
                <MessagesSquare size={20} />
                <strong>{query ? '没有匹配的对话' : '还没有对话'}</strong>
                <p>{query ? '换一个关键词试试。' : '新建一段对话，向 Agent 描述你的任务。'}</p>
              </div>
            ) : null}

            {filteredConversations.map((conversation) => (
              <Link
                key={conversation.conversation_id}
                to={`/projects/${projectId}/conversations/${conversation.conversation_id}`}
                className={`conversation-item ${
                  activeConversationId === conversation.conversation_id ? 'is-active' : ''
                }`}
              >
                <span className="conversation-item-indicator" aria-hidden="true" />
                <span className="conversation-item-copy">
                  <strong>{conversation.title}</strong>
                  <small>{formatRelativeTime(conversation.updated_at)}</small>
                </span>
                <ChevronRight size={14} className="conversation-item-arrow" />
              </Link>
            ))}
          </div>

          <Link to="/projects" className="conversation-pane-back">
            <ArrowLeft size={15} />
            所有项目
          </Link>
        </aside>

        <section className="workspace-stage">
          <div className="workspace-mobile-bar">
            <button
              type="button"
              className="icon-btn"
              onClick={openSidebar}
              aria-label="打开项目导航"
            >
              <Menu size={19} />
            </button>
            <div className="workspace-mobile-project">
              <ProjectGlyph projectId={project.project_id} name={project.name} size="small" />
              <strong>{project.name}</strong>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={() => setPaneOpen(true)}
              aria-label="打开对话列表"
            >
              <MessagesSquare size={19} />
            </button>
            {IS_CLOUD_MODE ? (
              <button
                type="button"
                className="icon-btn"
                onClick={toggleFilesPanel}
                aria-label={filesPanelOpen ? '收起项目文件' : '打开项目文件'}
              >
                <FolderTree size={18} />
              </button>
            ) : null}
          </div>
          <Outlet context={contextValue} />
          {IS_CLOUD_MODE && !filesPanelOpen && !activeConversationId ? (
            <button
              type="button"
              className="files-panel-reopen"
              onClick={toggleFilesPanel}
            >
              <FolderTree size={15} />
              项目文件
            </button>
          ) : null}
        </section>
        {IS_CLOUD_MODE && filesPanelOpen ? (
          <>
            <button
              type="button"
              className="files-panel-scrim"
              onClick={() => setFilesPanelOpen(false)}
              aria-label="关闭项目文件"
            />
            <ProjectFilesPanel
              projectId={project.project_id}
              refreshVersion={filesRefreshVersion}
              taskMutating={taskMutating}
              onClose={() => setFilesPanelOpen(false)}
            />
          </>
        ) : null}
      </div>

      <CreateConversationDialog
        open={createConversationOpen}
        projectId={projectId}
        onClose={() => setCreateConversationOpen(false)}
        onCreated={handleConversationCreated}
      />
    </ProjectWorkspaceContext.Provider>
  )
}

export function useProjectWorkspace(): ProjectWorkspaceContextValue {
  const context = useContext(ProjectWorkspaceContext)
  if (!context) {
    throw new Error('useProjectWorkspace must be used inside ProjectWorkspaceLayout')
  }
  return context
}
