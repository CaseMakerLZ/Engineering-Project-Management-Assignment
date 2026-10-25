import { useEffect } from 'react'
import {
  AlertCircle,
  ArrowUpRight,
  FolderKanban,
  Menu,
  Plus,
  RefreshCw,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { IS_CLOUD_MODE } from '../config'
import { formatRelativeTime } from '../lib/format'
import { useAppShell } from '../components/AppShell'
import { EmptyState } from '../components/EmptyState'
import { ProjectGlyph } from '../components/ProjectGlyph'

function todayLabel(): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date())
}

export function ProjectsPage() {
  const {
    projects,
    projectsLoading,
    projectsError,
    refreshProjects,
    openCreateProject,
    openSidebar,
  } = useAppShell()

  useEffect(() => {
    document.title = '项目 · AgentDesk'
  }, [])

  return (
    <div className="projects-page">
      <div className="projects-topbar">
        <button type="button" className="mobile-menu-button" onClick={openSidebar} aria-label="打开导航">
          <Menu size={19} />
        </button>
        <span className="projects-mode-badge">
          <i className={IS_CLOUD_MODE ? 'mode-cloud' : 'mode-local'} />
          {IS_CLOUD_MODE ? '云端工作区' : '本地工作区'}
        </span>
        <button
          type="button"
          className="icon-btn topbar-refresh"
          onClick={refreshProjects}
          aria-label="刷新项目"
          title="刷新项目"
        >
          <RefreshCw size={16} className={projectsLoading ? 'spin' : undefined} />
        </button>
      </div>

      <main className="projects-content">
        <header className="projects-hero">
          <div className="projects-hero-copy">
            <span className="eyebrow">PROJECT INDEX · {todayLabel()}</span>
            <h1>
              项目<span>。</span>
            </h1>
            <p>用一个项目收拢上下文，在持续对话中把任务向前推进。</p>
          </div>
          <div className="projects-hero-actions">
            <span className="project-count">
              <strong>{projects.length}</strong>
              <span>个项目</span>
            </span>
            <button type="button" className="btn btn-primary" onClick={openCreateProject}>
              <Plus size={17} />
              新建项目
            </button>
          </div>
          <div className="projects-hero-line" aria-hidden="true" />
        </header>

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
          <div className="project-grid" aria-label="正在加载项目">
            {[0, 1, 2].map((index) => (
              <div key={index} className="project-card project-card-skeleton">
                <span />
                <i />
                <i />
                <i />
              </div>
            ))}
          </div>
        ) : null}

        {!projectsLoading && !projectsError && projects.length === 0 ? (
          <section className="projects-empty-surface">
            <EmptyState
              icon={FolderKanban}
              eyebrow="FRESH START"
              title="还没有项目"
              description={
                IS_CLOUD_MODE
                  ? '创建第一个项目，然后新建对话，把任务交给 Agent。'
                  : '创建第一个项目并绑定本地目录，Java 后端会在该目录中执行 Agent 任务。'
              }
              action={
                <button type="button" className="btn btn-primary" onClick={openCreateProject}>
                  <Plus size={17} />
                  创建第一个项目
                </button>
              }
            />
          </section>
        ) : null}

        {projects.length > 0 ? (
          <section className="project-grid-section">
            <div className="section-heading-row">
              <div>
                <span className="eyebrow">ALL PROJECTS</span>
                <h2>你的工作区</h2>
              </div>
              <span className="section-note">按最近更新排序</span>
            </div>
            <div className="project-grid">
              {projects.map((project) => (
                <Link
                  key={project.project_id}
                  to={`/projects/${project.project_id}`}
                  className="project-card"
                >
                  <div className="project-card-top">
                    <ProjectGlyph projectId={project.project_id} name={project.name} />
                    <span className="project-open-icon">
                      <ArrowUpRight size={17} />
                    </span>
                  </div>
                  <div className="project-card-copy">
                    <h3>{project.name}</h3>
                    <p>{project.description || '这个项目还没有描述。'}</p>
                  </div>
                  <div className="project-card-footer">
                    <span>更新于 {formatRelativeTime(project.updated_at)}</span>
                    <span className="project-card-id">#{project.project_id.slice(-6)}</span>
                  </div>
                </Link>
              ))}
              <button type="button" className="project-card project-card-new" onClick={openCreateProject}>
                <span className="project-new-icon">
                  <Plus size={22} />
                </span>
                <strong>新建项目</strong>
                <span>开启新的 Agent 工作流</span>
              </button>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  )
}
