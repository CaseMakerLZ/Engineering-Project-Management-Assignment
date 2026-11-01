export type ProjectFileKind = 'file' | 'directory'

export interface ProjectFileEntry {
  name: string
  path: string
  kind: ProjectFileKind
  size_bytes: number | null
}

export interface ProjectFileTree {
  project_id: string
  path: string
  entries: ProjectFileEntry[]
  next_cursor: string | null
}

export interface ProjectFileContent {
  project_id: string
  path: string
  content: string
  size_bytes: number
  encoding: string
}

export interface LocalDirectoryRoot {
  root_id: string
  name: string
}

export interface LocalDirectoryEntry {
  name: string
  path: string
}

export interface LocalDirectoryListing {
  roots: LocalDirectoryRoot[]
  root_id: string | null
  path: string | null
  absolute_path: string | null
  entries: LocalDirectoryEntry[]
  next_cursor: string | null
}

export interface SelectedLocalDirectory {
  root_id: string
  path: string
  absolute_path: string
}

export interface CreateLocalDirectoryInput {
  root_id: string
  parent_path: string
  name: string
}
