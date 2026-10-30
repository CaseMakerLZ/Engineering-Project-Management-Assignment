import { useCallback, useEffect, useRef, useState } from 'react'
import { listProjectFiles, readProjectFile } from '../api/files'
import { ApiError, describeError } from '../lib/errors'
import type { ProjectFileEntry } from '../types/files'

const MAX_CACHED_FILES = 20
const MAX_CACHED_BYTES = 10 * 1024 * 1024
const ROOT_PATH = ''

interface DirectoryView {
  entries: ProjectFileEntry[]
  nextCursor: string | null
  loading: boolean
  loadingMore: boolean
  error: string | null
}

interface CachedDirectory {
  entries: ProjectFileEntry[]
  nextCursor: string | null
}

interface CachedContent {
  content: string
  sizeBytes: number
}

export interface FilePreviewState {
  path: string | null
  content: string | null
  sizeBytes: number
  loading: boolean
  error: string | null
}

const EMPTY_DIRECTORY: DirectoryView = {
  entries: [],
  nextCursor: null,
  loading: false,
  loadingMore: false,
  error: null,
}

const EMPTY_PREVIEW: FilePreviewState = {
  path: null,
  content: null,
  sizeBytes: 0,
  loading: false,
  error: null,
}

function contentError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 415) return '这个文件不是受支持的 UTF-8 文本，无法预览。'
    if (error.status === 413) return '文件超过预览大小限制，请直接下载查看。'
    if (error.status === 409) return '项目正在修改中，请等任务结束后刷新。'
  }
  return describeError(error)
}

