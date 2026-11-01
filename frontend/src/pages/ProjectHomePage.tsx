import { useEffect } from 'react'
import {
  ArrowRight,
  ChevronRight,
  Clock3,
  FolderOpen,
  MessageSquarePlus,
  MessagesSquare,
  Sparkles,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { IS_CLOUD_MODE } from '../config'
import { formatDateTime, formatRelativeTime } from '../lib/format'
import { useProjectWorkspace } from '../components/ProjectWorkspaceLayout'
import { ProjectGlyph } from '../components/ProjectGlyph'

const STEPS = [
  { number: '01', title: '开启对话', text: '为不同目标建立独立上下文。' },
  { number: '02', title: '描述任务', text: '输入要分析、生成或执行的内容。' },
  { number: '03', title: '检查结果', text: '查看实时输出、工具状态和最终回答。' },
]

export function ProjectHomePage() {
  const { project, conversations, openNewConversation } = useProjectWorkspace()

  useEffect(() => {
    document.title = `${project.name} · AgentDesk`
  }, [project.name])

  const recentConversations = conversations.slice(0, 4)

  return (
    <div className="project-home">
      <div className="project-home-scroll">
        <section className="project-home-hero">
          <div className="project-home-hero-top">
            <ProjectGlyph projectId={project.project_id} name={project.name} size="large" />
            <span className="project-ready-badge">
              <Sparkles size={13} />
              项目已就绪
            </span>
          </div>
          <span className="eyebrow">PROJECT OVERVIEW</span>
          <h1>{project.name}</h1>
          <p>{project.description || '这个项目还没有描述。你仍然可以直接开始一段 Agent 对话。'}</p>
          {!IS_CLOUD_MODE ? (
            <p className="project-local-hint">本地项目文件请使用本机编辑器查看。</p>
          ) : null}
          <div className="project-home-actions">
            <button type="button" className="btn btn-primary" onClick={openNewConversation}>
              <MessageSquarePlus size={17} />
              新建对话
            </button>
            {recentConversations[0] ? (
              <Link
                to={`/projects/${project.project_id}/conversations/${recentConversations[0].conversation_id}`}
                className="btn btn-secondary"
              >
                继续最近对话
                <ArrowRight size={16} />
              </Link>
            ) : null}
          </div>
          <span className="hero-glow" aria-hidden="true" />
        </section>

        <section className="project-overview-grid">
          <div className="overview-stat">
            <span className="overview-stat-icon">
              <MessagesSquare size={18} />
            </span>
            <span>
              <small>对话数量</small>
              <strong>{conversations.length}</strong>
            </span>
          </div>
          <div className="overview-stat">
            <span className="overview-stat-icon">
              <Clock3 size={18} />
            </span>
            <span>
              <small>最近更新</small>
              <strong>{formatRelativeTime(project.updated_at)}</strong>
            </span>
          </div>
          <div className="overview-stat overview-stat-wide">
            <span className="overview-stat-icon">
              <FolderOpen size={18} />
            </span>
            <span>
              <small>项目目录</small>
              <strong className={project.local_path ? undefined : 'muted-strong'}>
                {project.local_path ||
                  (IS_CLOUD_MODE ? '云端项目（无本地目录）' : '未绑定本地目录')}
              </strong>
            </span>
          </div>
        </section>

        <div className="project-home-columns">
          <section className="project-panel">
            <div className="project-panel-heading">
              <div>
                <span className="eyebrow">CONVERSATIONS</span>
                <h2>继续对话</h2>
              </div>
              {conversations.length > recentConversations.length ? (
                <span className="section-note">共 {conversations.length} 段</span>
              ) : null}
            </div>

            {recentConversations.length === 0 ? (
              <div className="project-panel-empty">
                <MessagesSquare size={24} />
                <strong>还没有对话</strong>
                <p>新建一段对话，向 Agent 描述第一个任务。</p>
                <button type="button" className="btn btn-secondary btn-small" onClick={openNewConversation}>
                  <MessageSquarePlus size={15} />
                  新建对话
                </button>
              </div>
            ) : (
              <div className="recent-conversation-list">
                {recentConversations.map((conversation) => (
                  <Link
                    key={conversation.conversation_id}
                    to={`/projects/${project.project_id}/conversations/${conversation.conversation_id}`}
                    className="recent-conversation-item"
                  >
                    <span className="recent-conversation-icon">
                      <MessagesSquare size={16} />
                    </span>
                    <span>
                      <strong>{conversation.title}</strong>
                      <small>更新于 {formatRelativeTime(conversation.updated_at)}</small>
                    </span>
                    <ChevronRight size={15} />
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section className="project-panel project-guide">
            <div className="project-panel-heading">
              <div>
                <span className="eyebrow">HOW IT WORKS</span>
                <h2>工作方式</h2>
              </div>
            </div>
            <ol className="project-steps">
              {STEPS.map((step) => (
                <li key={step.number}>
                  <span>{step.number}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <p>{step.text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="project-created-at">创建于 {formatDateTime(project.created_at)}</div>
          </section>
        </div>
      </div>
    </div>
  )
}
