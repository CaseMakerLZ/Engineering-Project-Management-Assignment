import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { listProjects } from '../api/projects'
import { useAuth } from '../auth/AuthProvider'
import { describeError } from '../lib/errors'
import type { Project } from '../types/api'
import { AppSidebar } from './AppSidebar'
import { CreateProjectDialog } from './CreateProjectDialog'
import { useToast } from './ToastProvider'

interface AppShellContextValue {
  projects: Project[]
  projectsLoading: boolean
  projectsError: string | null
  refreshProjects: () => void
  addProject: (project: Project) => void
  openCreateProject: () => void
  openSidebar: () => void
}

const AppShellContext = createContext<AppShellContextValue | null>(null)

function sortProjects(items: Project[]): Project[] {
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

export function AppShell() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [projectsError, setProjectsError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [createProjectOpen, setCreateProjectOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const { pushToast } = useToast()
  const activeProjectId = projectIdFromPath(location.pathname)

  const refreshProjects = useCallback(async () => {
    setProjectsLoading(true)
    setProjectsError(null)
    try {
      const data = await listProjects()
      setProjects(sortProjects(Array.isArray(data) ? data : []))
    } catch (error) {
      setProjectsError(describeError(error))
    } finally {
      setProjectsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshProjects()
  }, [refreshProjects])

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

  const value = useMemo<AppShellContextValue>(
    () => ({
      projects,
      projectsLoading,
      projectsError,
      refreshProjects: () => void refreshProjects(),
      addProject,
      openCreateProject: () => setCreateProjectOpen(true),
      openSidebar: () => setSidebarOpen(true),
    }),
    [addProject, projects, projectsError, projectsLoading, refreshProjects],
  )

  return (
    <AppShellContext.Provider value={value}>
      <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <button
          type="button"
          className="app-scrim"
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭导航"
          tabIndex={sidebarOpen ? 0 : -1}
        />
        <AppSidebar
          open={sidebarOpen}
          projects={projects}
          loading={projectsLoading}
          error={projectsError}
          activeProjectId={activeProjectId}
          user={user}
          onClose={() => setSidebarOpen(false)}
          onCreateProject={() => setCreateProjectOpen(true)}
          onRefreshProjects={() => void refreshProjects()}
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