export function useProjectFiles(projectId: string, refreshVersion: number) {
  const [directories, setDirectories] = useState<Record<string, DirectoryView>>({})
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set([ROOT_PATH]))
  const [preview, setPreview] = useState<FilePreviewState>(EMPTY_PREVIEW)
  const [refreshing, setRefreshing] = useState(false)

  const generationRef = useRef(0)
  const directoryCacheRef = useRef(new Map<string, CachedDirectory>())
  const directoryInflightRef = useRef(new Map<string, Promise<void>>())
  const contentCacheRef = useRef(new Map<string, CachedContent>())
  const contentInflightRef = useRef(new Map<string, Promise<void>>())
  const contentBytesRef = useRef(0)
  const selectedPathRef = useRef<string | null>(null)
  const expandedRef = useRef(expanded)
  const refreshingRef = useRef(false)
  const refreshRunRef = useRef(0)
  const reloadDirectoryRef = useRef<(path: string) => void>(() => undefined)

  expandedRef.current = expanded

  const updateDirectory = useCallback(
    (path: string, update: Partial<DirectoryView>) => {
      setDirectories((current) => ({
        ...current,
        [path]: { ...(current[path] ?? EMPTY_DIRECTORY), ...update },
      }))
    },
    [],
  )

  const loadDirectory = useCallback(
    async (path: string, cursor?: string, append = false): Promise<void> => {
      const generation = generationRef.current
      const key = `${path}\u0000${cursor ?? ''}`
      const existing = directoryInflightRef.current.get(key)
      if (existing) return existing

      updateDirectory(
        path,
        append ? { loadingMore: true, error: null } : { loading: true, error: null },
      )

      const request = (async () => {
        try {
          const page = await listProjectFiles(projectId, path, cursor)
          if (generation !== generationRef.current) return
          const previous = directoryCacheRef.current.get(path)
          const entries =
            append && previous
              ? [
                  ...previous.entries,
                  ...page.entries.filter(
                    (entry) =>
                      !previous.entries.some(
                        (known) => known.path === entry.path && known.kind === entry.kind,
                      ),
                  ),
                ]
              : page.entries
          const cached = { entries, nextCursor: page.next_cursor }
          directoryCacheRef.current.set(path, cached)
          updateDirectory(path, {
            entries,
            nextCursor: page.next_cursor,
            loading: false,
            loadingMore: false,
            error: null,
          })
        } catch (error) {
          if (generation !== generationRef.current) return
          if (append && error instanceof ApiError && error.status === 409) {
            directoryCacheRef.current.delete(path)
            updateDirectory(path, {
              loadingMore: false,
              error: null,
            })
            reloadDirectoryRef.current(path)
            return
          }
          updateDirectory(path, {
            loading: false,
            loadingMore: false,
            error:
              error instanceof ApiError && error.status === 409
                ? '项目正在修改中，请等任务结束后刷新。'
                : describeError(error),
          })
        } finally {
          if (generation === generationRef.current) {
            directoryInflightRef.current.delete(key)
          }
        }
      })()

      directoryInflightRef.current.set(key, request)
      return request
    },
    [projectId, updateDirectory],
  )
  reloadDirectoryRef.current = (path: string) => {
    void loadDirectory(path)
  }

  const trimContentCache = useCallback(() => {
    const cache = contentCacheRef.current
    while (cache.size > MAX_CACHED_FILES || contentBytesRef.current > MAX_CACHED_BYTES) {
      const oldest = cache.entries().next().value as
        | [string, CachedContent]
        | undefined
      if (!oldest) break
      cache.delete(oldest[0])
      contentBytesRef.current -= oldest[1].sizeBytes
    }
  }, [])

  const openFile = useCallback(
    async (path: string): Promise<void> => {
      selectedPathRef.current = path
      const cached = contentCacheRef.current.get(path)
      if (cached) {
        contentCacheRef.current.delete(path)
        contentCacheRef.current.set(path, cached)
        setPreview({
          path,
          content: cached.content,
          sizeBytes: cached.sizeBytes,
          loading: false,
          error: null,
        })
        return
      }

      setPreview({
        path,
        content: null,
        sizeBytes: 0,
        loading: true,
        error: null,
      })

      const existing = contentInflightRef.current.get(path)
      if (existing) return existing
      const generation = generationRef.current
      const request = (async () => {
        try {
          const file = await readProjectFile(projectId, path)
          if (generation !== generationRef.current) return
          const cachedContent = {
            content: file.content,
            sizeBytes: Math.max(
              file.size_bytes,
              new TextEncoder().encode(file.content).byteLength,
            ),
          }
          const previous = contentCacheRef.current.get(path)
          if (previous) contentBytesRef.current -= previous.sizeBytes
          contentCacheRef.current.delete(path)
          contentCacheRef.current.set(path, cachedContent)
          contentBytesRef.current += cachedContent.sizeBytes
          trimContentCache()
          if (selectedPathRef.current === path) {
            setPreview({
              path,
              content: file.content,
              sizeBytes: file.size_bytes,
              loading: false,
              error: null,
            })
          }
        } catch (error) {
          if (generation !== generationRef.current) return
          if (selectedPathRef.current === path) {
            setPreview({
              path,
              content: null,
              sizeBytes: 0,
              loading: false,
              error: contentError(error),
            })
          }
        } finally {
          if (generation === generationRef.current) {
            contentInflightRef.current.delete(path)
          }
        }
      })()
      contentInflightRef.current.set(path, request)
      return request
    },
    [projectId, trimContentCache],
  )

  const refresh = useCallback(async (force = false): Promise<void> => {
    if (refreshingRef.current && !force) return
    const run = ++refreshRunRef.current
    refreshingRef.current = true
    setRefreshing(true)
    generationRef.current += 1
    directoryCacheRef.current.clear()
    directoryInflightRef.current.clear()
    contentCacheRef.current.clear()
    contentInflightRef.current.clear()
    contentBytesRef.current = 0
    setDirectories({})

    const currentFile = selectedPathRef.current
    const paths = [ROOT_PATH, ...expandedRef.current].filter(
      (path, index, values) => values.indexOf(path) === index,
    )
    await Promise.all([
      ...paths.map((path) => loadDirectory(path)),
      ...(currentFile ? [openFile(currentFile)] : []),
    ])
    if (run === refreshRunRef.current) {
      refreshingRef.current = false
      setRefreshing(false)
    }
  }, [loadDirectory, openFile])

  useEffect(() => {
    expandedRef.current = new Set([ROOT_PATH])
    setExpanded(new Set([ROOT_PATH]))
    selectedPathRef.current = null
    setPreview(EMPTY_PREVIEW)
    void refresh(true)
    return () => {
      generationRef.current += 1
      refreshRunRef.current += 1
    }
  }, [projectId, refresh, refreshVersion])

  const toggleDirectory = useCallback(
    (path: string) => {
      const opening = !expandedRef.current.has(path)
      setExpanded((current) => {
        const next = new Set(current)
        if (next.has(path)) next.delete(path)
        else next.add(path)
        expandedRef.current = next
        return next
      })
      if (opening && !directoryCacheRef.current.has(path) && !directories[path]) {
        void loadDirectory(path)
      }
    },
    [directories, loadDirectory],
  )

  return {
    directories,
    expanded,
    preview,
    refreshing,
    toggleDirectory,
    loadDirectory,
    openFile,
    refresh,
  }
}
