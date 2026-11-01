import { apiRequest } from './client'
import type {
  CreateLocalDirectoryInput,
  LocalDirectoryListing,
  SelectedLocalDirectory,
} from '../types/files'

export function listLocalDirectories(input?: {
  rootId?: string
  path?: string
  cursor?: string
  pageSize?: number
}): Promise<LocalDirectoryListing> {
  const params = new URLSearchParams()
  if (input?.rootId) params.set('root_id', input.rootId)
  if (input?.path !== undefined) params.set('path', input.path)
  if (input?.cursor) params.set('cursor', input.cursor)
  if (input?.pageSize) params.set('page_size', String(input.pageSize))
  const suffix = params.toString()
  return apiRequest<LocalDirectoryListing>(
    `/api/local/directories${suffix ? `?${suffix}` : ''}`,
  )
}

export function createLocalDirectory(
  input: CreateLocalDirectoryInput,
): Promise<SelectedLocalDirectory> {
  return apiRequest<SelectedLocalDirectory>('/api/local/directories', {
    method: 'POST',
    body: input,
  })
}
