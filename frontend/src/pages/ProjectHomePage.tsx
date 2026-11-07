import { useEffect } from 'react'
import { FolderTree, MessageSquarePlus } from 'lucide-react'
import { IS_CLOUD_MODE } from '../config'
import { useProjectWorkspace } from '../components/ProjectWorkspaceLayout'

export function ProjectHomePage() {
  const {
    project,
    conversations,
    conversationsLoading,
    conversationsError,
    openNewConversation,
    filesPanelOpen,
    toggleFilesPanel,
    refreshConversations,
  } = useProjectWorkspace()

  useEffect(() => {
    document.title = `${project.name} · AgentDesk`
  }, [project.name])

  return (
    <div className="project-empty-workspace">
      <header className="workspace-page-header">
        <div className="workspace-page-title">
          <span>当前项目</span>
          <h1 title={project.name}>{project.name}</h1>
        </div>
        {IS_CLOUD_MODE ? (
          <button
            type="button"
            className="icon-btn"
            onClick={toggleFilesPanel}
            aria-label={filesPanelOpen ? '收起项目文件' : '打开项目文件'}
            title={filesPanelOpen ? '收起项目文件' : '打开项目文件'}
          >
            <FolderTree size={17} />
          </button>
        ) : null}
      </header>

      <main className="workspace-empty-guide">
        <MessageSquarePlus size={24} />
        <h2>选择一个对话，或新建对话</h2>
        <p>项目下方的对话列表可以展开查看；新对话会直接打开。</p>
        {conversationsError ? (
          <button type="button" className="text-action" onClick={refreshConversations}>
            对话加载失败，点击重试
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={openNewConversation}
            disabled={conversationsLoading}
          >
            <MessageSquarePlus size={15} />
            新建对话
          </button>
        )}
        {conversations.length > 0 ? (
          <span className="workspace-empty-note">
            当前项目有 {conversations.length} 个对话，可从左侧继续。
          </span>
        ) : null}
      </main>
    </div>
  )
}
