import { ApiError } from '../lib/errors'
import type { ProjectFileContent, ProjectFileTree } from '../types/files'
import { apiRequest } from './client'
import { bearerHeaders, emitAuthExpired, endpoint } from './client'

const MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024

function query(path: string, values: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null) params.set(key, String(value))
  })
  const suffix = params.toString()
  return suffix ? `${path}?${suffix}` : path
}

export function listProjectFiles(
  projectId: string,
  path = '',
  cursor?: string,
  pageSize = 100,
): Promise<ProjectFileTree> {
  return apiRequest<ProjectFileTree>(
    query(`/api/projects/${encodeURIComponent(projectId)}/files/tree`, {
      path,
      page_size: pageSize,
      cursor,
    }),
  )
}

export function readProjectFile(
  projectId: string,
  path: string,
): Promise<ProjectFileContent> {
  return apiRequest<ProjectFileContent>(
    query(`/api/projects/${encodeURIComponent(projectId)}/files/content`, { path }),
  )
}

async function responseError(response: Response): Promise<ApiError> {
  let message = `下载失败（HTTP ${response.status}）`
  let code: number | undefined
  try {
    const payload = (await response.json()) as { msg?: string; code?: number }
    message = payload.msg?.trim() || message
    code = typeof payload.code === 'number' ? payload.code : undefined
  } catch {
    // Error responses are not guaranteed to use JSON when a stream already started.
  }
  if (response.status === 401 || code === 10002) emitAuthExpired()
  return new ApiError(message, response.status, code)
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim())
    } catch {
      // Fall through to the plain filename parameter.
    }
  }
  const plainMatch = header.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1]?.trim() || fallback
}

async function fetchDownload(
  path: string,
  signal?: AbortSignal,
  expectedType?: string,
): Promise<{ blob: Blob; filename: string | null }> {
  let response: Response
  try {
    response = await fetch(endpoint(path), {
      headers: bearerHeaders(expectedType ?? 'application/octet-stream'),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new TypeError('下载请求失败')
  }
  if (!response.ok) throw await responseError(response)

  const contentType = response.headers.get('Content-Type')?.toLowerCase() ?? ''
  if (contentType.includes('application/json')) {
    let payload: { msg?: string; code?: number } | null = null
    try {
      payload = (await response.json()) as { msg?: string; code?: number }
    } catch {
      // The content type is still invalid for a file download.
    }
    throw new ApiError(
      payload?.msg?.trim() || '服务器返回了错误响应，未保存下载文件。',
      response.status,
      payload?.code,
    )
  }
  if (expectedType && !contentType.includes(expectedType)) {
    throw new ApiError('服务器返回的文件类型不符合预期。', response.status)
  }

  const declaredLength = Number(response.headers.get('Content-Length'))
  if (Number.isFinite(declaredLength) && declaredLength > MAX_DOWNLOAD_BYTES) {
    throw new ApiError('下载内容超过前端允许的大小，请缩小导出范围。', 413)
  }

  return {
    blob: await readLimitedBlob(response, MAX_DOWNLOAD_BYTES),
    filename: response.headers.get('Content-Disposition'),
  }
}

async function readLimitedBlob(response: Response, maxBytes: number): Promise<Blob> {
  if (!response.body) return response.blob()
  const reader = response.body.getReader()
  const chunks: BlobPart[] = []
  let total = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      total += value.byteLength
      if (total > maxBytes) {
        throw new ApiError('下载内容超过前端允许的大小，请缩小导出范围。', 413)
      }
      chunks.push(value as unknown as BlobPart)
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
  return new Blob(chunks, {
    type: response.headers.get('Content-Type') ?? 'application/octet-stream',
  })
}

export async function downloadProjectFile(
  projectId: string,
  path: string,
  signal?: AbortSignal,
): Promise<void> {
  const result = await fetchDownload(
    query(`/api/projects/${encodeURIComponent(projectId)}/files/download`, { path }),
    signal,
  )
  const fallback = path.split('/').filter(Boolean).at(-1) || 'download'
  saveBlob(result.blob, filenameFromDisposition(result.filename, fallback))
}

export async function downloadProjectArchive(
  projectId: string,
  signal?: AbortSignal,
): Promise<void> {
  const result = await fetchDownload(
    `/api/projects/${encodeURIComponent(projectId)}/archive`,
    signal,
    'application/zip',
  )
  saveBlob(result.blob, filenameFromDisposition(result.filename, 'project.zip'))
}

function saveBlob(blob: Blob, filename: string): void {
  const safeName = filename
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_')
    .replace(/^\.+$/, '')
    .trim()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = safeName || 'download'
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

export {
  filenameFromDisposition,
}
