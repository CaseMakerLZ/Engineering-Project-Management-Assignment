import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { listConversations } from '../api/conversations'
import { listProjects } from '../api/projects'
import { useAuth } from '../auth/AuthProvider'
import { describeError } from '../lib/errors'
import type { Conversation, Project } from '../types/api'
import { AppSidebar } from './AppSidebar'
import { CreateConversationDialog } from './CreateConversationDialog'
import { CreateProjectDialog } from './CreateProjectDialog'
import { useToast } from './ToastProvider'

const SIDEBAR_COLLAPSED_KEY = 'agentdesk.sidebar.collapsed'

export interface ConversationBucket {
  items: Conversation[]
  loading: boolean
  loaded: boolean
  error: string | null
}

interface AppShellContextValue {
  projects: Project[]
  projectsLoading: boolean
  projectsError: string | null
  conversationsByProject: Record<string, ConversationBucket>
  sidebarCollapsed: boolean
  refreshProjects: () => void
  addProject: (project: Project) => void
  loadConversations: (projectId: string, force?: boolean) => Promise<void>
  refreshConversations: (projectId: string) => void
  openCreateProject: () => void
  openNewConversation: (projectId: string) => void
  openSidebar: () => void
  toggleSidebar: () => void
}

const AppShellContext = createContext<AppShellContextValue | null>(null)

function sortProjects(items: Project[]): Project[] {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at).getTime()
    const rightTime = new Date(right.updated_at || right.created_at).getTime()
    return rightTime - leftTime
  })
}

export function sortConversations(items: Conversation[]): Conversation[] {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at).getTime()
    const rightTime = new Date(right.updated_at || right.created_at).getTime()
    return rightTime - leftTime
  })
}

function projectIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/projects\/([^/]+)/)
  if (!match) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    return match[1]
  }
}

function readSidebarPreference(): boolean {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
}

