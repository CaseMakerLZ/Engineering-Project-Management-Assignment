import type {
  Conversation,
  CreateConversationInput,
  CreateTurnInput,
  CreateTurnResponse,
  Turn,
} from '../types/api'
import { apiRequest } from './client'

export function listConversations(projectId: string): Promise<Conversation[]> {
  return apiRequest<Conversation[]>(
    `/api/projects/${encodeURIComponent(projectId)}/conversations`,
  )
}

export function createConversation(
  projectId: string,
  input: CreateConversationInput,
): Promise<Conversation> {
  return apiRequest<Conversation>(
    `/api/projects/${encodeURIComponent(projectId)}/conversations`,
    { method: 'POST', body: input },
  )
}

export function getConversation(conversationId: string): Promise<Conversation> {
  return apiRequest<Conversation>(`/api/conversations/${encodeURIComponent(conversationId)}`)
}

export function listTurns(conversationId: string): Promise<Turn[]> {
  return apiRequest<Turn[]>(
    `/api/conversations/${encodeURIComponent(conversationId)}/turns`,
  )
}

export function createTurn(
  conversationId: string,
  input: CreateTurnInput,
): Promise<CreateTurnResponse> {
  return apiRequest<CreateTurnResponse>(
    `/api/conversations/${encodeURIComponent(conversationId)}/turns`,
    { method: 'POST', body: input },
  )
}

export function getTurn(conversationId: string, taskId: string): Promise<Turn> {
  return apiRequest<Turn>(
    `/api/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(taskId)}`,
  )
}
