import type { CreateProjectInput, Project } from '../types/api'
import { apiRequest } from './client'

export function listProjects(): Promise<Project[]> {
  return apiRequest<Project[]>('/api/projects')
}

export function createProject(input: CreateProjectInput): Promise<Project> {
  return apiRequest<Project>('/api/projects', { method: 'POST', body: input })
}

export function getProject(projectId: string): Promise<Project> {
  return apiRequest<Project>(`/api/projects/${encodeURIComponent(projectId)}`)
}
