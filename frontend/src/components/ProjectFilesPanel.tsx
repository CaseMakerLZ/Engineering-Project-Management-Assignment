import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Code2,
  Download,
  File,
  Folder,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  X,
} from 'lucide-react'
import { downloadProjectArchive, downloadProjectFile } from '../api/files'
import { describeError } from '../lib/errors'
import { formatFileSize } from '../lib/format'
import { useProjectFiles } from '../hooks/useProjectFiles'
import type { ProjectFileEntry } from '../types/files'
import { useToast } from './ToastProvider'

interface ProjectFilesPanelProps {
  projectId: string
  refreshVersion: number
  taskMutating: boolean
  onClose: () => void
}

interface DirectoryBranchProps {
  path: string
  directories: ReturnType<typeof useProjectFiles>['directories']
  expanded: Set<string>
  selectedPath: string | null
  level: number
  onToggle: (path: string) => void
  onLoadMore: (path: string, cursor: string) => void
  onOpenFile: (path: string) => void
}

function DirectoryBranch({
  path,
  directories,
  expanded,
  selectedPath,
  level,
  onToggle,
  onLoadMore,
  onOpenFile,
}: DirectoryBranchProps) {
  const directory = directories[path]
  const isExpanded = expanded.has(path)

  return (
    <div className="file-tree-branch" role="group">
      {directory?.loading ? (
        <div className="file-tree-status" style={{ paddingLeft: 12 + level * 14 }}>
          <LoaderCircle size={13} className="spin" />
          正在读取…
        </div>
      ) : null}
      {directory?.error ? (
        <div className="file-tree-error" style={{ marginLeft: 8 + level * 14 }}>
          <AlertCircle size={13} />
          <span>{directory.error}</span>
        </div>
      ) : null}
      {!directory?.loading && !directory?.error && isExpanded && directory?.entries.length === 0 ? (
        <div className="file-tree-empty" style={{ paddingLeft: 12 + level * 14 }}>
          空目录
        </div>
      ) : null}
      {isExpanded
        ? directory?.entries.map((entry: ProjectFileEntry) => {
            const indent = 8 + level * 15
            if (entry.kind === 'directory') {
              const childExpanded = expanded.has(entry.path)
              return (
                <div key={`${entry.kind}:${entry.path}`}>
                  <button
                    type="button"
                    className="file-tree-row"
                    style={{ paddingLeft: indent }}
                    onClick={() => onToggle(entry.path)}
                    aria-expanded={childExpanded}
                  >
                    {childExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    {childExpanded ? <FolderOpen size={15} /> : <Folder size={15} />}
                    <span>{entry.name}</span>
                  </button>
                  {childExpanded ? (
                    <DirectoryBranch
                      path={entry.path}
                      directories={directories}
                      expanded={expanded}
                      selectedPath={selectedPath}
                      level={level + 1}
                      onToggle={onToggle}
                      onLoadMore={onLoadMore}
                      onOpenFile={onOpenFile}
                    />
                  ) : null}
                </div>
              )
            }
            return (
              <button
                key={`${entry.kind}:${entry.path}`}
                type="button"
                className={`file-tree-row file-tree-file ${
                  selectedPath === entry.path ? 'is-active' : ''
                }`}
                style={{ paddingLeft: indent + 13 }}
                onClick={() => onOpenFile(entry.path)}
                title={entry.path}
              >
                <File size={14} />
                <span>{entry.name}</span>
                {entry.size_bytes !== null ? (
                  <small>{formatFileSize(entry.size_bytes)}</small>
                ) : null}
              </button>
            )
          })
        : null}
      {isExpanded && directory?.nextCursor ? (
        <button
          type="button"
          className="file-tree-more"
          style={{ marginLeft: 12 + level * 15 }}
          disabled={directory.loadingMore}
          onClick={() => onLoadMore(path, directory.nextCursor as string)}
        >
          {directory.loadingMore ? <LoaderCircle size={12} className="spin" /> : null}
          加载更多
        </button>
      ) : null}
    </div>
  )
}

export function ProjectFilesPanel({
  projectId,
  refreshVersion,
  taskMutating,
  onClose,
}: ProjectFilesPanelProps) {
  const { directories, expanded, preview, refreshing, toggleDirectory, loadDirectory, openFile, refresh } =
    useProjectFiles(projectId, refreshVersion)
  const { pushToast } = useToast()
  const [downloadKey, setDownloadKey] = useState<string | null>(null)
  const [downloadController, setDownloadController] = useState<AbortController | null>(null)
  const downloadGuardRef = useRef(false)
  const downloadControllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      downloadControllerRef.current?.abort()
    }
  }, [])

  const startDownload = async (key: string, run: (signal: AbortSignal) => Promise<void>) => {
    if (downloadGuardRef.current) return
    downloadGuardRef.current = true
    const controller = new AbortController()
    downloadControllerRef.current = controller
    setDownloadKey(key)
    setDownloadController(controller)
    try {
      await run(controller.signal)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        if (mountedRef.current) pushToast('下载已取消。', 'info')
      } else if (mountedRef.current) {
        pushToast(describeError(error), 'error')
      }
    } finally {
      downloadGuardRef.current = false
      downloadControllerRef.current = null
      if (mountedRef.current) {
        setDownloadKey(null)
        setDownloadController(null)
      }
    }
  }

  return (
    <aside className="project-files-panel" aria-label="项目文件">
      <header className="project-files-header">
        <div>
          <span className="eyebrow">PROJECT FILES</span>
          <h2>项目文件</h2>
        </div>
        <div className="project-files-actions">
          <button
            type="button"
            className="icon-btn icon-btn-xs"
            onClick={() => void refresh()}
            disabled={refreshing}
            aria-label="刷新项目文件"
            title="刷新项目文件"
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : undefined} />
          </button>
          <button
            type="button"
            className="icon-btn icon-btn-xs project-files-close"
            onClick={onClose}
            aria-label="收起项目文件"
          >
            <X size={15} />
          </button>
        </div>
      </header>

      {taskMutating ? (
        <div className="project-files-warning">
          <LoaderCircle size={14} className="spin" />
          任务正在修改项目，当前内容可能不是最新。
        </div>
      ) : null}

      <div className="project-files-toolbar">
        <span>工作区</span>
        {downloadController ? (
          <button
            type="button"
            className="project-files-download project-files-cancel"
            onClick={() => downloadController.abort()}
          >
            <X size={13} />
            取消下载
          </button>
        ) : (
          <button
            type="button"
            className="project-files-download"
            disabled={downloadKey !== null}
            onClick={() =>
              void startDownload('archive', (signal) =>
                downloadProjectArchive(projectId, signal),
              )
            }
          >
            {downloadKey === 'archive' ? (
              <LoaderCircle size={13} className="spin" />
            ) : (
              <Download size={13} />
            )}
            下载项目
          </button>
        )}
      </div>

      <div className="file-tree">
        <DirectoryBranch
          path=""
          directories={directories}
          expanded={expanded}
          selectedPath={preview.path}
          level={0}
          onToggle={toggleDirectory}
          onLoadMore={(path, cursor) => void loadDirectory(path, cursor, true)}
          onOpenFile={(path) => void openFile(path)}
        />
      </div>

      <section className="file-preview" aria-label="文件内容预览">
        <header className="file-preview-header">
          <div>
            <Code2 size={14} />
            <strong title={preview.path ?? undefined}>
              {preview.path?.split('/').at(-1) ?? '选择文件查看内容'}
            </strong>
          </div>
          {preview.path && preview.content !== null ? (
            <button
              type="button"
              className="icon-btn icon-btn-xs"
              disabled={downloadKey !== null}
              onClick={() =>
                void startDownload(`file:${preview.path}`, (signal) =>
                  downloadProjectFile(projectId, preview.path as string, signal),
                )
              }
              aria-label="下载当前文件"
              title="下载当前文件"
            >
              {downloadKey === `file:${preview.path}` ? (
                <LoaderCircle size={13} className="spin" />
              ) : (
                <Download size={13} />
              )}
            </button>
          ) : null}
        </header>
        <div className="file-preview-body">
          {!preview.path ? (
            <p>从上方目录选择一个文件。文件内容只读，不会在浏览器中执行。</p>
          ) : preview.loading ? (
            <span className="file-preview-status">
              <LoaderCircle size={15} className="spin" />
              正在读取文件…
            </span>
          ) : preview.error ? (
            <span className="file-preview-status file-preview-error">
              <AlertCircle size={15} />
              {preview.error}
            </span>
          ) : preview.content === '' ? (
            <p className="file-preview-empty">这是一个空文件。</p>
          ) : (
            <>
              <pre>
                <code>{preview.content}</code>
              </pre>
              <span className="file-preview-size">{formatFileSize(preview.sizeBytes)}</span>
            </>
          )}
        </div>
      </section>
    </aside>
  )
}
