import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  Check,
  ChevronRight,
  Folder,
  FolderPlus,
  Home,
  LoaderCircle,
  RotateCcw,
} from 'lucide-react'
import {
  createLocalDirectory,
  listLocalDirectories,
} from '../api/localDirectories'
import { ApiError, describeError } from '../lib/errors'
import { validateLocalDirectoryName } from '../lib/localDirectoryName'
import type {
  LocalDirectoryListing,
  SelectedLocalDirectory,
} from '../types/files'
import { Modal } from './Modal'

interface DirectoryPickerProps {
  open: boolean
  initialRootId?: string | null
  initialPath?: string | null
  onClose: () => void
  onSelect: (directory: SelectedLocalDirectory) => void
  onFolderCreated?: (directory: SelectedLocalDirectory) => void
  allowCreate?: boolean
}

interface PickerLocation {
  rootId: string | null
  path: string | null
}

const INITIAL_LOCATION: PickerLocation = { rootId: null, path: null }

export function DirectoryPicker({
  open,
  initialRootId,
  initialPath,
  onClose,
  onSelect,
  onFolderCreated,
  allowCreate = true,
}: DirectoryPickerProps) {
  const [location, setLocation] = useState<PickerLocation>(INITIAL_LOCATION)
  const [listing, setListing] = useState<LocalDirectoryListing | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creatingOpen, setCreatingOpen] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [createdNotice, setCreatedNotice] = useState<string | null>(null)
  const requestIdRef = useRef(0)
  const creatingRef = useRef(false)

  const loadLocation = useCallback(async (next: PickerLocation, append = false) => {
    const requestId = append ? requestIdRef.current : ++requestIdRef.current
    setLocation(next)
    if (append) setLoadingMore(true)
    else {
      setListing(null)
      setLoading(true)
      setError(null)
    }
    try {
      const data = await listLocalDirectories({
        rootId: next.rootId ?? undefined,
        path: next.path ?? undefined,
        cursor: append ? (listing?.next_cursor ?? undefined) : undefined,
      })
      if (requestId !== requestIdRef.current) return
      setListing((current) => {
        if (!append || !current) return data
        const known = new Set(current.entries.map((entry) => entry.path))
        return {
          ...data,
          entries: [
            ...current.entries,
            ...data.entries.filter((entry) => !known.has(entry.path)),
          ],
        }
      })
    } catch (loadError) {
      if (requestId !== requestIdRef.current) return
      setError(
        loadError instanceof ApiError && loadError.status === 404
          ? '目录不存在、已被移动，或当前不允许访问。'
          : describeError(loadError),
      )
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
        setLoadingMore(false)
      }
    }
  }, [listing?.next_cursor])

  useEffect(() => {
    if (!open) return
    requestIdRef.current += 1
    setListing(null)
    setLoading(true)
    setLoadingMore(false)
    setError(null)
    setCreatingOpen(false)
    setFolderName('')
    setCreating(false)
    setCreateError(null)
    setCreatedNotice(null)
    creatingRef.current = false
    const next = initialRootId
      ? { rootId: initialRootId, path: initialPath ?? '' }
      : INITIAL_LOCATION
    void loadLocation(next)
    return () => {
      requestIdRef.current += 1
    }
    // initial values intentionally define a fresh browsing session on each open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPath, initialRootId, open])

  const goToParent = () => {
    if (!location.rootId || !location.path) return
    const parts = location.path.split('/').filter(Boolean)
    parts.pop()
    void loadLocation({ rootId: location.rootId, path: parts.join('/') })
  }

  const handleCreate = async () => {
    if (!location.rootId || location.path === null || creatingRef.current) return
    const validation = validateLocalDirectoryName(folderName)
    if (validation) {
      setCreateError(validation)
      return
    }
    creatingRef.current = true
    setCreating(true)
    setCreateError(null)
    try {
      const created = await createLocalDirectory({
        root_id: location.rootId,
        parent_path: location.path,
        name: folderName.trim(),
      })
      setCreatingOpen(false)
      setFolderName('')
      setCreatedNotice(`“${created.path.split('/').at(-1)}”已创建。确认选择后会绑定这个文件夹。`)
      onFolderCreated?.(created)
      await loadLocation({ rootId: created.root_id, path: created.path })
    } catch (createFailure) {
      const message =
        createFailure instanceof ApiError && createFailure.status === 409
          ? '同名文件夹已存在，未覆盖原目录。'
          : describeError(createFailure)
      setCreateError(message)
    } finally {
      creatingRef.current = false
      setCreating(false)
    }
  }

  const canConfirm =
    Boolean(location.rootId) &&
    location.path !== null &&
    Boolean(listing?.absolute_path) &&
    !loading &&
    !error

  const breadcrumbParts = (location.path ?? '').split('/').filter(Boolean)
  const rootName =
    listing?.roots.find((root) => root.root_id === location.rootId)?.name ??
    location.rootId ??
    '位置'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="选择项目文件夹"
      description="目录来自运行 Java 的电脑。浏览器、Java 和 Agent 需要在同一台电脑上访问同一个文件系统。"
      size="wide"
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canConfirm || creating}
            onClick={() => {
              if (!listing?.root_id || listing.path === null || !listing.absolute_path) return
              onSelect({
                root_id: listing.root_id,
                path: listing.path,
                absolute_path: listing.absolute_path,
              })
            }}
          >
            <Check size={16} />
            选择此文件夹
          </button>
        </>
      }
    >
      <div className="directory-picker">
        <div className="directory-picker-toolbar">
          <button
            type="button"
            className="icon-btn icon-btn-xs"
            onClick={() => void loadLocation(INITIAL_LOCATION)}
            disabled={loading || creating}
            aria-label="返回允许位置"
            title="返回允许位置"
          >
            <Home size={14} />
          </button>
          <button
            type="button"
            className="icon-btn icon-btn-xs"
            onClick={goToParent}
            disabled={!location.rootId || !location.path || loading || creating}
            aria-label="返回上级文件夹"
            title="返回上级文件夹"
          >
            <ArrowLeft size={14} />
          </button>
          <nav className="directory-breadcrumbs" aria-label="当前目录">
            {listing?.root_id ? (
              <>
                <button
                  type="button"
                  onClick={() => void loadLocation({ rootId: listing.root_id, path: '' })}
                  disabled={loading}
                >
                  {rootName}
                </button>
                {breadcrumbParts.map((part, index) => {
                  const path = breadcrumbParts.slice(0, index + 1).join('/')
                  return (
                    <span key={path}>
                      <ChevronRight size={12} />
                      <button
                        type="button"
                        onClick={() => void loadLocation({ rootId: location.rootId, path })}
                        disabled={loading}
                      >
                        {part}
                      </button>
                    </span>
                  )
                })}
              </>
            ) : (
              <span>可用位置</span>
            )}
          </nav>
          {listing?.root_id && allowCreate ? (
            <button
              type="button"
              className="btn btn-secondary btn-small directory-new-folder"
              onClick={() => {
                setCreatingOpen(true)
                setCreateError(null)
              }}
              disabled={loading || creating}
            >
              <FolderPlus size={14} />
              新建文件夹
            </button>
          ) : null}
        </div>

        {createdNotice ? <div className="form-success directory-notice">{createdNotice}</div> : null}

        {creatingOpen ? (
          <div className="directory-create-form">
            <label>
              <span>新文件夹名称</span>
              <input
                autoFocus
                value={folderName}
                onChange={(event) => {
                  setFolderName(event.target.value)
                  setCreateError(null)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void handleCreate()
                  }
                }}
                placeholder="例如 course-agent"
                maxLength={100}
              />
            </label>
            <button
              type="button"
              className="btn btn-primary btn-small"
              onClick={() => void handleCreate()}
              disabled={creating}
            >
              {creating ? <LoaderCircle size={14} className="spin" /> : <FolderPlus size={14} />}
              创建
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={() => {
                setCreatingOpen(false)
                setFolderName('')
                setCreateError(null)
              }}
              disabled={creating}
            >
              取消
            </button>
          </div>
        ) : null}
        {createError ? (
          <div className="form-alert directory-create-error">{createError}</div>
        ) : null}

        <div className="directory-picker-list">
          {loading ? (
            <div className="directory-picker-status">
              <LoaderCircle size={17} className="spin" />
              正在读取目录…
            </div>
          ) : null}
          {error && !loading ? (
            <div className="directory-picker-status directory-picker-error">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button type="button" onClick={() => void loadLocation(location)}>
                <RotateCcw size={13} />
                重试
              </button>
            </div>
          ) : null}

          {!loading && !error && listing?.root_id === null ? (
            <div className="directory-roots">
              {listing.roots.length === 0 ? (
                <div className="directory-picker-status">Java 没有返回可用的目录入口。</div>
              ) : (
                listing.roots.map((root) => (
                  <button
                    key={root.root_id}
                    type="button"
                    className="directory-root-card"
                    onClick={() => void loadLocation({ rootId: root.root_id, path: '' })}
                  >
                    <Folder size={21} />
                    <span>
                      <strong>{root.name}</strong>
                      <small>点击进入</small>
                    </span>
                    <ChevronRight size={15} />
                  </button>
                ))
              )}
            </div>
          ) : null}

          {!loading && !error && listing?.root_id ? (
            <>
              <div className="directory-current-path">{listing.absolute_path}</div>
              {listing.entries.length === 0 ? (
                <div className="directory-empty">
                  <Folder size={26} />
                  <strong>空文件夹</strong>
                  <span>这个文件夹仍可直接选择。</span>
                </div>
              ) : (
                <div className="directory-entry-list">
                  {listing.entries.map((entry) => (
                    <button
                      key={entry.path}
                      type="button"
                      className="directory-entry"
                      onClick={() =>
                        void loadLocation({
                          rootId: listing.root_id,
                          path: entry.path,
                        })
                      }
                    >
                      <Folder size={17} />
                      <span>{entry.name}</span>
                      <ChevronRight size={15} />
                    </button>
                  ))}
                </div>
              )}
              {listing.next_cursor ? (
                <button
                  type="button"
                  className="directory-load-more"
                  disabled={loadingMore}
                  onClick={() => void loadLocation(location, true)}
                >
                  {loadingMore ? <LoaderCircle size={13} className="spin" /> : null}
                  加载更多
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </Modal>
  )
}
