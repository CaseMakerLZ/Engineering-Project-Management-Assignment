import type { LoginResponse, User } from '../types/api'
import { apiRequest } from './client'

export interface Credentials {
  username: string
  password: string
}

export function register(credentials: Credentials): Promise<User> {
  return apiRequest<User>('/api/auth/register', {
    method: 'POST',
    body: credentials,
    auth: false,
  })
}

export function login(credentials: Credentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: credentials,
    auth: false,
  })
}

export function getCurrentUser(): Promise<User> {
  return apiRequest<User>('/api/auth/me')
}

export function logout(): Promise<void> {
  return apiRequest<void>('/api/auth/logout', { method: 'POST' })
}
