import type { TaskStatus } from './api'

export type TurnConnectionStatus =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'

export interface TurnDisplayMessage {
  message_id: string
  text: string
}

export interface TurnToolState {
  call_id: string
  tool_name: string
  success?: boolean
  error?: string | null
  error_code?: string | null
}

export interface TurnEventBase {
  task_id: string
  conversation_id: string
  run_id?: string | null
  sequence: number
  created_at?: string
}

export interface TurnSnapshotEvent extends TurnEventBase {
  status: TaskStatus
  messages?: TurnDisplayMessage[]
  active_tool?: Omit<TurnToolState, 'success' | 'error' | 'error_code'> | null
  result?: string | null
  error?: string | null
}

export interface AssistantDeltaEvent extends TurnEventBase {
  message_id: string
  delta: string
}

export interface ToolStartedEvent extends TurnEventBase {
  call_id: string
  tool_name: string
}

export interface ToolFinishedEvent extends ToolStartedEvent {
  success: boolean
  error_code?: string | null
  error?: string | null
}

export interface RunTerminalEvent extends TurnEventBase {
  status: TaskStatus
  result?: string | null
  error?: string | null
}

export interface StreamErrorEvent extends TurnEventBase {
  code: string
  message: string
  retryable?: boolean
}

export type TurnEventName =
  | 'run.snapshot'
  | 'run.started'
  | 'assistant.delta'
  | 'tool.started'
  | 'tool.finished'
  | 'run.completed'
  | 'run.failed'
  | 'run.cancelled'
  | 'stream.error'

export type TurnEventPayload =
  | TurnSnapshotEvent
  | AssistantDeltaEvent
  | ToolStartedEvent
  | ToolFinishedEvent
  | RunTerminalEvent
  | StreamErrorEvent
  | TurnEventBase

export interface TurnEventFrame {
  event: TurnEventName
  id?: string
  data: TurnEventPayload
}

export interface TurnStreamState {
  status: TaskStatus
  messages: TurnDisplayMessage[]
  activeTool: TurnToolState | null
  tools: TurnToolState[]
  connectionStatus: TurnConnectionStatus
  sequence: number
  result: string | null
  error: string | null
  channelError: string | null
  reconnectAttempt: number
}
