import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { ArrowLeft, FolderSearch, FolderTree, Menu } from 'lucide-react'
import { Link, Outlet, useParams } from 'react-router-dom'
import { getProject } from '../api/projects'
import { IS_CLOUD_MODE } from '../config'
import { describeError, isResourceNotFound } from '../lib/errors'
import type { Conversation, Project } from '../types/api'
import { useAppShell } from './AppShell'
import { ProjectFilesPanel } from './ProjectFilesPanel'

const FILES_WIDTH_KEY = 'agentdesk.files.width'
const DEFAULT_FILES_WIDTH = 360
const MIN_FILES_WIDTH = 280
const MIN_CHAT_WIDTH = 430

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

function readFilesWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_FILES_WIDTH
  const stored = Number(window.localStorage.getItem(FILES_WIDTH_KEY))
  if (!Number.isFinite(stored)) return DEFAULT_FILES_WIDTH
  return Math.max(MIN_FILES_WIDTH, Math.min(stored, 720))
}

export function ProjectWorkspaceLayout() {
  const { projectId = '' } = useParams()
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filesPanelOpen, setFilesPanelOpen] = useState(() =>
    typeof window === 'undefined' ? true : window.innerWidth > 1280,
  )
  const [filesPanelWidth, setFilesPanelWidth] = useState(readFilesWidth)
  const [filesRefreshVersion, setFilesRefreshVersion] = useState(0)
  const [taskMutating, setTaskMutating] = useState(false)
  const activeTaskIdsRef = useRef(new Set<string>())
  const projectGenerationRef = useRef(0)
  const workspaceRef = useRef<HTMLDivElement>(null)
  const filesPanelWidthRef = useRef(filesPanelWidth)
  const resizeCleanupRef = useRef<(() => void) | null>(null)
  const { openSidebar, conversationsByProject, loadConversations, refreshConversations, openNewConversation } =
    useAppShell()

  filesPanelWidthRef.current = filesPanelWidth

  useEffect(() => {
    activeTaskIdsRef.current.clear()
    setTaskMutating(false)
  }, [projectId])

  useEffect(() => {
    const generation = ++projectGenerationRef.current
    setLoading(true)
    setError(null)
    setProject(null)

    void getProject(projectId)
      .then((projectData) => {
        if (generation !== projectGenerationRef.current) return
        setProject(projectData)
        setLoading(false)
        void loadConversations(projectId)
      })
      .catch((loadError: unknown) => {
        if (generation !== projectGenerationRef.current) return
        setError(
          isResourceNotFound(loadError)
            ? '项目不存在、已被删除，或当前账号无权访问。'
            : describeError(loadError),
        )
        setLoading(false)
      })

    return () => {
      if (generation === projectGenerationRef.current) {
        projectGenerationRef.current += 1
      }
    }
  }, [loadConversations, projectId])

  useEffect(() => {
    if (!project) return
    document.title = `${project.name} · AgentDesk`
  }, [project])

  useEffect(
    () => () => {
      resizeCleanupRef.current?.()
      document.body.classList.remove('is-resizing-files')
    },
    [],
  )

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

  const applyFilesWidth = useCallback((next: number, persist = false) => {
    const workspaceWidth = workspaceRef.current?.getBoundingClientRect().width ?? window.innerWidth
    const maximum = Math.max(MIN_FILES_WIDTH, Math.min(720, workspaceWidth - MIN_CHAT_WIDTH))
    const clamped = Math.round(Math.max(MIN_FILES_WIDTH, Math.min(next, maximum)))
    filesPanelWidthRef.current = clamped
    setFilesPanelWidth(clamped)
    if (persist) window.localStorage.setItem(FILES_WIDTH_KEY, String(clamped))
  }, [])

  const startFilesResize = (event: React.PointerEvent<HTMLElement>) => {
    if (window.innerWidth <= 1280) return
    event.preventDefault()
    resizeCleanupRef.current?.()
    const startX = event.clientX
    const startWidth = filesPanelWidthRef.current
    document.body.classList.add('is-resizing-files')

    const handleMove = (moveEvent: PointerEvent) => {
      applyFilesWidth(startWidth + startX - moveEvent.clientX)
    }
    const cleanup = () => {
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
      window.removeEventListener('pointercancel', handleUp)
      window.removeEventListener('blur', handleUp)
      document.body.classList.remove('is-resizing-files')
      resizeCleanupRef.current = null
    }
    const handleUp = () => {
      window.localStorage.setItem(FILES_WIDTH_KEY, String(filesPanelWidthRef.current))
      cleanup()
    }

    resizeCleanupRef.current = cleanup
    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
    window.addEventListener('pointercancel', handleUp)
    window.addEventListener('blur', handleUp)
  }

  const resizeFilesWithKeyboard = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Home') {
      event.preventDefault()
      applyFilesWidth(DEFAULT_FILES_WIDTH, true)
      return
    }
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const direction = event.key === 'ArrowLeft' ? 16 : -16
    applyFilesWidth(filesPanelWidthRef.current + direction, true)
  }

  const bucket = conversationsByProject[projectId]
  const conversations = bucket?.items ?? []

  const contextValue = useMemo<ProjectWorkspaceContextValue | null>(() => {
    if (!project) return null
    return {
      project,
      conversations,
      conversationsLoading: bucket?.loading ?? true,
      conversationsError: bucket?.error ?? null,
      refreshConversations: () => refreshConversations(projectId),
      openNewConversation: () => openNewConversation(projectId),
      filesPanelOpen,
      toggleFilesPanel,
      taskMutating,
      notifyTaskStarted,
      notifyTaskSettled,
    }
  }, [
    bucket?.error,
    bucket?.loading,
    conversations,
    filesPanelOpen,
    notifyTaskSettled,
    notifyTaskStarted,
    openNewConversation,
    project,
    projectId,
    refreshConversations,
    taskMutating,
    toggleFilesPanel,
  ])

  if (loading) {
    return (
      <div className="workspace-loading">
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
          <h1>无法打开这个项目</h1>
          <p>{error || '项目不存在或已被删除。'}</p>
          <div className="error-actions">
            <Link to="/projects" className="btn btn-secondary">
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
        className={`workspace ${IS_CLOUD_MODE && filesPanelOpen ? 'files-panel-open' : ''}`}
        ref={workspaceRef}
        style={
          {
            '--files-panel-current-width': `${filesPanelWidth}px`,
          } as React.CSSProperties
        }
      >
        <section className="workspace-stage">
          <div className="workspace-mobile-bar">
            <button
              type="button"
              className="icon-btn"
              onClick={openSidebar}
              aria-label="打开项目与对话导航"
            >
              <Menu size={19} />
            </button>
            <strong className="workspace-mobile-project" title={project.name}>
              {project.name}
            </strong>
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
              onResizeStart={startFilesResize}
              onResizeKeyDown={resizeFilesWithKeyboard}
            />
          </>
        ) : null}
      </div>
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
