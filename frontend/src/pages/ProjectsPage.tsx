import { useEffect } from 'react'
import { AlertCircle, Folder, Menu, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAppShell } from '../components/AppShell'

export function ProjectsPage() {
  const { projects, projectsLoading, projectsError, refreshProjects, openSidebar } = useAppShell()

  useEffect(() => {
    document.title = '项目 · AgentDesk'
  }, [])

  return (
    <div className="projects-page">
      <header className="projects-topbar">
        <button
          type="button"
          className="mobile-menu-button"
          onClick={openSidebar}
          aria-label="打开项目导航"
        >
          <Menu size={19} />
        </button>
        <span>项目</span>
        <button
          type="button"
          className="icon-btn topbar-refresh"
          onClick={refreshProjects}
          aria-label="刷新项目"
          title="刷新项目"
        >
          <RefreshCw size={16} className={projectsLoading ? 'spin' : undefined} />
        </button>
      </header>

      <main className="projects-content">
        <div className="projects-list-heading">
          <div>
            <h1>项目</h1>
            <p>选择项目进入工作区，或从左侧创建新项目。</p>
          </div>
        </div>

        {projectsError ? (
          <div className="notice notice-error" role="alert">
            <AlertCircle size={18} />
            <div>
              <strong>项目列表加载失败</strong>
              <p>{projectsError}</p>
            </div>
            <button type="button" className="btn btn-secondary btn-small" onClick={refreshProjects}>
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        ) : null}

        {projectsLoading && projects.length === 0 ? (
          <div className="compact-project-list" aria-label="正在加载项目">
            {[0, 1, 2].map((index) => (
              <div key={index} className="compact-project-row project-row-skeleton">
                <i />
                <span />
              </div>
            ))}
          </div>
        ) : null}

        {!projectsLoading && !projectsError && projects.length === 0 ? (
          <section className="projects-empty-state">
            <Folder size={25} />
            <h2>还没有项目</h2>
            <p>使用左侧“新建项目”开始。</p>
          </section>
        ) : null}

        {projects.length > 0 ? (
          <section className="compact-project-list" aria-label="项目列表">
            {projects.map((project) => (
              <Link
                key={project.project_id}
                to={`/projects/${project.project_id}`}
                className="compact-project-row"
                title={project.name}
              >
                <span className="compact-project-icon" aria-hidden="true">
                  <Folder size={18} />
                </span>
                <span className="compact-project-copy">
                  <strong>{project.name}</strong>
                  {project.description ? <small>{project.description}</small> : null}
                </span>
              </Link>
            ))}
          </section>
        ) : null}
      </main>
    </div>
  )
}
