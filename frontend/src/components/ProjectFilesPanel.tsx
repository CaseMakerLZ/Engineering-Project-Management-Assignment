import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
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
  onResizeStart: (event: React.PointerEvent<HTMLElement>) => void
  onResizeKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void
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
                    title={entry.path}
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

function fileName(path: string): string {
  return path.split('/').filter(Boolean).at(-1) ?? path
}

export function ProjectFilesPanel({
  projectId,
  refreshVersion,
  taskMutating,
  onClose,
  onResizeStart,
  onResizeKeyDown,
}: ProjectFilesPanelProps) {
  const { directories, expanded, preview, refreshing, toggleDirectory, loadDirectory, openFile, refresh } =
    useProjectFiles(projectId, refreshVersion)
  const { pushToast } = useToast()
  const [view, setView] = useState<'directory' | 'content'>('directory')
  const [downloadKey, setDownloadKey] = useState<string | null>(null)
  const [downloadController, setDownloadController] = useState<AbortController | null>(null)
  const downloadGuardRef = useRef(false)
  const downloadControllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)
  const treeRef = useRef<HTMLDivElement>(null)

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

  const openFileView = (path: string) => {
    setView('content')
    void openFile(path)
  }

  const returnToDirectory = () => {
    setView('directory')
    window.requestAnimationFrame(() => treeRef.current?.focus())
  }

  return (
    <aside className="project-files-panel" aria-label="项目文件">
      <button
        type="button"
        className="files-resize-handle"
        onPointerDown={onResizeStart}
        onKeyDown={onResizeKeyDown}
        aria-label="调整文件面板宽度"
        aria-orientation="vertical"
        title="拖动调整宽度；方向键微调，Home 恢复默认"
      />

      <header className="project-files-header">
        <div className="project-files-title">
          {view === 'content' ? (
            <button
              type="button"
              className="project-files-back"
              onClick={returnToDirectory}
              aria-label="返回目录"
              title="返回目录"
            >
              <ArrowLeft size={15} />
              返回目录
            </button>
          ) : (
            <strong>项目文件</strong>
          )}
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

      <div className="files-panel-view" hidden={view !== 'directory'}>
        <div className="project-files-toolbar">
          <span>目录</span>
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

        <div className="file-tree" ref={treeRef} tabIndex={-1}>
          <DirectoryBranch
            path=""
            directories={directories}
            expanded={expanded}
            selectedPath={preview.path}
            level={0}
            onToggle={toggleDirectory}
            onLoadMore={(path, cursor) => void loadDirectory(path, cursor, true)}
            onOpenFile={openFileView}
          />
        </div>
      </div>

      <section className="files-panel-view file-content-view" hidden={view !== 'content'}>
        <header className="file-content-header">
          <div>
            <strong title={preview.path ?? undefined}>
              {preview.path ? fileName(preview.path) : '文件内容'}
            </strong>
            {preview.path ? <small title={preview.path}>{preview.path}</small> : null}
          </div>
          {preview.path ? (
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
            <p>从目录选择一个文件。</p>
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
