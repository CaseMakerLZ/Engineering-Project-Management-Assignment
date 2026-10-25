export type TaskStatus = 'CREATED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export interface ResultEnvelope<T> {
  code: number
  msg: string
  data: T
}

export interface User {
  user_id: string
  username: string
}

export interface LoginResponse {
  token: string
  expires_in: number
  user: User
}

export interface Project {
  project_id: string
  name: string
  description: string
  local_path?: string | null
  created_at: string
  updated_at: string
}

export interface CreateProjectInput {
  name: string
  description?: string
  local_path?: string
}

export interface Conversation {
  conversation_id: string
  project_id: string
  title: string
  status?: string | null
  created_at: string
  updated_at: string
}

export interface CreateConversationInput {
  title: string
}

export interface Turn {
  task_id: string
  conversation_id: string
  python_run_id?: string | null
  prompt: string
  status: TaskStatus
  result?: string | null
  error?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}

export interface CreateTurnResponse {
  task_id: string
  conversation_id: string
  python_run_id?: string | null
  status: TaskStatus
}

export interface CreateTurnInput {
  prompt: string
}