export function AppShell() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [projectsError, setProjectsError] = useState<string | null>(null)
  const [conversationsByProject, setConversationsByProject] = useState<
    Record<string, ConversationBucket>
  >({})
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarPreference)
  const [createProjectOpen, setCreateProjectOpen] = useState(false)
  const [createConversationProjectId, setCreateConversationProjectId] = useState<string | null>(
    null,
  )
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const { pushToast } = useToast()
  const activeProjectId = projectIdFromPath(location.pathname)

  const projectsGenerationRef = useRef(0)
  const conversationGenerationRef = useRef(new Map<string, number>())
  const conversationInflightRef = useRef(new Map<string, Promise<void>>())
  const loadedConversationIdsRef = useRef(new Set<string>())

  const refreshProjects = useCallback(async () => {
    const generation = ++projectsGenerationRef.current
    setProjectsLoading(true)
    setProjectsError(null)
    try {
      const data = await listProjects()
      if (generation !== projectsGenerationRef.current) return
      setProjects(sortProjects(Array.isArray(data) ? data : []))
    } catch (error) {
      if (generation === projectsGenerationRef.current) {
        setProjectsError(describeError(error))
      }
    } finally {
      if (generation === projectsGenerationRef.current) setProjectsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshProjects()
  }, [refreshProjects, user?.user_id])

  useEffect(() => {
    // AppShell is unmounted on logout, but clearing on identity changes also prevents
    // an account switch during session hydration from exposing a previous cache.
    conversationGenerationRef.current.forEach((_value, projectId) => {
      conversationGenerationRef.current.set(projectId, Number.MAX_SAFE_INTEGER)
    })
    conversationInflightRef.current.clear()
    loadedConversationIdsRef.current.clear()
    setConversationsByProject({})
  }, [user?.user_id])

  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!sidebarOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [sidebarOpen])

  const loadConversations = useCallback(
    (projectId: string, force = false): Promise<void> => {
      if (!projectId) return Promise.resolve()
      if (!force && loadedConversationIdsRef.current.has(projectId)) return Promise.resolve()

      const existing = conversationInflightRef.current.get(projectId)
      if (!force && existing) return existing

      const generation = (conversationGenerationRef.current.get(projectId) ?? 0) + 1
      conversationGenerationRef.current.set(projectId, generation)
      if (force) conversationInflightRef.current.delete(projectId)

      setConversationsByProject((current) => ({
        ...current,
        [projectId]: {
          items: current[projectId]?.items ?? [],
          loading: true,
          loaded: current[projectId]?.loaded ?? false,
          error: null,
        },
      }))

      const request = (async () => {
        try {
          const data = await listConversations(projectId)
          if (conversationGenerationRef.current.get(projectId) !== generation) return
          loadedConversationIdsRef.current.add(projectId)
          setConversationsByProject((current) => ({
            ...current,
            [projectId]: {
              items: sortConversations(Array.isArray(data) ? data : []),
              loading: false,
              loaded: true,
              error: null,
            },
          }))
        } catch (error) {
          if (conversationGenerationRef.current.get(projectId) !== generation) return
          loadedConversationIdsRef.current.delete(projectId)
          setConversationsByProject((current) => ({
            ...current,
            [projectId]: {
              items: current[projectId]?.items ?? [],
              loading: false,
              loaded: false,
              error: describeError(error),
            },
          }))
        } finally {
          if (conversationGenerationRef.current.get(projectId) === generation) {
            conversationInflightRef.current.delete(projectId)
          }
        }
      })()

      conversationInflightRef.current.set(projectId, request)
      return request
    },
    [],
  )

  useEffect(() => {
    if (activeProjectId) void loadConversations(activeProjectId)
  }, [activeProjectId, loadConversations])

  const addProject = useCallback((project: Project) => {
    setProjects((current) =>
      sortProjects([project, ...current.filter((item) => item.project_id !== project.project_id)]),
    )
  }, [])

  const handleProjectCreated = (project: Project) => {
    addProject(project)
    pushToast('项目已创建。', 'success')
    navigate(`/projects/${project.project_id}`)
  }

  const openNewConversation = useCallback((projectId: string) => {
    setCreateConversationProjectId(projectId)
  }, [])

  const handleConversationCreated = (conversation: Conversation) => {
    loadedConversationIdsRef.current.add(conversation.project_id)
    setConversationsByProject((current) => ({
      ...current,
      [conversation.project_id]: {
        items: sortConversations([
          conversation,
          ...(current[conversation.project_id]?.items ?? []).filter(
            (item) => item.conversation_id !== conversation.conversation_id,
          ),
        ]),
        loading: false,
        loaded: true,
        error: null,
      },
    }))
    pushToast('对话已创建，可以开始提问了。', 'success')
    navigate(
      `/projects/${conversation.project_id}/conversations/${conversation.conversation_id}`,
    )
  }

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((current) => {
      const next = !current
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next))
      return next
    })
  }, [])

  const value = useMemo<AppShellContextValue>(
    () => ({
      projects,
      projectsLoading,
      projectsError,
      conversationsByProject,
      sidebarCollapsed,
      refreshProjects: () => void refreshProjects(),
      addProject,
      loadConversations,
      refreshConversations: (projectId: string) => void loadConversations(projectId, true),
      openCreateProject: () => setCreateProjectOpen(true),
      openNewConversation,
      openSidebar: () => setSidebarOpen(true),
      toggleSidebar,
    }),
    [
      addProject,
      conversationsByProject,
      loadConversations,
      openNewConversation,
      projects,
      projectsError,
      projectsLoading,
      refreshProjects,
      sidebarCollapsed,
      toggleSidebar,
    ],
  )

  return (
    <AppShellContext.Provider value={value}>
      <div
        className={`app-shell ${sidebarOpen ? 'sidebar-open' : ''} ${
          sidebarCollapsed ? 'sidebar-collapsed' : ''
        }`}
      >
        <button
          type="button"
          className="app-scrim"
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭导航"
          tabIndex={sidebarOpen ? 0 : -1}
        />
        <AppSidebar
          open={sidebarOpen}
          collapsed={sidebarCollapsed}
          onClose={() => setSidebarOpen(false)}
          onLogout={() => void logout()}
        />
        <div className="app-content">
          <Outlet />
        </div>
        <CreateProjectDialog
          open={createProjectOpen}
          onClose={() => setCreateProjectOpen(false)}
          onCreated={handleProjectCreated}
        />
        <CreateConversationDialog
          open={createConversationProjectId !== null}
          projectId={createConversationProjectId ?? ''}
          onClose={() => setCreateConversationProjectId(null)}
          onCreated={handleConversationCreated}
        />
      </div>
    </AppShellContext.Provider>
  )
}

export function useAppShell(): AppShellContextValue {
  const context = useContext(AppShellContext)
  if (!context) {
    throw new Error('useAppShell must be used inside AppShell')
  }
  return context
}
